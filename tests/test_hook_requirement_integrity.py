import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "runtime" / "codex_stage_hook.py"


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
    receipt.write_text(json.dumps({
        "schema": "seo-stage-validation/v1",
        "stage": stage,
        "status": "PASS",
        "candidate_id": None,
        "report_ref": str(report),
        "report_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
    }), encoding="utf-8")
    return str(receipt)


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
        "completion_requirements": [{"stage": "fake_stage"}],
        "stages": {"fake_stage": {"status": "PASS", "validation_receipt_ref": fake_receipt}},
    }
    payload = {"hook_event_name": "Stop", "stop_hook_active": False, "last_assistant_message": "done"}
    proc = run_hook(tmp_path, "stop", payload, manifest)
    assert proc.returncode == 2
    assert "unknown" in proc.stderr.lower() or "require" in proc.stderr.lower()


def test_complete_must_include_route_minimum_stage6_exact(tmp_path):
    handoff_receipt = fake_stage_receipt(tmp_path, "discovery_handoff")
    manifest = {
        "run_id": "r3",
        "route": "traditional",
        "status": "COMPLETE",
        "completion_requirements": [{"stage": "discovery_handoff"}],
        "stages": {"discovery_handoff": {"status": "PASS", "validation_receipt_ref": handoff_receipt}},
    }
    payload = {"hook_event_name": "Stop", "stop_hook_active": False, "last_assistant_message": "done"}
    proc = run_hook(tmp_path, "stop", payload, manifest)
    assert proc.returncode == 2
    assert "stage6_exact" in proc.stderr.lower() or "minimum" in proc.stderr.lower()
