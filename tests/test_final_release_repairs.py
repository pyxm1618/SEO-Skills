import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "runtime" / "codex_stage_hook.py"
START = ROOT / "runtime" / "start_seo_run.py"
VALIDATOR = ROOT / "runtime" / "stage_validator.py"
PIPELINE = ROOT / "runtime" / "emerging_pipeline.py"
ROUTE = ROOT / "skills" / "emerging-keyword-monitor" / "scripts" / "route_candidates.py"


def load_hook(name="final_release_hook"):
    spec = importlib.util.spec_from_file_location(name, HOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_validator(name="final_release_validator"):
    spec = importlib.util.spec_from_file_location(name, VALIDATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def start_run(tmp_path, route="traditional"):
    manifest = tmp_path / "active.json"
    env = dict(os.environ, SEO_RUN_MANIFEST=str(manifest))
    result = subprocess.run(
        [sys.executable, str(START), "--route", route],
        text=True,
        capture_output=True,
        env=env,
    )
    return result, manifest


def test_start_seo_run_creates_minimal_active_manifest(tmp_path):
    result, manifest_path = start_run(tmp_path)

    assert result.returncode == 0, result.stderr
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["run_id"]
    assert manifest["route"] == "traditional"
    assert manifest["status"] == "IN_PROGRESS"
    assert manifest["stages"] == {}
    assert manifest["candidates"] == {}


def test_start_seo_run_does_not_overwrite_active_in_progress_manifest(tmp_path):
    first, manifest_path = start_run(tmp_path)
    original = manifest_path.read_text(encoding="utf-8")

    second, _ = start_run(tmp_path, route="emerging")

    assert first.returncode == 0
    assert second.returncode == 2
    assert manifest_path.read_text(encoding="utf-8") == original
    assert "IN_PROGRESS" in second.stderr


@pytest.mark.parametrize(
    ("command", "stage"),
    [
        ("python3 runtime/stage_validator.py --stage discovery_handoff --input handoff.json", "discovery_coverage"),
        ("python3 runtime/collectors/google_live_collector.py intitle --keyword example --output out.json", "stage6_exact"),
        ("python3 runtime/kgr_evidence_merge.py --exact exact.json --intitle intitle.json", "stage6_exact"),
        ("python3 skills/seo-keyword-selection/scripts/evaluate_candidates.py --stage exact --input rows.json", "stage6_exact"),
        ("python3 runtime/collectors/google_live_collector.py serp --keyword example --output out.json", "kgr_intitle"),
        ("python3 skills/seo-keyword-selection/scripts/evaluate_candidates.py --stage final --input rows.json", "kgr_intitle"),
        ("python3 runtime/collectors/google_live_collector.py trends --keyword example --output out.json", "serp_review"),
        ("python3 runtime/stage_validator.py --stage finalist_trend --input trend.json", "serp_review"),
    ],
)
def test_multiline_protected_commands_have_same_stage_as_single_line(command, stage):
    hook = load_hook(f"multiline_{stage}_{abs(hash(command))}")
    multiline = command.replace(" ", " \\\n  ", 2)

    variants = (command, multiline, f"cd /tmp/project && {multiline}")

    for variant in variants:
        payload = {"tool_name": "Bash", "tool_input": {"command": variant}}
        assert hook._protected_requirement(payload) == stage


def test_ordinary_multiline_command_is_not_protected():
    hook = load_hook("multiline_ordinary")
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "python3 scripts/google_live_collector_helper.py \\\n  --mode intitle"},
    }

    assert hook._protected_requirement(payload) is None


def test_stop_without_an_seo_manifest_remains_available_for_ordinary_sessions():
    hook = load_hook("ordinary_stop_without_manifest")

    assert hook.stop({"stop_hook_active": False}, None) == 0


