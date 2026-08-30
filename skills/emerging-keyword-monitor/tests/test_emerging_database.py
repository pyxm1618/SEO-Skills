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
