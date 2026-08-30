import csv
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
DATABASE = SKILL_ROOT / "scripts" / "update_emerging_database.py"
RUNNER = SKILL_ROOT / "scripts" / "run_emerging_radar.py"
ROUTER = SKILL_ROOT / "scripts" / "route_candidates.py"
CONTRACTS = Path(__file__).resolve().parents[3] / "runtime" / "stage_contracts.json"
VALIDATOR = Path(__file__).resolve().parents[3] / "runtime" / "stage_validator.py"


def load_module(name, path):
    scripts_dir = str(path.parent)
    sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.path.remove(scripts_dir)
    return module


def test_database_merge_preserves_first_seen_and_previous_state(tmp_path):
    database = load_module("database_merge_red", DATABASE)
    existing = {
        "schema_version": 1,
        "records": [
            {
                "domain": "wedding",
                "keyword": "micro wedding",
                "first_observed_at": "2026-08-01",
                "last_seen_at": "2026-08-29T00:00:00Z",
                "status": "watch",
                "source_evidence": ["old.json"],
            }
        ],
    }

    merged = database.merge_database(
        existing,
        [
            {
                "domain": "wedding",
                "keyword": "micro wedding",
                "first_observed_at": "2026-08-20",
                "status": "emerging",
                "source_evidence": ["new.json"],
                "volume": None,
            }
        ],
        [],
        "2026-08-30T00:00:00Z",
    )

    record = merged["records"][0]
    assert record["first_observed_at"] == "2026-08-01"
    assert record["previous_status"] == "watch"
    assert record["status"] == "emerging"
    assert record["volume"] is None
    assert record["status_history"][-1]["status"] == "watch"
    assert record["status_history"][-1]["observed_at"] == "2026-08-29T00:00:00Z"
    assert record["previous_source_evidence"] == ["old.json"]

    database_path = tmp_path / ".seo-run" / "emerging-keywords.json"
    csv_path = tmp_path / ".seo-run" / "emerging-keywords.csv"
    database.write_database(merged, database_path, csv_path)
    written = json.loads(database_path.read_text(encoding="utf-8"))
    assert written["records"][0]["volume"] is None
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert row["volume"] == ""


def test_runner_does_not_make_autocomplete_or_semrush_edges_recursive():
    runner = load_module("runner_supplemental_red", RUNNER)
    related_calls = []
    autocomplete_calls = []
    semrush_calls = []

    def fake_related(anchor):
        related_calls.append(anchor)
        return {
            "related_queries": [
                {"query": f"{anchor} top", "relation_type": "top", "rank": 1, "is_google_breakout": False},
                {"query": f"{anchor} rising", "relation_type": "rising", "rank": 1, "rising_value": 200, "is_google_breakout": False},
            ]
        }

    def fake_autocomplete(anchor):
        autocomplete_calls.append(anchor)
        return [{"query": f"{anchor} autocomplete"}]

    def fake_semrush(anchor):
        semrush_calls.append(anchor)
        return [{"keyword": f"{anchor} semrush"}]

    result = runner.run_pipeline(
        fake_related,
        fake_autocomplete,
        fake_semrush,
        domain="wedding",
        max_depth=1,
        max_candidates=3,
    )

    assert result["recursive_edge_policy"] == "google_trends_rising_only"
    assert result["supplemental_recursive"] is False
    assert autocomplete_calls
    assert semrush_calls
    assert all("autocomplete" not in call and "semrush" not in call for call in related_calls)


def test_existing_root_confirmed_candidate_keeps_selection_handoff():
    router = load_module("router_history_red", ROUTER)
    route = router.route_candidate(
        {
            "keyword": "micro wedding",
            "root_id": "root-wedding",
            "root_relation": "existing_root",
            "status": "emerging",
            "signal_type": "breakout",
            "demand_history_type": "newly_observed",
            "estimated_birth_window": "2026-08",
            "birth_source_resolution": "weekly",
            "source_evidence": [{"source": "google_trends", "provenance_status": "verified"}],
        }
    )

    assert route["route"] == "selection_handoff"
    assert route["handoff"]["demand_history_type"] == "newly_observed"
    assert route["handoff"]["estimated_birth_window"] == "2026-08"
    assert "do_candidate" not in json.dumps(route)


def test_runner_result_has_a_valid_emerging_radar_run_contract():
    runner = load_module("runner_contract_red", RUNNER)

    result = runner.run_pipeline(
        lambda anchor: {"related_queries": []},
        domain="wedding",
    )
    validator = load_module("stage_validator_runner_contract_red", VALIDATOR)
    contracts = json.loads(CONTRACTS.read_text(encoding="utf-8"))

    assert validator.validate_stage("emerging_radar_run", result, contracts) == []


def test_runner_slug_does_not_collapse_unicode_only_keywords():
    runner = load_module("runner_unicode_slug_red", RUNNER)

    assert runner._slug("婚礼预算") != runner._slug("易经")


def test_runner_registers_and_validates_the_final_summary_stage(tmp_path):
    runner = load_module("runner_summary_stage_red", RUNNER)
    result = runner.run_pipeline(lambda anchor: {"related_queries": []}, domain="wedding")
    result["output_artifacts"] = {
        "run_summary": str(tmp_path / "run-summary.json"),
        "database": str(tmp_path / "emerging-keywords.json"),
        "csv": str(tmp_path / "emerging-keywords.csv"),
        "evidence_dir": str(tmp_path / "evidence"),
    }

    summary = tmp_path / "run-summary.json"
    runner.write_validated_run_summary(result, summary)
    payload = json.loads(summary.read_text(encoding="utf-8"))
    stage = payload["stages"]["emerging_radar_run"]

    assert stage["status"] == "PASS"
    assert Path(stage["validation_receipt_ref"]).is_file()


def test_runner_loads_current_semrush_ideas_descriptors_for_supplemental_use(tmp_path):
    runner = load_module("runner_semrush_descriptor_red", RUNNER)
    descriptor = tmp_path / "semrush-ideas-request.json"
    descriptor.write_text(
        json.dumps({"mode": "ideas", "seed": "wedding planner"}),
        encoding="utf-8",
    )

    request_map = runner.load_semrush_request_map([descriptor])

    assert request_map["wedding planner"] == descriptor


def test_unmapped_semrush_supplemental_anchor_remains_optional():
    runner = load_module("runner_optional_semrush_red", RUNNER)

    result = runner.run_pipeline(
        lambda anchor: {"related_queries": []},
        semrush_fetcher=lambda anchor: None,
        domain="wedding",
    )

    assert result["status"] == "PASS"
    assert not [blocker for blocker in result["blockers"] if blocker["stage"] == "semrush_ideas"]


def test_production_radar_contract_rejects_pass_with_blockers():
    validator = load_module("stage_validator_radar_blocker_red", VALIDATOR)
    contracts = json.loads(CONTRACTS.read_text(encoding="utf-8"))
    payload = {
        "domain": "wedding",
        "status": "PASS",
        "recursive_edge_policy": "google_trends_rising_only",
        "supplemental_recursive": False,
        "anchor_pool": [{"keyword": "wedding", "anchor_source": "domain", "discovery_depth": 0}],
        "candidate_counts": {},
        "blockers": [{"status": "BLOCKED", "reason": "unexpected blocker"}],
        "output_artifacts": {
            "run_summary": "summary.json",
            "database": "database.json",
            "csv": "database.csv",
            "evidence_dir": "evidence",
            "emerging_radar_run_validation": "summary.validation.json",
        },
    }

    errors = validator.validate_stage("emerging_radar_run", payload, contracts, production=True)

    assert any("blocker" in error.lower() for error in errors)