def write_candidate_validation_artifacts(tmp_path, hook, stage, receipt_candidate_id, row_keyword):
    report_path = tmp_path / f"{stage}.report.json"
    receipt_path = tmp_path / f"{stage}.receipt.json"
    report = {
        "stage": stage,
        "status": "PASS",
        "production": True,
        "candidate_id": receipt_candidate_id,
        "candidate_keyword": " ".join(row_keyword.split()).casefold(),
        "complete_count": 1,
        "blocked_count": 0,
        "complete": [{"keyword": row_keyword}],
        "blocked": [],
        "validation_receipt_ref": str(receipt_path),
    }
    report_path.write_text(json.dumps(report), encoding="utf-8")
    receipt = {
        "schema": "seo-stage-validation/v1",
        "stage": stage,
        "status": "PASS",
        "candidate_id": receipt_candidate_id,
        "candidate_keyword": report["candidate_keyword"],
        "validator_source_sha256": hook._sha256(hook.VALIDATOR_PATH),
        "report_ref": str(report_path),
        "report_sha256": hook._sha256(report_path),
    }
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    return {"status": "PASS", "validation_receipt_ref": str(receipt_path)}


def test_candidate_validation_writer_derives_keyword_from_the_only_complete_row(tmp_path):
    validator = load_validator("candidate_keyword_writer")
    report_path = tmp_path / "candidate.report.json"
    receipt_path = tmp_path / "candidate.receipt.json"
    report = {
        "stage": "stage6_exact",
        "status": "PASS",
        "production": True,
        "candidate_id": "cand-1",
        "complete_count": 1,
        "blocked_count": 0,
        "complete": [{"keyword": "  Wedding   Cost Calculator  "}],
        "blocked": [],
        "validation_receipt_ref": str(receipt_path),
    }

    receipt_path = validator._write_validation_receipt(report_path, report, "cand-1")

    saved_report = json.loads(report_path.read_text(encoding="utf-8"))
    saved_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert saved_report["candidate_keyword"] == "wedding cost calculator"
    assert saved_receipt["candidate_keyword"] == "wedding cost calculator"


def test_candidate_validation_writer_rejects_multiple_complete_rows(tmp_path):
    validator = load_validator("candidate_keyword_multiple_rows")
    report = {
        "stage": "stage6_exact",
        "status": "PASS",
        "production": True,
        "candidate_id": "cand-1",
        "complete_count": 2,
        "blocked_count": 0,
        "complete": [{"keyword": "one"}, {"keyword": "two"}],
        "blocked": [],
    }

    with pytest.raises(ValueError, match="exactly one"):
        validator._write_validation_receipt(tmp_path / "multiple.report.json", report, "cand-1")


def test_candidate_validation_writer_rejects_missing_keyword(tmp_path):
    validator = load_validator("candidate_keyword_missing")
    report = {
        "stage": "stage6_exact",
        "status": "PASS",
        "production": True,
        "candidate_id": "cand-1",
        "complete_count": 1,
        "blocked_count": 0,
        "complete": [{"volume": 100}],
        "blocked": [],
    }

    with pytest.raises(ValueError, match="keyword"):
        validator._write_validation_receipt(tmp_path / "missing.report.json", report, "cand-1")


@pytest.mark.parametrize(
    "stage",
    ["stage6_exact", "intitle_observation", "kgr_intitle", "serp_review", "finalist_trend"],
)
def test_candidate_receipt_binds_id_and_normalized_keyword_for_every_selection_stage(tmp_path, stage, monkeypatch):
    hook = load_hook(f"candidate_binding_{stage}")
    monkeypatch.setattr(hook, "_verify_current_evidence", lambda report, current_stage: (True, ""))
    record = write_candidate_validation_artifacts(tmp_path, hook, stage, "cand-1", "  Wedding   Cost Calculator ")

    valid, reason = hook._verify_validation_receipt(record, stage, "cand-1", "wedding cost calculator")

    assert valid is True, reason


def test_candidate_receipt_with_wrong_keyword_is_rejected(tmp_path, monkeypatch):
    hook = load_hook("candidate_binding_wrong_keyword")
    monkeypatch.setattr(hook, "_verify_current_evidence", lambda report, current_stage: (True, ""))
    record = write_candidate_validation_artifacts(tmp_path, hook, "stage6_exact", "cand-1", "wedding cost calculator")

    valid, reason = hook._verify_validation_receipt(record, "stage6_exact", "cand-1", "different keyword")

    assert valid is False
    assert "keyword" in reason.lower()


