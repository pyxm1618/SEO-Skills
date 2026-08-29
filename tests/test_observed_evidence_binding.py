import hashlib
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
        assert "collector" in str(exc).lower() or "written" in str(exc).lower()
    else:
        raise AssertionError("generic helper must not write production Semrush receipts")


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
        assert "collector" in str(exc).lower() or "written" in str(exc).lower()
    else:
        raise AssertionError("generic helper must not write production Google receipts")


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


def test_self_consistent_semrush_receipt_passes_structural_replay_scope(tmp_path):
    raw = tmp_path / "raw.json"
    capture = tmp_path / "capture.json"
    capture.write_text(json.dumps({"captured": True}), encoding="utf-8")
    raw_data = {
        "observed_at": "2026-08-27T00:00:00Z",
        "relay_origin": "https://sem.3ue.com/",
        "request_method": "POST",
        "request_path": "/api/exact",
        "capture_observed_at": "2026-08-27T00:00:00Z",
        "capture_evidence_ref": str(capture),
        "mode": "exact",
        "metric_database": "us",
        "keyword": "wedding calculator",
        "response": {"result": {"keywords": [{
            "phrase": "wedding calculator", "database": "us", "volume": 1000,
            "difficulty": 20, "cpc": 0.2, "intents": ["commercial"],
            "competition_level": "low", "trend": [50] * 12,
        }]}},
    }
    raw.write_text(json.dumps(raw_data), encoding="utf-8")
    norm_path = tmp_path / "norm.json"
    receipt_path = tmp_path / "norm.receipt.json"
    norm_data = {
        "keyword": "wedding calculator", "volume": 1000, "kd": 20, "cpc": 0.2,
        "intent": ["commercial"], "competition_level": "low", "trend": [50] * 12,
        "metric_source": "Semrush", "metric_database": "us", "metric_stage": "exact",
        "observed_at": "2026-08-27T00:00:00Z", "relay_origin": "https://sem.3ue.com/",
        "provenance_ref": str(raw), "evidence_receipt_ref": str(receipt_path),
    }
    norm_path.write_text(json.dumps(norm_data), encoding="utf-8")
    receipt_data = {
        "schema": "seo-observed-evidence/v2",
        "collector": "semrush_relay_collector",
        "collector_source_sha256": hashlib.sha256((ROOT / "runtime" / "collectors" / "semrush_relay_collector.py").read_bytes()).hexdigest(),
        "evidence_type": "semrush_exact",
        "normalized_ref": str(norm_path),
        "normalized_sha256": hashlib.sha256(norm_path.read_bytes()).hexdigest(),
        "artifacts": [
            {"role": "relay_raw_response", "path": str(raw), "sha256": hashlib.sha256(raw.read_bytes()).hexdigest()},
            {"role": "current_network_capture", "path": str(capture), "sha256": hashlib.sha256(capture.read_bytes()).hexdigest()},
        ],
    }
    receipt_path.write_text(json.dumps(receipt_data), encoding="utf-8")

    proc, report_path = _run_production_validation(tmp_path, "stage6_exact", norm_path)
    assert proc.returncode == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "PASS"
    assert report["blocked_count"] == 0


def _valid_png_bytes():
    return b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"


def test_self_consistent_google_intitle_receipt_passes_structural_scope(tmp_path):
    png = tmp_path / "screen.png"
    png.write_bytes(_valid_png_bytes())
    obs = tmp_path / "obs.json"
    obs.write_text(json.dumps({
        "page_url": "https://www.google.com/search?q=intitle%3A%22wedding+calculator%22",
        "query": 'intitle:"wedding calculator"', "result_stats_text": "About 10 results",
        "intitle_results": 10, "market": "US", "observed_at": "2026-08-27T00:00:00Z",
    }), encoding="utf-8")
    norm_path = tmp_path / "intitle_norm.json"
    receipt_path = tmp_path / "intitle_norm.receipt.json"
    norm_data = {
        "keyword": "wedding calculator", "intitle_results": 10, "source": "Google",
        "market": "US", "observed_at": "2026-08-27T00:00:00Z",
        "evidence_ref": str(png), "observation_ref": str(obs),
        "evidence_receipt_ref": str(receipt_path),
    }
    norm_path.write_text(json.dumps(norm_data), encoding="utf-8")
    receipt_data = {
        "schema": "seo-observed-evidence/v2",
        "collector": "google_live_collector",
        "collector_source_sha256": hashlib.sha256((ROOT / "runtime" / "collectors" / "google_live_collector.py").read_bytes()).hexdigest(),
        "evidence_type": "google_intitle",
        "normalized_ref": str(norm_path),
        "normalized_sha256": hashlib.sha256(norm_path.read_bytes()).hexdigest(),
        "artifacts": [
            {"role": "screenshot", "path": str(png), "sha256": hashlib.sha256(png.read_bytes()).hexdigest()},
            {"role": "structured_observation", "path": str(obs), "sha256": hashlib.sha256(obs.read_bytes()).hexdigest()},
        ],
    }
    receipt_path.write_text(json.dumps(receipt_data), encoding="utf-8")

    proc, report_path = _run_production_validation(tmp_path, "intitle_observation", norm_path)
    assert proc.returncode == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "PASS"


