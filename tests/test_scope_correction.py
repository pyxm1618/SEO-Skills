# RED tests for returning A+ to workflow-correctness scope.
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BINDING = ROOT / "runtime" / "evidence_binding.py"
HOOK = ROOT / "runtime" / "codex_stage_hook.py"
SEMRUSH = ROOT / "runtime" / "collectors" / "semrush_relay_collector.py"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_structurally_bound_live_receipt_does_not_require_os_broker(tmp_path):
    binding = load_module("scope_binding", BINDING)
    raw = tmp_path / "exact.raw.json"
    capture = tmp_path / "capture.json"
    normalized = tmp_path / "exact.json"
    receipt = tmp_path / "exact.receipt.json"

    capture.write_text(json.dumps({"captured_at": "2026-08-28T00:00:00Z", "url": "https://sem.3ue.com/dpa/rpc"}), encoding="utf-8")
    raw_payload = {
        "observed_at": "2026-08-28T00:00:01Z",
        "relay_origin": "https://sem.3ue.com/",
        "request_method": "POST",
        "request_path": "/dpa/rpc",
        "capture_observed_at": "2026-08-28T00:00:00Z",
        "capture_evidence_ref": str(capture),
        "mode": "exact",
        "metric_database": "us",
        "keyword": "wedding calculator",
        "response": {
            "result": {
                "keywords": [
                    {
                        "phrase": "wedding calculator",
                        "database": "us",
                        "volume": 1000,
                        "difficulty": 20,
                        "cpc": 0.2,
                        "intents": ["commercial"],
                        "competition_level": "low",
                        "trend": [50] * 12,
                    }
                ]
            }
        },
    }
    raw.write_text(json.dumps(raw_payload), encoding="utf-8")
    normalized_payload = {
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
        "observed_at": "2026-08-28T00:00:01Z",
        "relay_origin": "https://sem.3ue.com/",
        "provenance_ref": str(raw),
        "evidence_receipt_ref": str(receipt),
    }
    normalized.write_text(json.dumps(normalized_payload), encoding="utf-8")
    receipt_payload = {
        "schema": "seo-observed-evidence/v2",
        "collector": "semrush_relay_collector",
        "collector_source_sha256": hashlib.sha256(SEMRUSH.read_bytes()).hexdigest(),
        "evidence_type": "semrush_exact",
        "normalized_ref": str(normalized),
        "normalized_sha256": hashlib.sha256(normalized.read_bytes()).hexdigest(),
        "artifacts": [
            {"role": "relay_raw_response", "path": str(raw), "sha256": hashlib.sha256(raw.read_bytes()).hexdigest()},
            {"role": "current_network_capture", "path": str(capture), "sha256": hashlib.sha256(capture.read_bytes()).hexdigest()},
        ],
    }
    receipt.write_text(json.dumps(receipt_payload), encoding="utf-8")

    verified = binding.verify_receipt_ref(str(receipt), "semrush_exact")
    assert verified["keyword"] == "wedding calculator"


def test_emerging_route_requires_complete_monitor_pipeline_attestation(tmp_path):
    hook = load_module("scope_route_hook", HOOK)
    handoff = tmp_path / "routes.json"
    handoff.write_text(
        json.dumps(
            {
                "routes": [
                    {
                        "keyword": "new demand term",
                        "status": "emerging",
                        "root_relation": "existing_root",
                        "route": "selection_handoff",
                        "handoff": {
                            "keyword": "new demand term",
                            "root_id": "root-1",
                            "status": "emerging",
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    manifest = {
        "run_id": "r-emerging",
        "route": "emerging",
        "status": "COMPLETE",
        "route_handoff_ref": str(handoff),
        "candidates": {"cand_1": {"keyword": "new demand term"}},
    }
    stages, reason = hook._infer_canonical_required_stages(manifest)
    # Route handoff alone is not a complete monitor pipeline attestation, so no
    # canonical stage list is inferred at all. The separate requirement that a
    # fully attested emerging run must still carry emerging_radar_run is covered
    # by test_emerging_completion_requires_a_validated_radar_run_stage.
    assert stages is None
    assert "receipt" in reason.lower() or "pipeline" in reason.lower()


def test_explicit_finalist_review_false_does_not_require_external_attestation(monkeypatch):
    hook = load_module("scope_finalist_hook", HOOK)
    monkeypatch.setattr(hook, "_verify_validation_receipt", lambda *args, **kwargs: (True, ""))
    monkeypatch.setattr(hook, "_verified_exact_disposition", lambda *args, **kwargs: ("do_candidate", ""))
    manifest = {
        "run_id": "r-traditional",
        "route": "traditional",
        "status": "COMPLETE",
        "stages": {
            "discovery_autocomplete": {"status": "PASS", "validation_receipt_ref": "auto"},
            "discovery_handoff": {"status": "PASS", "validation_receipt_ref": "handoff"},
        },
        "candidates": {
            "cand_1": {
                "keyword": "new demand term",
                "stage6_exact": {"status": "PASS", "validation_receipt_ref": "exact"},
                "intitle_observation": {"status": "PASS", "validation_receipt_ref": "intitle"},
                "kgr_intitle": {"status": "PASS", "validation_receipt_ref": "kgr"},
                "serp_review": {"status": "PASS", "validation_receipt_ref": "serp"},
                "finalist_review": {"is_finalist": False, "reason": "not promoted to serious finalist"},
            }
        },
    }
    valid, reason = hook._verify_completion_requirements(manifest)
    assert valid is True, reason


def test_structured_run_blocker_does_not_require_broker_attestation():
    hook = load_module("scope_blocked_hook", HOOK)
    blocked_reason = "Semrush relay unavailable after authenticated collector attempt"
    valid, reason = hook._verify_blocked_run(
        {
            "run_id": "r-blocked",
            "route": "traditional",
            "status": "BLOCKED",
            "blocked_stage": "stage6_exact",
            "blocked_reason": blocked_reason,
            "stages": {
                "stage6_exact": {"status": "BLOCKED", "blocked_reason": blocked_reason}
            },
        }
    )
    assert valid is True, reason