def test_candidate_receipt_with_wrong_id_is_rejected_even_when_keyword_matches(tmp_path, monkeypatch):
    hook = load_hook("candidate_binding_wrong_id")
    monkeypatch.setattr(hook, "_verify_current_evidence", lambda report, current_stage: (True, ""))
    record = write_candidate_validation_artifacts(tmp_path, hook, "stage6_exact", "cand-wrong", "wedding cost calculator")

    valid, reason = hook._verify_validation_receipt(record, "stage6_exact", "cand-right", "wedding cost calculator")

    assert valid is False
    assert "candidate" in reason.lower()


def test_candidate_receipt_requires_manifest_candidate_keyword(tmp_path, monkeypatch):
    hook = load_hook("candidate_binding_missing_manifest_keyword")
    monkeypatch.setattr(hook, "_verify_validation_receipt", lambda *args, **kwargs: (True, ""))
    record = write_candidate_validation_artifacts(tmp_path, hook, "stage6_exact", "cand-1", "wedding cost calculator")
    manifest = {"candidates": {"cand-1": {}}}

    valid, reason = hook._verify_candidate_receipt(
        manifest,
        "cand-1",
        manifest["candidates"]["cand-1"],
        record,
        "stage6_exact",
    )

    assert valid is False
    assert "manifest candidate keyword" in reason.lower()


def test_global_discovery_receipt_cannot_carry_candidate_identity(tmp_path, monkeypatch):
    hook = load_hook("global_receipt_candidate_id")
    monkeypatch.setattr(hook, "_verify_current_evidence", lambda report, current_stage: (True, ""))
    record = write_candidate_validation_artifacts(tmp_path, hook, "discovery_autocomplete", "cand-1", "wedding cost calculator")

    valid, reason = hook._verify_validation_receipt(record, "discovery_autocomplete")

    assert valid is False
    assert "global" in reason.lower() or "candidate" in reason.lower()


def test_candidate_receipt_cannot_be_mounted_on_another_manifest_candidate(tmp_path, monkeypatch):
    hook = load_hook("candidate_receipt_mounted_elsewhere")
    monkeypatch.setattr(hook, "_verify_current_evidence", lambda report, current_stage: (True, ""))
    record = write_candidate_validation_artifacts(tmp_path, hook, "serp_review", "cand-a", "wedding cost calculator")

    valid, reason = hook._verify_validation_receipt(record, "serp_review", "cand-b", "wedding cost calculator")

    assert valid is False
    assert "candidate" in reason.lower()


def test_protected_candidate_command_without_marker_fails_closed(monkeypatch):
    hook = load_hook("candidate_marker_required")
    monkeypatch.setattr(hook, "_verify_validation_receipt", lambda *args, **kwargs: (True, ""))
    manifest = {
        "run_id": "r1",
        "route": "traditional",
        "status": "IN_PROGRESS",
        "stages": {},
        "candidates": {"cand-1": {"stage6_exact": {"status": "PASS"}}},
    }
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "python3 runtime/collectors/google_live_collector.py intitle --keyword example"},
    }

    assert hook.pre_tool_use(payload, manifest) == 2


@pytest.mark.parametrize(
    "stage",
    ["stage6_exact", "intitle_observation", "kgr_intitle", "serp_review", "finalist_trend"],
)
def test_direct_candidate_stage_validator_without_marker_fails_closed(stage):
    hook = load_hook(f"candidate_validator_marker_{stage}")
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": f"python3 runtime/stage_validator.py --stage {stage} --input rows.json"},
    }
    manifest = {
        "run_id": "r1",
        "route": "traditional",
        "status": "IN_PROGRESS",
        "stages": {},
        "candidates": {},
    }

    assert hook.pre_tool_use(payload, manifest) == 2


