import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "runtime" / "codex_stage_hook.py"
TEST_ISSUANCE_SECRET = "test-hook-requirement-secret-for-unit-tests"


def fake_stage_receipt(tmp_path, stage):
    report = tmp_path / f"{stage}.report.json"
    receipt = tmp_path / f"{stage}.report.receipt.json"
    report_data = {
        "stage": stage,
        "status": "PASS",
        "production": True,
        "candidate_id": None,
        "complete_count": 1,
        "blocked_count": 0,
        "complete": [{"synthetic": True}],
        "blocked": [],
        "validation_receipt_ref": str(receipt),
    }
    report.write_text(json.dumps(report_data), encoding="utf-8")
    report_sha = hashlib.sha256(report.read_bytes()).hexdigest()
    old_secret = os.environ.get("SEO_ISSUANCE_SECRET")
    os.environ["SEO_ISSUANCE_SECRET"] = TEST_ISSUANCE_SECRET
    try:
        spec = importlib.util.spec_from_file_location("binding_tmp", ROOT / "runtime" / "evidence_binding.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        issuance = mod._mint_issuance_proof("stage_validator", stage, report_sha, "2026-08-27T00:00:00Z")
    finally:
        if old_secret is None:
            os.environ.pop("SEO_ISSUANCE_SECRET", None)
        else:
            os.environ["SEO_ISSUANCE_SECRET"] = old_secret
    receipt.write_text(json.dumps({
        "schema": "seo-stage-validation/v1",
        "stage": stage,
        "status": "PASS",
        "candidate_id": None,
        "report_ref": str(report),
        "report_sha256": report_sha,
        "issuance": issuance,
    }), encoding="utf-8")
    return str(receipt)


def run_hook(tmp_path, mode, payload, manifest):
    manifest_path = tmp_path / "active.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    env = dict(os.environ, SEO_RUN_MANIFEST=str(manifest_path), SEO_ISSUANCE_SECRET=TEST_ISSUANCE_SECRET)
    return subprocess.run(
        [sys.executable, str(HOOK), mode],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env=env,
    )


def test_explicit_fake_marker_cannot_override_protected_inferred_stage(tmp_path):
    fake_receipt = fake_stage_receipt(tmp_path, "fake_stage")
    manifest = {
        "run_id": "r1",
        "route": "traditional",
        "status": "IN_PROGRESS",
        "stages": {
            "fake_stage": {"status": "PASS", "validation_receipt_ref": fake_receipt},
            "stage6_exact": {"status": "BLOCKED", "blocked_reason": "real Exact evidence missing"},
        },
    }
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {
            "command": "SEO_STAGE_REQUIRE=fake_stage python3 skills/seo-keyword-selection/scripts/evaluate_candidates.py --input rows.json --stage exact"
        },
    }
    proc = run_hook(tmp_path, "pre", payload, manifest)
    assert proc.returncode == 2
    assert "stage6_exact" in proc.stderr


def test_complete_cannot_use_unknown_fake_requirement(tmp_path):
    fake_receipt = fake_stage_receipt(tmp_path, "fake_stage")
    manifest = {
        "run_id": "r2",
        "route": "traditional",
        "status": "COMPLETE",
        "stages": {"fake_stage": {"status": "PASS", "validation_receipt_ref": fake_receipt}},
    }
    payload = {"hook_event_name": "Stop", "stop_hook_active": False, "last_assistant_message": "done"}
    proc = run_hook(tmp_path, "stop", payload, manifest)
    assert proc.returncode == 2
    assert "system required stage" in proc.stderr.lower() or "cannot be complete" in proc.stderr.lower()


def test_traditional_route_only_autocomplete_and_exact_is_denied(tmp_path):
    auto_receipt = fake_stage_receipt(tmp_path, "discovery_autocomplete")
    handoff_receipt = fake_stage_receipt(tmp_path, "discovery_handoff")
    exact_receipt = fake_stage_receipt(tmp_path, "stage6_exact")
    manifest = {
        "run_id": "r_trad_partial",
        "route": "traditional",
        "status": "COMPLETE",
        "stages": {
            "discovery_autocomplete": {"status": "PASS", "validation_receipt_ref": auto_receipt},
            "discovery_handoff": {"status": "PASS", "validation_receipt_ref": handoff_receipt},
            "stage6_exact": {"status": "PASS", "validation_receipt_ref": exact_receipt},
        },
    }
    payload = {"hook_event_name": "Stop", "stop_hook_active": False, "last_assistant_message": "done"}
    proc = run_hook(tmp_path, "stop", payload, manifest)
    assert proc.returncode == 2
    assert "intitle_observation" in proc.stderr or "kgr_intitle" in proc.stderr or "serp_review" in proc.stderr


def test_emerging_route_only_exact_is_denied(tmp_path):
    exact_receipt = fake_stage_receipt(tmp_path, "stage6_exact")
    manifest = {
        "run_id": "r_emerg_partial",
        "route": "emerging",
        "status": "COMPLETE",
        "stages": {
            "stage6_exact": {"status": "PASS", "validation_receipt_ref": exact_receipt},
        },
    }
    payload = {"hook_event_name": "Stop", "stop_hook_active": False, "last_assistant_message": "done"}
    proc = run_hook(tmp_path, "stop", payload, manifest)
    assert proc.returncode == 2
    assert "intitle_observation" in proc.stderr or "kgr_intitle" in proc.stderr or "finalist_trend" in proc.stderr


def test_finalist_without_trends_is_denied(tmp_path):
    auto_receipt = fake_stage_receipt(tmp_path, "discovery_autocomplete")
    handoff_receipt = fake_stage_receipt(tmp_path, "discovery_handoff")
    exact_receipt = fake_stage_receipt(tmp_path, "stage6_exact")
    intitle_receipt = fake_stage_receipt(tmp_path, "intitle_observation")
    kgr_receipt = fake_stage_receipt(tmp_path, "kgr_intitle")
    serp_receipt = fake_stage_receipt(tmp_path, "serp_review")
    manifest = {
        "run_id": "r_trad_finalist_missing_trends",
        "route": "traditional",
        "status": "COMPLETE",
        "candidates": {
            "cand_1": {"is_finalist": True}
        },
        "stages": {
            "discovery_autocomplete": {"status": "PASS", "validation_receipt_ref": auto_receipt},
            "discovery_handoff": {"status": "PASS", "validation_receipt_ref": handoff_receipt},
            "stage6_exact": {"status": "PASS", "validation_receipt_ref": exact_receipt},
            "intitle_observation": {"status": "PASS", "validation_receipt_ref": intitle_receipt},
            "kgr_intitle": {"status": "PASS", "validation_receipt_ref": kgr_receipt},
            "serp_review": {"status": "PASS", "validation_receipt_ref": serp_receipt},
            # Missing finalist_trend
        },
    }
    payload = {"hook_event_name": "Stop", "stop_hook_active": False, "last_assistant_message": "done"}
    proc = run_hook(tmp_path, "stop", payload, manifest)
    assert proc.returncode == 2
    assert "finalist_trend" in proc.stderr
