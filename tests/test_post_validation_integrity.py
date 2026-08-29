import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "runtime" / "codex_stage_hook.py"
VALIDATOR = ROOT / "runtime" / "stage_validator.py"


def load_hook(name):
    spec = importlib.util.spec_from_file_location(name, HOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_hook(tmp_path, mode, payload, manifest):
    manifest_path = tmp_path / "active.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    env = dict(os.environ, SEO_RUN_MANIFEST=str(manifest_path))
    return subprocess.run(
        [sys.executable, str(HOOK), mode],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env=env,
    )


def make_structural_validation_receipt(tmp_path, stage="stage6_exact"):
    report = tmp_path / "stage.report.json"
    receipt = tmp_path / "stage.report.receipt.json"
    report_data = {
        "stage": stage,
        "status": "PASS",
        "production": True,
        "candidate_id": None,
        "complete_count": 1,
        "blocked_count": 0,
        "complete": [{"synthetic_unit_row": True}],
        "blocked": [],
        "validation_receipt_ref": str(receipt),
    }
    report.write_text(json.dumps(report_data), encoding="utf-8")
    receipt.write_text(json.dumps({
        "schema": "seo-stage-validation/v1",
        "stage": stage,
        "status": "PASS",
        "candidate_id": None,
        "validator_source_sha256": hashlib.sha256(VALIDATOR.read_bytes()).hexdigest(),
        "report_ref": str(report),
        "report_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
    }), encoding="utf-8")
    return {"status": "PASS", "validation_receipt_ref": str(receipt)}


def test_validation_receipt_path_rechecks_current_underlying_evidence(monkeypatch, tmp_path):
    hook = load_hook("post_validation_recheck_unit")
    record = make_structural_validation_receipt(tmp_path)
    monkeypatch.setattr(hook, "_verify_current_evidence", lambda report, stage: (False, "underlying evidence invalid: tampered"))
    valid, reason = hook._verify_validation_receipt(record, "stage6_exact")
    assert valid is False
    assert "underlying evidence" in reason.lower()


def test_validation_receipt_rejects_wrong_validator_source_hash(tmp_path):
    hook = load_hook("post_validation_source_hash")
    record = make_structural_validation_receipt(tmp_path)
    receipt_path = Path(record["validation_receipt_ref"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["validator_source_sha256"] = "0" * 64
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    valid, reason = hook._verify_validation_receipt(record, "stage6_exact")
    assert valid is False
    assert "validator source hash" in reason.lower()


def test_stop_rejects_bare_complete_status(tmp_path):
    manifest = {
        "run_id": "r1",
        "route": "traditional",
        "status": "COMPLETE",
        "stages": {},
    }
    payload = {"hook_event_name": "Stop", "stop_hook_active": False, "last_assistant_message": "done"}
    proc = run_hook(tmp_path, "stop", payload, manifest)
    assert proc.returncode == 2
    assert "complete" in proc.stderr.lower() or "required" in proc.stderr.lower()


def test_complete_control_flow_allows_valid_candidate_lifecycle_when_verifiers_pass(monkeypatch):
    hook = load_hook("complete_control_flow_unit")
    monkeypatch.setattr(hook, "_verify_validation_receipt", lambda *args, **kwargs: (True, ""))
    monkeypatch.setattr(hook, "_verified_exact_disposition", lambda *args, **kwargs: ("do_candidate", ""))
    monkeypatch.setattr(hook, "_verify_finalist_disposition", lambda *args, **kwargs: (False, ""))
    manifest = {
        "run_id": "r1",
        "route": "traditional",
        "status": "COMPLETE",
        "stages": {
            "discovery_autocomplete": {"status": "PASS"},
            "discovery_handoff": {"status": "PASS"},
        },
        "candidates": {
            "candidate-1": {
                "keyword": "candidate keyword",
                "stage6_exact": {"status": "PASS"},
                "intitle_observation": {"status": "PASS"},
                "kgr_intitle": {"status": "PASS"},
                "serp_review": {"status": "PASS"},
            }
        },
    }
    valid, reason = hook._verify_completion_requirements(manifest)
    assert valid is True, reason