def emerging_observations(keyword="new demand", root_id="root-1", values=None):
    values = values or [("2026-08-01", 0), ("2026-08-10", 0), ("2026-08-15", 0), ("2026-08-21", 10), ("2026-08-22", 20), ("2026-08-23", 30)]
    rows = []
    for observed_at, signal_value in values:
        rows.append(
            {
                "keyword": keyword,
                "observed_at": observed_at,
                "source": "google_trends",
                "source_type": "trend_index",
                "source_url": "https://trends.google.com/trends/explore",
                "country": "US",
                "time_window": "daily",
                "signal_unit": "index_0_100",
                "metric_source": "google_trends",
                "metric_database": "US",
                "root_id": root_id,
                "signal_value": signal_value,
            }
        )
    return rows


def run_emerging_pipeline(tmp_path, rows):
    input_path = tmp_path / "observations.json"
    output_dir = tmp_path / "pipeline-output"
    input_path.write_text(json.dumps(rows), encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(PIPELINE),
            "--input",
            str(input_path),
            "--as-of",
            "2026-08-23",
            "--output-dir",
            str(output_dir),
        ],
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    return input_path, output_dir, json.loads(result.stdout)


def emerging_manifest(receipt_path, receipt, candidates):
    return {
        "run_id": "emerging-run",
        "route": "emerging",
        "status": "COMPLETE",
        "emerging_pipeline_receipt_ref": str(receipt_path),
        "route_handoff_ref": receipt["outputs"]["routed"]["path"],
        "candidates": candidates,
    }


