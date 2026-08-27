import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "runtime" / "stage_validator.py"
HOOK = ROOT / "runtime" / "codex_stage_hook.py"
EVALUATOR = ROOT / "skills" / "seo-keyword-selection" / "scripts" / "evaluate_candidates.py"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fake_exact_row():
    return {
        "keyword": "fabricated keyword",
        "volume": 1000,
        "kd": 20,
        "cpc": 0.2,
        "intent": ["commercial"],
        "competition_level": "low",
        "trend": [50] * 12,
        "metric_source": "Semrush",
        "metric_database": "us",
        "metric_stage": "exact",
        "observed_at": "2026-08-27T00:00:00Z",
        "relay_origin": "https://sem.3ue.com/",
        "provenance_ref": "evidence/nonexistent.raw.json",
    }


def test_hand_written_observed_fields_cannot_pass_production_validation(tmp_path):
    input_path = tmp_path / "fake.json"
    report_path = tmp_path / "report.json"
    input_path.write_text(json.dumps(fake_exact_row()), encoding="utf-8")
    proc = subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            "--stage",
            "stage6_exact",
            "--input",
            str(input_path),
            "--report",
            str(report_path),
            "--production",
        ],
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 2
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["blocked_count"] == 1
    assert any("evidence" in err.lower() or "receipt" in err.lower() for err in report["blocked"][0]["errors"])


def test_evaluator_does_not_call_hand_written_metadata_verified():
    evaluator = load_module("evaluate_candidates_binding", EVALUATOR)
    row = dict(fake_exact_row(), intitle_results=50)
    evaluated = evaluator.normalize(row, "final")
    assert evaluated["provenance_status"] != "verified"


def test_hook_does_not_trust_bare_manifest_pass(tmp_path):
    manifest_path = tmp_path / "active.json"
    manifest_path.write_text(
        json.dumps({
            "run_id": "r1",
            "status": "IN_PROGRESS",
            "stages": {"stage6_exact": {"status": "PASS"}},
        }),
        encoding="utf-8",
    )
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {
            "command": "python3 skills/seo-keyword-selection/scripts/evaluate_candidates.py --input rows.json --stage exact"
        },
    }
    env = dict(os.environ, SEO_RUN_MANIFEST=str(manifest_path))
    proc = subprocess.run(
        [sys.executable, str(HOOK), "pre"],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env=env,
    )
    assert proc.returncode == 2
    assert "validation" in proc.stderr.lower() or "receipt" in proc.stderr.lower()
