import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "runtime" / "stage_validator.py"
HOOK = ROOT / "runtime" / "codex_stage_hook.py"
EVALUATOR = ROOT / "skills" / "seo-keyword-selection" / "scripts" / "evaluate_candidates.py"
BINDING = ROOT / "runtime" / "evidence_binding.py"
MERGER = ROOT / "runtime" / "kgr_evidence_merge.py"
SEMRUSH = ROOT / "runtime" / "collectors" / "semrush_relay_collector.py"


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


def test_evaluator_does_not_call_hand_written_metadata_verified():
    evaluator = load_module("evaluate_candidates_binding", EVALUATOR)
    row = dict(fake_exact_row(), intitle_results=50)
    evaluated = evaluator.normalize(row, "final")
    assert evaluated["provenance_status"] == "unverified"


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


def test_direct_self_minted_semrush_receipt_writer_is_rejected(tmp_path):
    binding = load_module("binding_self_mint_semrush", BINDING)
    raw = tmp_path / "forged.raw.json"
    capture = tmp_path / "forged.capture.json"
    raw.write_text(json.dumps({"response": {"result": {"keywords": []}}}), encoding="utf-8")
    capture.write_text(json.dumps({"captured": True}), encoding="utf-8")
    try:
        binding.write_observed_output(
            tmp_path / "forged.json",
            fake_exact_row(),
            "semrush_relay_collector",
            "semrush_exact",
            [
                {"path": raw, "role": "relay_raw_response"},
                {"path": capture, "role": "current_network_capture"},
            ],
        )
    except binding.EvidenceIntegrityError as exc:
        assert "collector" in str(exc).lower() or "mint" in str(exc).lower()
    else:
        raise AssertionError("generic helper must not mint production Semrush receipts")


def test_direct_self_minted_google_receipt_writer_is_rejected(tmp_path):
    binding = load_module("binding_self_mint_google", BINDING)
    screenshot = tmp_path / "fake.png"
    observation = tmp_path / "fake-observation.json"
    screenshot.write_bytes(b"not-a-real-screenshot")
    observation.write_text(json.dumps({"page_url": "https://www.google.com/"}), encoding="utf-8")
    try:
        binding.write_observed_output(
            tmp_path / "fake-intitle.json",
            {"keyword": "fabricated", "intitle_results": 50, "source": "Google", "market": "US"},
            "google_live_collector",
            "google_intitle",
            [
                {"path": screenshot, "role": "screenshot"},
                {"path": observation, "role": "structured_observation"},
            ],
        )
    except binding.EvidenceIntegrityError as exc:
        assert "collector" in str(exc).lower() or "mint" in str(exc).lower()
    else:
        raise AssertionError("generic helper must not mint production Google receipts")


def test_imported_monkeypatched_collector_main_cannot_mint_production_receipt(tmp_path, monkeypatch):
    semrush = load_module("semrush_imported_attack", SEMRUSH)
    observed_at = datetime.now(timezone.utc).isoformat()
    capture = tmp_path / "capture.json"
    capture.write_text(json.dumps({"fake_capture": True}), encoding="utf-8")
    descriptor = tmp_path / "request.json"
    descriptor.write_text(json.dumps({
        "path": "/api/exact",
        "method": "POST",
        "body": {},
        "capture_observed_at": observed_at,
        "capture_evidence_ref": str(capture),
        "mode": "exact",
        "metric_database": "us",
        "keyword": "fabricated keyword",
    }), encoding="utf-8")
    output = tmp_path / "out.json"
    raw_output = tmp_path / "out.raw.json"

    class Dummy:
        def close(self):
            pass
        def stop(self):
            pass

    monkeypatch.setattr(semrush, "connect_same_origin", lambda: (Dummy(), Dummy(), object()))

    def fake_collect(_page, loaded, raw_evidence_ref=None, raw_output_path=None):
        response = {"result": {"keywords": [{
            "phrase": "fabricated keyword", "database": "us", "volume": 1000,
            "difficulty": 20, "cpc": 0.2, "intents": ["commercial"],
            "competition_level": "low", "trend": [50] * 12,
        }]}}
        Path(raw_output_path).write_text(json.dumps({
            "observed_at": observed_at,
            "relay_origin": "https://sem.3ue.com/",
            "request_method": loaded["method"],
            "request_path": loaded["path"],
            "capture_observed_at": loaded["capture_observed_at"],
            "capture_evidence_ref": loaded["capture_evidence_ref"],
            "mode": "exact",
            "metric_database": "us",
            "keyword": "fabricated keyword",
            "response": response,
        }), encoding="utf-8")
        return semrush.normalize_exact(response, loaded, observed_at, str(raw_output_path))

    monkeypatch.setattr(semrush, "collect", fake_collect)
    old_argv = sys.argv[:]
    try:
        sys.argv = [str(SEMRUSH), "--request", str(descriptor), "--output", str(output), "--raw-output", str(raw_output)]
        rc = semrush.main()
    finally:
        sys.argv = old_argv
    assert rc == 2
    assert not output.with_suffix(".receipt.json").exists()


def test_semrush_replay_detects_raw_normalized_mismatch_even_when_hash_layer_is_not_involved(tmp_path):
    binding = load_module("binding_semantic_replay", BINDING)
    raw = tmp_path / "raw.json"
    capture = tmp_path / "capture.json"
    capture.write_text(json.dumps({"capture": True}), encoding="utf-8")
    raw.write_text(json.dumps({
        "observed_at": "2026-08-27T00:00:00Z",
        "relay_origin": "https://sem.3ue.com/",
        "request_method": "POST",
        "request_path": "/api/exact",
        "capture_observed_at": "2026-08-27T00:00:00Z",
        "capture_evidence_ref": str(capture),
        "mode": "exact",
        "metric_database": "us",
        "keyword": "fabricated keyword",
        "response": {"result": {"keywords": [{
            "phrase": "fabricated keyword", "database": "us", "volume": 999,
            "difficulty": 20, "cpc": 0.2, "intents": ["commercial"],
            "competition_level": "low", "trend": [50] * 12,
        }]}},
    }), encoding="utf-8")
    normalized = fake_exact_row()
    normalized["provenance_ref"] = str(raw)
    try:
        binding._verify_semrush_semantics("semrush_exact", normalized, {
            "relay_raw_response": raw,
            "current_network_capture": capture,
        })
    except binding.EvidenceIntegrityError as exc:
        assert "replay" in str(exc).lower() or "differs" in str(exc).lower()
    else:
        raise AssertionError("raw/normalized mismatch must fail deterministic replay")


def test_collector_artifact_role_contracts_fail_closed(tmp_path):
    binding = load_module("binding_roles", BINDING)
    artifact = tmp_path / "artifact.json"
    artifact.write_text("{}", encoding="utf-8")
    try:
        binding._artifact_records([{"path": artifact, "role": "relay_raw_response"}], "semrush_exact")
    except binding.EvidenceIntegrityError as exc:
        assert "roles" in str(exc).lower()
    else:
        raise AssertionError("Semrush evidence without current_network_capture must fail")