def test_direct_fabricated_emerging_route_is_rejected(tmp_path):
    hook = load_hook("fabricated_emerging_route")
    handoff = tmp_path / "routes.json"
    handoff.write_text(
        json.dumps(
            {
                "routes": [
                    {
                        "keyword": "new demand",
                        "status": "emerging",
                        "root_relation": "existing_root",
                        "route": "selection_handoff",
                        "handoff": {
                            "keyword": "new demand",
                            "root_id": "root-1",
                            "status": "emerging",
                            "signal_type": "search_velocity",
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    manifest = emerging_manifest(tmp_path / "missing-receipt.json", {"outputs": {"routed": {"path": str(handoff)}}}, {"cand-1": {"keyword": "new demand", "root_id": "root-1", "status": "emerging"}})
    manifest["route_handoff_ref"] = str(handoff)

    valid, reason = hook._verify_route_attestation(manifest)

    assert valid is False
    assert "receipt" in reason.lower() or "pipeline" in reason.lower()


def test_route_candidates_recomputes_confirmed_status_instead_of_trusting_input(tmp_path):
    input_path = tmp_path / "classified.json"
    output_path = tmp_path / "routed.json"
    input_path.write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "keyword": "fabricated demand",
                        "status": "emerging",
                        "signal_type": "search_velocity",
                        "root_relation": "existing_root",
                        "root_id": "root-1",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(ROUTE), "--input", str(input_path), "--format", "json"],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    route = json.loads(result.stdout)["routes"][0]
    assert route["route"] != "selection_handoff"


def test_route_candidates_requires_a_real_classifier_output_for_confirmed_status(tmp_path):
    input_path = tmp_path / "classified.json"
    input_path.write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "keyword": "fabricated canonical demand",
                        "status": "emerging",
                        "signal_type": "net_new",
                        "root_relation": "existing_root",
                        "root_id": "root-1",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(ROUTE), "--input", str(input_path), "--format", "json"],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    route = json.loads(result.stdout)["routes"][0]
    assert route["route"] != "selection_handoff"


def test_complete_emerging_pipeline_receipt_is_replayed_and_allows_handoff(tmp_path):
    input_path, output_dir, receipt = run_emerging_pipeline(tmp_path, emerging_observations())
    receipt_path = output_dir / "receipt.json"
    hook = load_hook("valid_emerging_pipeline")
    routed = json.loads(Path(receipt["outputs"]["routed"]["path"]).read_text(encoding="utf-8"))
    assert routed["routes"][0]["route"] == "selection_handoff"
    manifest = emerging_manifest(
        receipt_path,
        receipt,
        {"cand-1": {"keyword": " NEW   DEMAND ", "root_id": "root-1", "status": "emerging"}},
    )

    valid, reason = hook._verify_route_attestation(manifest)

    assert valid is True, reason
    assert input_path.exists()


def test_emerging_pipeline_input_hash_tampering_is_rejected(tmp_path):
    input_path, output_dir, receipt = run_emerging_pipeline(tmp_path, emerging_observations())
    input_path.write_text(json.dumps(emerging_observations(values=[("2026-08-23", 99)])), encoding="utf-8")
    hook = load_hook("emerging_input_hash")
    manifest = emerging_manifest(
        output_dir / "receipt.json",
        receipt,
        {"cand-1": {"keyword": "new demand", "root_id": "root-1", "status": "emerging"}},
    )

    valid, reason = hook._verify_route_attestation(manifest)

    assert valid is False
    assert "hash" in reason.lower()


def test_emerging_pipeline_output_hash_tampering_is_rejected(tmp_path):
    _, output_dir, receipt = run_emerging_pipeline(tmp_path, emerging_observations())
    routed_path = Path(receipt["outputs"]["routed"]["path"])
    routed_path.write_text(routed_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    hook = load_hook("emerging_output_hash")
    manifest = emerging_manifest(
        output_dir / "receipt.json",
        receipt,
        {"cand-1": {"keyword": "new demand", "root_id": "root-1", "status": "emerging"}},
    )

    valid, reason = hook._verify_route_attestation(manifest)

    assert valid is False
    assert "hash" in reason.lower()


@pytest.mark.parametrize("field", ["scripts", "scripts_birth_history", "thresholds"])
def test_emerging_pipeline_receipt_rejects_changed_source_hash(tmp_path, field):
    _, output_dir, receipt = run_emerging_pipeline(tmp_path, emerging_observations())
    if field == "scripts":
        receipt["scripts"]["route_candidates.py"]["sha256"] = "0" * 64
    elif field == "scripts_birth_history":
        # birth_history.py drives the estimated birth window, so it must be bound
        # by the pipeline receipt exactly like every other aggregation script.
        receipt["scripts"]["birth_history.py"]["sha256"] = "0" * 64
    else:
        receipt["thresholds"]["sha256"] = "0" * 64
    receipt_path = output_dir / "receipt-tampered.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    hook = load_hook(f"emerging_{field}_hash")
    manifest = emerging_manifest(
        receipt_path,
        receipt,
        {"cand-1": {"keyword": "new demand", "root_id": "root-1", "status": "emerging"}},
    )

    valid, reason = hook._verify_route_attestation(manifest)

    assert valid is False
    assert "hash" in reason.lower()


def test_complete_emerging_pipeline_no_handoff_is_preserved_without_fabrication(tmp_path):
    _, output_dir, receipt = run_emerging_pipeline(
        tmp_path,
        emerging_observations(keyword="not enough evidence", values=[("2026-08-23", 0)]),
    )
    routed = json.loads(Path(receipt["outputs"]["routed"]["path"]).read_text(encoding="utf-8"))
    assert routed["routes"][0]["route"] == "no_handoff"
    hook = load_hook("valid_emerging_no_handoff")
    manifest = emerging_manifest(output_dir / "receipt.json", receipt, {})

    valid, reason = hook._verify_route_attestation(manifest)

    assert valid is True, reason


@pytest.mark.parametrize(
    "candidate",
    [
        {"keyword": "different demand", "root_id": "root-1", "status": "emerging"},
        {"keyword": "new demand", "root_id": "root-2", "status": "emerging"},
        {"keyword": "new demand", "root_id": "root-1", "status": "breakout"},
    ],
)
def test_emerging_handoff_must_match_manifest_candidate_identity(tmp_path, candidate):
    _, output_dir, receipt = run_emerging_pipeline(tmp_path, emerging_observations())
    hook = load_hook(f"emerging_candidate_mismatch_{abs(hash(json.dumps(candidate, sort_keys=True)))}")
    manifest = emerging_manifest(output_dir / "receipt.json", receipt, {"cand-1": candidate})

    valid, reason = hook._verify_route_attestation(manifest)

    assert valid is False
    assert "candidate" in reason.lower() or "handoff" in reason.lower() or "match" in reason.lower()