def test_self_consistent_google_trends_receipt_passes_structural_scope(tmp_path):
    png = tmp_path / "trends.png"
    png.write_bytes(_valid_png_bytes())
    raw = tmp_path / "trends_raw.json"
    raw.write_text(json.dumps({
        "keyword": "wedding calculator", "market": "US", "observed_at": "2026-08-27T00:00:00Z",
        "source_url": "https://trends.google.com/trends/api/widgetdata/timeline",
        "payload": {"default": {"timelineData": [{"time": "1", "value": [50]}, {"time": "2", "value": [60]}]}},
        "series": [{"time": "1", "value": 50}, {"time": "2", "value": 60}],
    }), encoding="utf-8")
    norm_path = tmp_path / "trends_norm.json"
    receipt_path = tmp_path / "trends_norm.receipt.json"
    norm_data = {
        "keyword": "wedding calculator", "is_finalist": True, "google_trends_source": "Google Trends",
        "google_trends_market": "US", "google_trends_observed_at": "2026-08-27T00:00:00Z",
        "google_trends_evidence_ref": str(raw), "google_trends_screenshot_ref": str(png),
        "google_trends_series": [{"time": "1", "value": 50}, {"time": "2", "value": 60}],
        "evidence_receipt_ref": str(receipt_path),
    }
    norm_path.write_text(json.dumps(norm_data), encoding="utf-8")
    receipt_data = {
        "schema": "seo-observed-evidence/v2",
        "collector": "google_live_collector",
        "collector_source_sha256": hashlib.sha256((ROOT / "runtime" / "collectors" / "google_live_collector.py").read_bytes()).hexdigest(),
        "evidence_type": "google_trends",
        "normalized_ref": str(norm_path),
        "normalized_sha256": hashlib.sha256(norm_path.read_bytes()).hexdigest(),
        "artifacts": [
            {"role": "temporal_payload", "path": str(raw), "sha256": hashlib.sha256(raw.read_bytes()).hexdigest()},
            {"role": "screenshot", "path": str(png), "sha256": hashlib.sha256(png.read_bytes()).hexdigest()},
        ],
    }
    receipt_path.write_text(json.dumps(receipt_data), encoding="utf-8")

    proc, report_path = _run_production_validation(tmp_path, "finalist_trend", norm_path)
    assert proc.returncode == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "PASS"


def test_forged_observed_receipt_leads_to_hook_deny(tmp_path):
    raw = tmp_path / "raw.json"
    raw.write_text("{}", encoding="utf-8")
    norm_path = tmp_path / "forged_norm.json"
    receipt_path = tmp_path / "forged_norm.receipt.json"
    norm_data = fake_exact_row()
    norm_data["evidence_receipt_ref"] = str(receipt_path)
    norm_path.write_text(json.dumps(norm_data), encoding="utf-8")
    receipt_data = {
        "schema": "seo-observed-evidence/v2",
        "collector": "semrush_relay_collector",
        "collector_source_sha256": "fake",
        "evidence_type": "semrush_exact",
        "normalized_ref": str(norm_path),
        "normalized_sha256": "fake",
        "artifacts": [{"role": "relay_raw_response", "path": str(raw), "sha256": "fake"}],
    }
    receipt_path.write_text(json.dumps(receipt_data), encoding="utf-8")

    proc, report_path = _run_production_validation(tmp_path, "stage6_exact", norm_path)
    assert proc.returncode == 2

    val_receipt = tmp_path / "val.receipt.json"
    val_receipt.write_text(json.dumps({
        "schema": "seo-stage-validation/v1",
        "stage": "stage6_exact",
        "status": "PASS",
        "candidate_id": None,
        "validator_source_sha256": hashlib.sha256(VALIDATOR.read_bytes()).hexdigest(),
        "report_ref": str(report_path),
        "report_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
    }), encoding="utf-8")
    manifest = {
        "run_id": "r_forged",
        "route": "traditional",
        "status": "IN_PROGRESS",
        "stages": {"stage6_exact": {"status": "PASS", "validation_receipt_ref": str(val_receipt)}},
    }
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "python3 skills/seo-keyword-selection/scripts/evaluate_candidates.py --stage exact"},
    }
    env = dict(os.environ, SEO_RUN_MANIFEST=str(tmp_path / "active.json"))
    (tmp_path / "active.json").write_text(json.dumps(manifest), encoding="utf-8")
    hook_proc = subprocess.run([sys.executable, str(HOOK), "pre"], input=json.dumps(payload), text=True, capture_output=True, env=env)
    assert hook_proc.returncode == 2
    assert "validation receipt" in hook_proc.stderr.lower()


