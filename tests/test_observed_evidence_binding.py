import hashlib
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
BINDING = ROOT / "runtime" / "evidence_binding.py"
MERGER = ROOT / "runtime" / "kgr_evidence_merge.py"


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


def _bind_output(tmp_path, name, payload, collector, evidence_type):
    binding = load_module(f"binding_{name}", BINDING)
    artifact = tmp_path / f"{name}.artifact.json"
    artifact.write_text(json.dumps({"real_test_artifact": name}), encoding="utf-8")
    output = tmp_path / f"{name}.json"
    bound = binding.write_observed_output(output, payload, collector, evidence_type, [artifact])
    return output, bound, artifact


def _run_production_validation(tmp_path, stage, input_path, candidate_id=None):
    report = tmp_path / f"{stage}.report.json"
    cmd = [sys.executable, str(VALIDATOR), "--stage", stage, "--input", str(input_path), "--report", str(report), "--production"]
    if candidate_id:
        cmd += ["--candidate-id", candidate_id]
    proc = subprocess.run(cmd, text=True, capture_output=True)
    return proc, report


def test_hand_written_observed_fields_cannot_pass_production_validation(tmp_path):
    input_path = tmp_path / "fake.json"
    input_path.write_text(json.dumps(fake_exact_row()), encoding="utf-8")
    proc, report_path = _run_production_validation(tmp_path, "stage6_exact", input_path)
    assert proc.returncode == 2
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["blocked_count"] == 1
    assert any("evidence" in err.lower() or "receipt" in err.lower() for err in report["blocked"][0]["errors"])


def test_collector_bound_exact_passes_production_validation(tmp_path):
    row = fake_exact_row()
    row["provenance_ref"] = str(tmp_path / "exact.artifact.json")
    output, bound, _ = _bind_output(tmp_path, "exact", row, "semrush_relay_collector", "semrush_exact")
    proc, report_path = _run_production_validation(tmp_path, "stage6_exact", output, candidate_id="cand-1")
    assert proc.returncode == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "PASS"
    assert report["production"] is True
    assert report["candidate_id"] == "cand-1"
    assert Path(report["validation_receipt_ref"]).is_file()
    assert bound["evidence_receipt_ref"]


def test_tampering_normalized_output_after_receipt_is_blocked(tmp_path):
    row = fake_exact_row()
    row["provenance_ref"] = str(tmp_path / "exact.artifact.json")
    output, bound, _ = _bind_output(tmp_path, "exact", row, "semrush_relay_collector", "semrush_exact")
    bound["volume"] = 999999
    output.write_text(json.dumps(bound), encoding="utf-8")
    proc, _ = _run_production_validation(tmp_path, "stage6_exact", output)
    assert proc.returncode == 2
    assert "hash mismatch" in proc.stderr.lower() or "evidence" in proc.stderr.lower()


def test_tampering_evidence_artifact_after_receipt_is_blocked(tmp_path):
    row = fake_exact_row()
    row["provenance_ref"] = str(tmp_path / "exact.artifact.json")
    output, _, artifact = _bind_output(tmp_path, "exact", row, "semrush_relay_collector", "semrush_exact")
    artifact.write_text("tampered", encoding="utf-8")
    proc, _ = _run_production_validation(tmp_path, "stage6_exact", output)
    assert proc.returncode == 2
    assert "hash mismatch" in proc.stderr.lower() or "evidence" in proc.stderr.lower()


def test_evaluator_does_not_call_hand_written_metadata_verified():
    evaluator = load_module("evaluate_candidates_binding", EVALUATOR)
    row = dict(fake_exact_row(), intitle_results=50)
    evaluated = evaluator.normalize(row, "final")
    assert evaluated["provenance_status"] == "unverified"


def test_evaluator_calls_bound_exact_verified(tmp_path):
    evaluator = load_module("evaluate_candidates_verified", EVALUATOR)
    row = fake_exact_row()
    row["provenance_ref"] = str(tmp_path / "exact.artifact.json")
    _, bound, _ = _bind_output(tmp_path, "exact", row, "semrush_relay_collector", "semrush_exact")
    evaluated = evaluator.normalize(bound, "exact")
    assert evaluated["provenance_status"] == "verified"


def test_hook_does_not_trust_bare_manifest_pass(tmp_path):
    manifest_path = tmp_path / "active.json"
    manifest_path.write_text(json.dumps({"run_id": "r1", "status": "IN_PROGRESS", "stages": {"stage6_exact": {"status": "PASS"}}}), encoding="utf-8")
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "python3 skills/seo-keyword-selection/scripts/evaluate_candidates.py --input rows.json --stage exact"},
    }
    env = dict(os.environ, SEO_RUN_MANIFEST=str(manifest_path))
    proc = subprocess.run([sys.executable, str(HOOK), "pre"], input=json.dumps(payload), text=True, capture_output=True, env=env)
    assert proc.returncode == 2
    assert "validation receipt" in proc.stderr.lower()


def test_hook_accepts_hash_verified_production_validation_receipt(tmp_path):
    row = fake_exact_row()
    row["provenance_ref"] = str(tmp_path / "exact.artifact.json")
    output, _, _ = _bind_output(tmp_path, "exact", row, "semrush_relay_collector", "semrush_exact")
    proc, report_path = _run_production_validation(tmp_path, "stage6_exact", output)
    assert proc.returncode == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    manifest_path = tmp_path / "active.json"
    manifest_path.write_text(json.dumps({
        "run_id": "r1",
        "status": "IN_PROGRESS",
        "stages": {"stage6_exact": {"status": "PASS", "validation_receipt_ref": report["validation_receipt_ref"]}},
    }), encoding="utf-8")
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "python3 skills/seo-keyword-selection/scripts/evaluate_candidates.py --input rows.json --stage exact"},
    }
    env = dict(os.environ, SEO_RUN_MANIFEST=str(manifest_path))
    hook = subprocess.run([sys.executable, str(HOOK), "pre"], input=json.dumps(payload), text=True, capture_output=True, env=env)
    assert hook.returncode == 0


def test_kgr_cli_rejects_hand_written_exact_and_intitle(tmp_path):
    exact_path = tmp_path / "exact.json"
    intitle_path = tmp_path / "intitle.json"
    exact_path.write_text(json.dumps(fake_exact_row()), encoding="utf-8")
    intitle_path.write_text(json.dumps({
        "keyword": "fabricated keyword", "intitle_results": 50, "source": "Google", "market": "US",
        "observed_at": "2026-08-27T00:01:00Z", "evidence_ref": "fake.png"
    }), encoding="utf-8")
    proc = subprocess.run([
        sys.executable, str(MERGER), "--exact", str(exact_path), "--intitle", str(intitle_path), "--output", str(tmp_path / "merged.json")
    ], text=True, capture_output=True)
    assert proc.returncode == 2
    assert "receipt" in proc.stderr.lower() or "evidence" in proc.stderr.lower()
