import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "runtime" / "codex_stage_hook.py"
VALIDATOR = ROOT / "runtime" / "stage_validator.py"


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


def make_exact_production_validation(tmp_path):
    sys.path.insert(0, str(ROOT / "runtime"))
    import evidence_binding

    artifact = tmp_path / "relay.raw.json"
    artifact.write_text(json.dumps({"response": {"real": True}}), encoding="utf-8")
    output = tmp_path / "exact.json"
    payload = {
        "keyword": "wedding calculator",
        "volume": 1000,
        "kd": 20,
        "cpc": 0.2,
        "intent": ["commercial"],
        "competition_level": "low",
        "trend": [50] * 12,
        "metric_source": "Semrush",
        "metric_database": "us",
        "metric_stage": "exact",
        "observed_at": "2026-08-27T03:00:00Z",
        "relay_origin": "https://sem.3ue.com/",
        "provenance_ref": str(artifact),
    }
    bound = evidence_binding.write_observed_output(
        output,
        payload,
        "semrush_relay_collector",
        "semrush_exact",
        [{"path": str(artifact), "role": "raw_relay_response"}],
    )
    report = tmp_path / "stage6.report.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            "--stage", "stage6_exact",
            "--input", str(output),
            "--report", str(report),
            "--production",
        ],
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stderr
    report_data = json.loads(report.read_text(encoding="utf-8"))
    return artifact, bound, report_data["validation_receipt_ref"]


def test_hook_rejects_stage_when_evidence_is_tampered_after_validation(tmp_path):
    artifact, _bound, validation_receipt_ref = make_exact_production_validation(tmp_path)
    manifest = {
        "run_id": "r1",
        "status": "IN_PROGRESS",
        "stages": {
            "stage6_exact": {
                "status": "PASS",
                "validation_receipt_ref": validation_receipt_ref,
            }
        },
    }
    artifact.write_text(json.dumps({"response": {"fabricated_after_validation": True}}), encoding="utf-8")
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {
            "command": "python3 skills/seo-keyword-selection/scripts/evaluate_candidates.py --input rows.json --stage exact"
        },
    }
    proc = run_hook(tmp_path, "pre", payload, manifest)
    assert proc.returncode == 2
    assert "evidence" in proc.stderr.lower() or "receipt" in proc.stderr.lower()


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
    assert "complete" in proc.stderr.lower() or "require" in proc.stderr.lower()


def test_stop_allows_complete_when_declared_requirements_have_valid_receipts(tmp_path):
    _artifact, _bound, validation_receipt_ref = make_exact_production_validation(tmp_path)
    manifest = {
        "run_id": "r1",
        "route": "emerging",
        "status": "COMPLETE",
        "completion_requirements": [
            {"stage": "stage6_exact"}
        ],
        "stages": {
            "stage6_exact": {
                "status": "PASS",
                "validation_receipt_ref": validation_receipt_ref,
            }
        },
    }
    payload = {"hook_event_name": "Stop", "stop_hook_active": False, "last_assistant_message": "done"}
    proc = run_hook(tmp_path, "stop", payload, manifest)
    assert proc.returncode == 0, proc.stderr