def _write_serp_receipt_fixture(tmp_path, results=None):
    png = tmp_path / "serp.png"
    png.write_bytes(_valid_png_bytes())
    page_urls = [
        "https://www.google.com/search?q=wedding+calculator&num=10",
        "https://www.google.com/search?q=wedding+calculator&start=10",
    ]
    observed_at = "2026-08-27T00:00:00Z"
    results = results or [
        {"rank": index, "url": f"https://result{index}.example/", "title": f"Result {index}"}
        for index in range(1, 11)
    ]
    obs = tmp_path / "serp-observation.json"
    obs.write_text(
        json.dumps(
            {
                "page_url": page_urls[-1],
                "page_urls": page_urls,
                "keyword": "wedding calculator",
                "market": "US",
                "observed_at": observed_at,
                "results": results,
            }
        ),
        encoding="utf-8",
    )
    norm_path = tmp_path / "serp.json"
    receipt_path = tmp_path / "serp.receipt.json"
    norm_path.write_text(
        json.dumps(
            {
                "keyword": "wedding calculator",
                "source": "Google",
                "market": "US",
                "observed_at": observed_at,
                "evidence_ref": str(png),
                "observation_ref": str(obs),
                "page_urls": page_urls,
                "results": results,
                "evidence_receipt_ref": str(receipt_path),
            }
        ),
        encoding="utf-8",
    )
    receipt_path.write_text(
        json.dumps(
            {
                "schema": "seo-observed-evidence/v2",
                "collector": "google_live_collector",
                "collector_source_sha256": hashlib.sha256(
                    (ROOT / "runtime" / "collectors" / "google_live_collector.py").read_bytes()
                ).hexdigest(),
                "evidence_type": "google_serp",
                "normalized_ref": str(norm_path),
                "normalized_sha256": hashlib.sha256(norm_path.read_bytes()).hexdigest(),
                "artifacts": [
                    {"role": "screenshot", "path": str(png), "sha256": hashlib.sha256(png.read_bytes()).hexdigest()},
                    {"role": "structured_observation", "path": str(obs), "sha256": hashlib.sha256(obs.read_bytes()).hexdigest()},
                ],
            }
        ),
        encoding="utf-8",
    )
    return norm_path, receipt_path


def test_google_serp_production_binding_requires_ten_contiguous_unique_http_results(tmp_path):
    invalid_results = [
        {"rank": index, "url": f"https://result{index}.example/", "title": f"Result {index}"}
        for index in range(1, 10)
    ] + [{"rank": 9, "url": "https://result10.example/", "title": "Result 10"}]
    norm_path, _ = _write_serp_receipt_fixture(tmp_path, invalid_results)

    proc, report_path = _run_production_validation(tmp_path, "serp_review", norm_path)

    assert proc.returncode == 2
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert any("rank" in error.lower() or "ten" in error.lower() for error in report["blocked"][0]["errors"])


def test_tampered_google_serp_receipt_fails_production_validation(tmp_path):
    norm_path, receipt_path = _write_serp_receipt_fixture(tmp_path)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["normalized_sha256"] = "0" * 64
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    proc, report_path = _run_production_validation(tmp_path, "serp_review", norm_path)

    assert proc.returncode == 2
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert "evidence" in report["blocked"][0]["errors"][0].lower()
