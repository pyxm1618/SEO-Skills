#!/usr/bin/env python3
"""P1 Integrity Attack Matrix Test Runner (P1-A to P1-Q).
Executes adversarial attacks and records independent evidence.
"""

import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "runtime"
EVALUATOR = ROOT / "skills" / "seo-keyword-selection" / "scripts" / "evaluate_candidates.py"
HOOK = RUNTIME / "codex_stage_hook.py"
VALIDATOR = RUNTIME / "stage_validator.py"
BINDING = RUNTIME / "evidence_binding.py"

sys.path.insert(0, str(RUNTIME))
import evidence_binding
import codex_stage_hook

attack_results = {}

def log_test(test_id, passed, detail):
    status = "PASS" if passed else "FAIL"
    attack_results[test_id] = {"status": status, "detail": detail}
    print(f"[{status}] {test_id}: {detail}")

def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

dummy_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"

print("========================================")
print("Running P1 Attack Matrix (P1-A to P1-Q)")
print("========================================")

with tempfile.TemporaryDirectory() as tmpdir:
    td = Path(tmpdir)
    cur_time = datetime.now(timezone.utc).isoformat()
    
    # ---------------------------------------------------------
    # P1-A: Hand-written observed, no receipt
    # ---------------------------------------------------------
    p1a_input = td / "p1a_input.json"
    p1a_input.write_text(json.dumps({
        "keyword": "wedding calculator",
        "volume": 2400,
        "kd": 28,
        "cpc": 1.45,
        "intent": ["commercial"],
        "competition_level": "low",
        "trend": [50]*12,
        "metric_source": "Semrush",
        "metric_database": "us",
        "metric_stage": "exact",
        "observed_at": cur_time,
        "relay_origin": "https://sem.3ue.com/",
        "provenance_ref": "https://sem.3ue.com/handwritten"
    }))
    proc_p1a = subprocess.run(
        [sys.executable, str(VALIDATOR), "--stage", "stage6_exact", "--input", str(p1a_input), "--production", "--report", str(td / "p1a_report.json")],
        capture_output=True, text=True
    )
    p1a_report = json.loads((td / "p1a_report.json").read_text()) if (td / "p1a_report.json").exists() else {}
    p1a_blocked = (proc_p1a.returncode == 2) and (p1a_report.get("status") == "BLOCKED") and any("receipt" in err for err in p1a_report.get("blocked", [{}])[0].get("errors", []))
    log_test("P1-A", p1a_blocked, f"Hand-written observed without receipt correctly BLOCKED (code={proc_p1a.returncode})")

    # ---------------------------------------------------------
    # P1-B: Evaluator false provenance
    # ---------------------------------------------------------
    p1b_input = td / "p1b_input.json"
    p1b_input.write_text(json.dumps([{
        "keyword": "wedding calculator",
        "volume": 2400,
        "kd": 28,
        "cpc": 1.45,
        "intent": ["commercial"],
        "competition_level": "low",
        "trend": [50]*12,
        "metric_source": "Semrush",
        "metric_database": "us",
        "metric_stage": "exact",
        "observed_at": cur_time,
        "relay_origin": "https://sem.3ue.com/",
        "provenance_ref": "https://sem.3ue.com/handwritten"
    }]))
    proc_p1b = subprocess.run(
        [sys.executable, str(EVALUATOR), "--stage", "exact", "--input", str(p1b_input)],
        capture_output=True, text=True
    )
    p1b_data = json.loads(proc_p1b.stdout)
    row0 = p1b_data["rows"][0] if isinstance(p1b_data, dict) and "rows" in p1b_data else p1b_data[0]
    p1b_not_verified = row0.get("provenance_status") == "unverified"
    log_test("P1-B", p1b_not_verified, f"Evaluator provenance_status is '{row0.get('provenance_status')}' (not 'verified')")

    # ---------------------------------------------------------
    # P1-H: Direct writer self-mint
    # ---------------------------------------------------------
    capture_file = td / "capture.json"
    capture_file.write_text(json.dumps({"capture": "live_mock_for_attack_only"}))
    raw_semrush_exact = td / "semrush_exact.raw.json"
    raw_semrush_exact.write_text(json.dumps({
        "observed_at": cur_time,
        "relay_origin": "https://sem.3ue.com/",
        "request_method": "POST",
        "request_path": "/api/v1/exact",
        "capture_observed_at": cur_time,
        "capture_evidence_ref": str(capture_file),
        "mode": "exact",
        "metric_database": "us",
        "keyword": "wedding calculator",
        "response": {
            "result": {
                "keywords": [
                    {
                        "phrase": "wedding calculator",
                        "database": "us",
                        "volume": 2400,
                        "difficulty": 28,
                        "cpc": 1.45,
                        "intents": ["commercial"],
                        "competition_level": "0.15",
                        "trend": [100]*12
                    }
                ]
            }
        }
    }))
    p1h_caught = False
    try:
        evidence_binding.write_observed_output(
            td / "p1h_out.json",
            {"keyword": "wedding calculator", "volume": 2400},
            "semrush_relay_collector",
            "semrush_exact",
            [{"path": str(raw_semrush_exact), "role": "relay_raw_response"}, {"path": str(capture_file), "role": "current_network_capture"}]
        )
    except evidence_binding.EvidenceIntegrityError as exc:
        p1h_caught = "production evidence receipts may only be minted by direct CLI execution" in str(exc)
    log_test("P1-H", p1h_caught, "Direct call to evidence_binding.write_observed_output was rejected with EvidenceIntegrityError")

    # ---------------------------------------------------------
    # P1-I: Imported Collector monkeypatch
    # ---------------------------------------------------------
    collector_file = RUNTIME / "collectors" / "semrush_relay_collector.py"
    req_file = td / "req.json"
    req_file.write_text(json.dumps({
        "path": "/api/v1/exact",
        "method": "POST",
        "body": {},
        "capture_observed_at": cur_time,
        "capture_evidence_ref": str(capture_file),
        "mode": "exact",
        "metric_database": "us",
        "keyword": "wedding calculator"
    }))
    p1i_script = td / "p1i_attack.py"
    p1i_script.write_text(f"""
import sys
sys.path.insert(0, "{RUNTIME}")
sys.path.insert(0, "{RUNTIME / 'collectors'}")
import semrush_relay_collector
class Dummy:
    def close(self): pass
    def stop(self): pass
semrush_relay_collector.connect_same_origin = lambda: (Dummy(), Dummy(), object())
semrush_relay_collector.collect = lambda page, desc, raw_evidence_ref=None, raw_output_path=None: {{
    "keyword": "wedding calculator",
    "volume": 2400, "kd": 28, "cpc": 1.45, "intent": ["commercial"],
    "competition_level": "0.15", "trend": [100]*12,
    "metric_source": "Semrush", "metric_database": "us", "metric_stage": "exact",
    "observed_at": "{cur_time}", "relay_origin": "https://sem.3ue.com/",
    "provenance_ref": "{capture_file}"
}}
sys.argv = ["semrush_relay_collector.py", "--request", "{req_file}", "--output", "{td / 'p1i_out.json'}"]
raise SystemExit(semrush_relay_collector.main())
""")
    proc_p1i = subprocess.run([sys.executable, str(p1i_script)], capture_output=True, text=True)
    p1i_blocked = proc_p1i.returncode == 2 and "production evidence receipts may only be minted by direct CLI execution" in proc_p1i.stderr
    log_test("P1-I", p1i_blocked, f"Imported collector monkeypatch rejected (code={proc_p1i.returncode})")

    # ---------------------------------------------------------
    # P1-J: Artifact Roles check
    # ---------------------------------------------------------
    p1j_missing_role = False
    try:
        evidence_binding._artifact_records([{"path": str(raw_semrush_exact), "role": "relay_raw_response"}], "semrush_exact")
    except evidence_binding.EvidenceIntegrityError as exc:
        p1j_missing_role = "collector artifact roles mismatch" in str(exc)
    log_test("P1-J", p1j_missing_role, "Missing required artifact role (current_network_capture) raised EvidenceIntegrityError")

    # ---------------------------------------------------------
    # Baseline setup for semantic replay attacks
    # ---------------------------------------------------------
    norm_exact_path = td / "exact.norm.json"
    receipt_exact_path = td / "exact.norm.receipt.json"
    exact_payload = {
        "keyword": "wedding calculator",
        "volume": 2400,
        "kd": 28,
        "cpc": 1.45,
        "intent": ["commercial"],
        "competition_level": "0.15",
        "trend": [100]*12,
        "metric_source": "Semrush",
        "metric_database": "us",
        "metric_stage": "exact",
        "observed_at": cur_time,
        "relay_origin": "https://sem.3ue.com/",
        "provenance_ref": str(raw_semrush_exact),
        "evidence_receipt_ref": str(receipt_exact_path)
    }
    norm_exact_path.write_text(json.dumps(exact_payload, indent=2))
    receipt_payload = {
        "schema": "seo-observed-evidence/v2",
        "collector": "semrush_relay_collector",
        "collector_source_sha256": sha256_file(collector_file),
        "evidence_type": "semrush_exact",
        "normalized_ref": str(norm_exact_path),
        "normalized_sha256": sha256_file(norm_exact_path),
        "artifacts": [
            {"role": "relay_raw_response", "path": str(raw_semrush_exact), "sha256": sha256_file(raw_semrush_exact)},
            {"role": "current_network_capture", "path": str(capture_file), "sha256": sha256_file(capture_file)}
        ]
    }
    receipt_exact_path.write_text(json.dumps(receipt_payload, indent=2))

    # ---------------------------------------------------------
    # P1-C: Tamper after normalized
    # ---------------------------------------------------------
    tampered_norm = copy.deepcopy(exact_payload)
    tampered_norm["volume"] = 99999
    tampered_norm_file = td / "tampered_norm.json"
    tampered_norm_file.write_text(json.dumps(tampered_norm, indent=2))
    proc_p1c = subprocess.run(
        [sys.executable, str(VALIDATOR), "--stage", "stage6_exact", "--input", str(tampered_norm_file), "--production", "--report", str(td / "p1c_rep.json")],
        capture_output=True, text=True
    )
    p1c_report = json.loads((td / "p1c_rep.json").read_text())
    p1c_blocked = proc_p1c.returncode == 2 and any("differs from collector-bound normalized evidence" in err or "hash mismatch" in err for err in p1c_report.get("blocked", [{}])[0].get("errors", []))
    log_test("P1-C", p1c_blocked, f"Tampered normalized volume rejected (code={proc_p1c.returncode})")

    # ---------------------------------------------------------
    # P1-D: Tamper after raw
    # ---------------------------------------------------------
    raw_tampered_file = td / "raw_tampered.json"
    raw_tampered_file.write_text(json.dumps({"some": "tampered_data"}))
    receipt_p1d = copy.deepcopy(receipt_payload)
    receipt_p1d["artifacts"][0]["path"] = str(raw_tampered_file)
    receipt_p1d["artifacts"][0]["sha256"] = sha256_file(raw_tampered_file)
    receipt_p1d_path = td / "p1d.receipt.json"
    receipt_p1d_path.write_text(json.dumps(receipt_p1d, indent=2))
    norm_p1d = copy.deepcopy(exact_payload)
    norm_p1d["evidence_receipt_ref"] = str(receipt_p1d_path)
    norm_p1d_path = td / "p1d_norm.json"
    norm_p1d_path.write_text(json.dumps(norm_p1d, indent=2))
    receipt_p1d["normalized_ref"] = str(norm_p1d_path)
    receipt_p1d["normalized_sha256"] = sha256_file(norm_p1d_path)
    receipt_p1d_path.write_text(json.dumps(receipt_p1d, indent=2))
    
    proc_p1d = subprocess.run(
        [sys.executable, str(VALIDATOR), "--stage", "stage6_exact", "--input", str(norm_p1d_path), "--production", "--report", str(td / "p1d_rep.json")],
        capture_output=True, text=True
    )
    p1d_report = json.loads((td / "p1d_rep.json").read_text())
    p1d_blocked = proc_p1d.returncode == 2 and any("missing fields" in err for err in p1d_report.get("blocked", [{}])[0].get("errors", []))
    log_test("P1-D", p1d_blocked, f"Tampered raw artifact rejected by semantics replay (code={proc_p1d.returncode})")

    # ---------------------------------------------------------
    # P1-K: Raw replay mismatch (modify volume in raw response but fix hashes)
    # ---------------------------------------------------------
    raw_k_data = json.loads(raw_semrush_exact.read_text())
    raw_k_data["response"]["result"]["keywords"][0]["volume"] = 5555  # differs from normalized 2400
    raw_k_file = td / "raw_k.json"
    raw_k_file.write_text(json.dumps(raw_k_data, indent=2))
    
    receipt_k = copy.deepcopy(receipt_payload)
    receipt_k["artifacts"][0] = {"role": "relay_raw_response", "path": str(raw_k_file), "sha256": sha256_file(raw_k_file)}
    receipt_k_file = td / "receipt_k.json"
    
    norm_k = copy.deepcopy(exact_payload)
    norm_k["evidence_receipt_ref"] = str(receipt_k_file)
    norm_k_file = td / "norm_k.json"
    norm_k_file.write_text(json.dumps(norm_k, indent=2))
    
    receipt_k["normalized_ref"] = str(norm_k_file)
    receipt_k["normalized_sha256"] = sha256_file(norm_k_file)
    receipt_k_file.write_text(json.dumps(receipt_k, indent=2))
    
    proc_p1k = subprocess.run(
        [sys.executable, str(VALIDATOR), "--stage", "stage6_exact", "--input", str(norm_k_file), "--production", "--report", str(td / "p1k_rep.json")],
        capture_output=True, text=True
    )
    p1k_report = json.loads((td / "p1k_rep.json").read_text())
    p1k_blocked = proc_p1k.returncode == 2 and any("raw-response replay" in err for err in p1k_report.get("blocked", [{}])[0].get("errors", []))
    log_test("P1-K", p1k_blocked, f"Raw replay volume mismatch detected and blocked (code={proc_p1k.returncode})")

    # ---------------------------------------------------------
    # P1-L: Capture binding mismatch
    # ---------------------------------------------------------
    other_capture = td / "other_capture.json"
    other_capture.write_text(json.dumps({"capture": "other"}))
    receipt_l = copy.deepcopy(receipt_payload)
    receipt_l["artifacts"][1] = {"role": "current_network_capture", "path": str(other_capture), "sha256": sha256_file(other_capture)}
    receipt_l_file = td / "receipt_l.json"
    norm_l = copy.deepcopy(exact_payload)
    norm_l["evidence_receipt_ref"] = str(receipt_l_file)
    norm_l_file = td / "norm_l.json"
    norm_l_file.write_text(json.dumps(norm_l, indent=2))
    receipt_l["normalized_ref"] = str(norm_l_file)
    receipt_l["normalized_sha256"] = sha256_file(norm_l_file)
    receipt_l_file.write_text(json.dumps(receipt_l, indent=2))
    
    proc_p1l = subprocess.run(
        [sys.executable, str(VALIDATOR), "--stage", "stage6_exact", "--input", str(norm_l_file), "--production", "--report", str(td / "p1l_rep.json")],
        capture_output=True, text=True
    )
    p1l_report = json.loads((td / "p1l_rep.json").read_text())
    p1l_blocked = proc_p1l.returncode == 2 and any("not bound to the receipt network capture" in err for err in p1l_report.get("blocked", [{}])[0].get("errors", []))
    log_test("P1-L", p1l_blocked, f"Capture binding mismatch correctly blocked (code={proc_p1l.returncode})")

    # ---------------------------------------------------------
    # P1-M: Google structured mismatch
    # ---------------------------------------------------------
    png_file = td / "screen.png"
    png_file.write_bytes(dummy_png)
    google_obs_file = td / "google_obs.json"
    google_obs_file.write_text(json.dumps({
        "page_url": "https://www.google.com/search?q=intitle%3A%22wedding+calculator%22",
        "query": 'intitle:"wedding calculator"',
        "result_stats_text": "About 142 results",
        "intitle_results": 142,
        "market": "US",
        "observed_at": cur_time
    }))
    receipt_m_file = td / "receipt_m.json"
    norm_m_file = td / "norm_m.json"
    norm_m_payload = {
        "keyword": "wedding calculator",
        "intitle_results": 999,  # Mismatch with observation 142!
        "source": "Google",
        "market": "US",
        "observed_at": cur_time,
        "evidence_ref": str(png_file),
        "observation_ref": str(google_obs_file),
        "evidence_receipt_ref": str(receipt_m_file)
    }
    norm_m_file.write_text(json.dumps(norm_m_payload, indent=2))
    receipt_m_payload = {
        "schema": "seo-observed-evidence/v2",
        "collector": "google_live_collector",
        "collector_source_sha256": sha256_file(RUNTIME / "collectors" / "google_live_collector.py"),
        "evidence_type": "google_intitle",
        "normalized_ref": str(norm_m_file),
        "normalized_sha256": sha256_file(norm_m_file),
        "artifacts": [
            {"role": "screenshot", "path": str(png_file), "sha256": sha256_file(png_file)},
            {"role": "structured_observation", "path": str(google_obs_file), "sha256": sha256_file(google_obs_file)}
        ]
    }
    receipt_m_file.write_text(json.dumps(receipt_m_payload, indent=2))
    
    proc_p1m = subprocess.run(
        [sys.executable, str(VALIDATOR), "--stage", "intitle_observation", "--input", str(norm_m_file), "--production", "--report", str(td / "p1m_rep.json")],
        capture_output=True, text=True
    )
    p1m_report = json.loads((td / "p1m_rep.json").read_text())
    p1m_blocked = proc_p1m.returncode == 2 and any("intitle_results differs from structured observation" in err for err in p1m_report.get("blocked", [{}])[0].get("errors", []))
    log_test("P1-M", p1m_blocked, f"Google structured observation mismatch detected and blocked (code={proc_p1m.returncode})")

    # ---------------------------------------------------------
    # P1-N: Trends replay mismatch
    # ---------------------------------------------------------
    trends_raw_file = td / "trends_raw.json"
    trends_raw_file.write_text(json.dumps({
        "keyword": "wedding calculator",
        "market": "US",
        "observed_at": cur_time,
        "source_url": "https://trends.google.com/trends/api/widgetdata/timeline",
        "payload": {
            "default": {
                "timelineData": [
                    {"time": "1672531200", "value": [50], "formattedTime": "Jan 2023"},
                    {"time": "1675209600", "value": [60], "formattedTime": "Feb 2023"}
                ]
            }
        },
        "series": [{"time": "1672531200", "value": 50, "formatted_time": "Jan 2023"}, {"time": "1675209600", "value": 60, "formatted_time": "Feb 2023"}]
    }))
    receipt_n_file = td / "receipt_n.json"
    norm_n_file = td / "norm_n.json"
    norm_n_payload = {
        "keyword": "wedding calculator",
        "is_finalist": True,
        "google_trends_source": "Google Trends",
        "google_trends_market": "US",
        "google_trends_observed_at": cur_time,
        "google_trends_evidence_ref": str(trends_raw_file),
        "google_trends_screenshot_ref": str(png_file),
        "google_trends_series": [
            {"time": "1672531200", "value": 999, "formatted_time": "Jan 2023"},
            {"time": "1675209600", "value": 60, "formatted_time": "Feb 2023"}
        ], # Tampered point 0!
        "evidence_receipt_ref": str(receipt_n_file)
    }
    norm_n_file.write_text(json.dumps(norm_n_payload, indent=2))
    receipt_n_payload = {
        "schema": "seo-observed-evidence/v2",
        "collector": "google_live_collector",
        "collector_source_sha256": sha256_file(RUNTIME / "collectors" / "google_live_collector.py"),
        "evidence_type": "google_trends",
        "normalized_ref": str(norm_n_file),
        "normalized_sha256": sha256_file(norm_n_file),
        "artifacts": [
            {"role": "temporal_payload", "path": str(trends_raw_file), "sha256": sha256_file(trends_raw_file)},
            {"role": "screenshot", "path": str(png_file), "sha256": sha256_file(png_file)}
        ]
    }
    receipt_n_file.write_text(json.dumps(receipt_n_payload, indent=2))
    proc_p1n = subprocess.run(
        [sys.executable, str(VALIDATOR), "--stage", "finalist_trend", "--input", str(norm_n_file), "--production", "--report", str(td / "p1n_rep.json")],
        capture_output=True, text=True
    )
    p1n_report = json.loads((td / "p1n_rep.json").read_text())
    p1n_blocked = proc_p1n.returncode == 2 and any("series differs from temporal payload replay" in err for err in p1n_report.get("blocked", [{}])[0].get("errors", []))
    log_test("P1-N", p1n_blocked, f"Trends temporal payload replay mismatch detected and blocked (code={proc_p1n.returncode})")

    # ---------------------------------------------------------
    # P1-F: Bare PASS in manifest
    # ---------------------------------------------------------
    manifest_p1f = td / "manifest_p1f.json"
    manifest_p1f.write_text(json.dumps({
        "run_id": "p1f-test",
        "stages": {"stage6_exact": {"status": "PASS"}} # No validation_receipt_ref
    }))
    env_p1f = dict(os.environ, SEO_RUN_MANIFEST=str(manifest_p1f))
    hook_input_f = json.dumps({"tool_name": "bash", "tool_input": "python3 skills/seo-keyword-selection/scripts/evaluate_candidates.py --stage exact"})
    proc_p1f = subprocess.run([sys.executable, str(HOOK), "pre"], input=hook_input_f, text=True, capture_output=True, env=env_p1f)
    p1f_denied = proc_p1f.returncode == 2 and "PASS validation receipt invalid: PASS lacks validation receipt" in proc_p1f.stderr
    log_test("P1-F", p1f_denied, f"Bare PASS in manifest correctly denied by PreToolUse hook (code={proc_p1f.returncode})")

    # ---------------------------------------------------------
    # P1-G: Bare COMPLETE in manifest
    # ---------------------------------------------------------
    manifest_p1g = td / "manifest_p1g.json"
    manifest_p1g.write_text(json.dumps({
        "run_id": "p1g-test",
        "status": "COMPLETE" # No completion_requirements
    }))
    env_p1g = dict(os.environ, SEO_RUN_MANIFEST=str(manifest_p1g))
    proc_p1g = subprocess.run([sys.executable, str(HOOK), "stop"], input="{}", text=True, capture_output=True, env=env_p1g)
    p1g_denied = proc_p1g.returncode == 2 and "COMPLETE lacks explicit completion_requirements" in proc_p1g.stderr
    log_test("P1-G", p1g_denied, f"Bare COMPLETE status correctly denied by Stop hook (code={proc_p1g.returncode})")

    # ---------------------------------------------------------
    # P1-E: Post-validation tampering
    # ---------------------------------------------------------
    val_report_e = td / "val_rep_e.json"
    proc_val_e = subprocess.run(
        [sys.executable, str(VALIDATOR), "--stage", "stage6_exact", "--input", str(norm_exact_path), "--production", "--report", str(val_report_e)],
        capture_output=True, text=True
    )
    val_receipt_e = val_report_e.with_suffix(".receipt.json")
    manifest_p1e = td / "manifest_p1e.json"
    manifest_p1e.write_text(json.dumps({
        "run_id": "p1e-test",
        "stages": {"stage6_exact": {"status": "PASS", "validation_receipt_ref": str(val_receipt_e)}}
    }))
    env_p1e = dict(os.environ, SEO_RUN_MANIFEST=str(manifest_p1e))
    hook_input_e = json.dumps({"tool_name": "bash", "tool_input": "python3 skills/seo-keyword-selection/scripts/evaluate_candidates.py --stage exact"})
    proc_e1 = subprocess.run([sys.executable, str(HOOK), "pre"], input=hook_input_e, text=True, capture_output=True, env=env_p1e)
    norm_exact_path.write_text(json.dumps({"keyword": "tampered", "volume": 999}))
    proc_e2 = subprocess.run([sys.executable, str(HOOK), "pre"], input=hook_input_e, text=True, capture_output=True, env=env_p1e)
    p1e_denied = proc_e1.returncode == 0 and proc_e2.returncode == 2 and "underlying evidence invalid" in proc_e2.stderr
    log_test("P1-E", p1e_denied, f"Post-validation tampering detected by re-verification in Hook (init={proc_e1.returncode}, tampered={proc_e2.returncode})")

    # ---------------------------------------------------------
    # P1-O: Marker spoofing
    # ---------------------------------------------------------
    manifest_p1o = td / "manifest_p1o.json"
    manifest_p1o.write_text(json.dumps({
        "run_id": "p1o-test",
        "stages": {
            "fake_stage": {"status": "PASS"},
            "stage6_exact": {"status": "BLOCKED", "blocked_reason": "stage6 not run"}
        }
    }))
    env_p1o = dict(os.environ, SEO_RUN_MANIFEST=str(manifest_p1o))
    hook_input_o = json.dumps({
        "tool_name": "bash",
        "tool_input": "SEO_STAGE_REQUIRE=fake_stage python3 skills/seo-keyword-selection/scripts/evaluate_candidates.py --stage exact"
    })
    proc_p1o = subprocess.run([sys.executable, str(HOOK), "pre"], input=hook_input_o, text=True, capture_output=True, env=env_p1o)
    p1o_denied = proc_p1o.returncode == 2 and "SEO stage gate denied stage6_exact; status=BLOCKED" in proc_p1o.stderr
    log_test("P1-O", p1o_denied, f"Marker spoofing ignored; inferred stage 'stage6_exact' enforced and denied (code={proc_p1o.returncode})")

    # ---------------------------------------------------------
    # P1-P: Fake completion stage
    # ---------------------------------------------------------
    manifest_p1p = td / "manifest_p1p.json"
    manifest_p1p.write_text(json.dumps({
        "run_id": "p1p-test",
        "status": "COMPLETE",
        "route": "emerging",
        "completion_requirements": [{"stage": "fake_stage"}]
    }))
    env_p1p = dict(os.environ, SEO_RUN_MANIFEST=str(manifest_p1p))
    proc_p1p = subprocess.run([sys.executable, str(HOOK), "stop"], input="{}", text=True, capture_output=True, env=env_p1p)
    p1p_denied = proc_p1p.returncode == 2 and "uses unknown/non-canonical stage: fake_stage" in proc_p1p.stderr
    log_test("P1-P", p1p_denied, f"Fake completion stage rejected by Stop hook (code={proc_p1p.returncode})")

    # ---------------------------------------------------------
    # P1-Q: Route minimum missing
    # ---------------------------------------------------------
    manifest_p1q = td / "manifest_p1q.json"
    manifest_p1q.write_text(json.dumps({
        "run_id": "p1q-test",
        "status": "COMPLETE",
        "route": "traditional",
        "completion_requirements": [
            {"stage": "discovery_autocomplete"}
        ],
        "stages": {
            "discovery_autocomplete": {"status": "PASS", "validation_receipt_ref": "nonexistent.receipt.json"}
        }
    }))
    env_p1q = dict(os.environ, SEO_RUN_MANIFEST=str(manifest_p1q))
    proc_p1q = subprocess.run([sys.executable, str(HOOK), "stop"], input="{}", text=True, capture_output=True, env=env_p1q)
    test_min_traditional = codex_stage_hook.ROUTE_MINIMUM_STAGES["traditional"]
    test_min_emerging = codex_stage_hook.ROUTE_MINIMUM_STAGES["emerging"]
    p1q_min_check = (test_min_traditional == frozenset({"discovery_autocomplete", "stage6_exact"})) and (test_min_emerging == frozenset({"stage6_exact"}))
    p1q_denied = proc_p1q.returncode == 2 and p1q_min_check
    log_test("P1-Q", p1q_denied, f"Missing route minimum stages contract enforced and rejected (code={proc_p1q.returncode})")

print("========================================")
all_pass = all(item["status"] == "PASS" for item in attack_results.values())
print(f"P1 Attack Matrix Result: {'ALL PASS (17/17)' if all_pass and len(attack_results) == 17 else 'FAIL'}")
print("========================================")

output_file = Path("acceptance-evidence/p1-attacks/p1_attack_results.json")
output_file.write_text(json.dumps(attack_results, indent=2))
