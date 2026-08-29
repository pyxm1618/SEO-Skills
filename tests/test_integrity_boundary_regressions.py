import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BINDING = ROOT / "runtime" / "evidence_binding.py"
HOOK = ROOT / "runtime" / "codex_stage_hook.py"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_hook(name="integrity_boundary_hook"):
    return load_module(name, HOOK)


def test_runtime_has_no_os_broker_dependency():
    binding = load_module("boundary_scoped_binding", BINDING)
    assert not hasattr(binding, "_trusted_broker_path")
    assert not hasattr(binding, "_broker_request")
    assert not hasattr(binding, "_mint_issuance_proof")
    assert not hasattr(binding, "verify_external_attestation")


def test_generic_helper_still_cannot_write_collector_receipt(tmp_path):
    binding = load_module("boundary_direct_writer", BINDING)
    raw = tmp_path / "raw.json"
    capture = tmp_path / "capture.json"
    raw.write_text("{}", encoding="utf-8")
    capture.write_text("{}", encoding="utf-8")
    try:
        binding.write_observed_output(
            tmp_path / "out.json",
            {"keyword": "example"},
            "semrush_relay_collector",
            "semrush_exact",
            [
                {"path": raw, "role": "relay_raw_response"},
                {"path": capture, "role": "current_network_capture"},
            ],
        )
    except binding.EvidenceIntegrityError as exc:
        assert "collector" in str(exc).lower() or "direct cli" in str(exc).lower()
    else:
        raise AssertionError("ordinary helper code must not write production collector receipts")


def test_artifact_hash_tampering_is_rejected(tmp_path):
    binding = load_module("boundary_artifact_hash", BINDING)
    raw = tmp_path / "raw.json"
    capture = tmp_path / "capture.json"
    raw.write_text(json.dumps({"original": True}), encoding="utf-8")
    capture.write_text(json.dumps({"capture": True}), encoding="utf-8")
    records = [
        {"role": "relay_raw_response", "path": str(raw), "sha256": hashlib.sha256(raw.read_bytes()).hexdigest()},
        {"role": "current_network_capture", "path": str(capture), "sha256": hashlib.sha256(capture.read_bytes()).hexdigest()},
    ]
    raw.write_text(json.dumps({"tampered": True}), encoding="utf-8")
    try:
        binding._roles_to_paths(records, "semrush_exact")
    except binding.EvidenceIntegrityError as exc:
        assert "hash mismatch" in str(exc).lower()
    else:
        raise AssertionError("post-capture artifact tampering must be rejected")


def test_emerging_route_cannot_be_self_declared_without_monitor_handoff():
    hook = load_hook("route_handoff_required")
    stages, error = hook._infer_canonical_required_stages({
        "run_id": "r-emerging",
        "route": "emerging",
        "status": "COMPLETE",
        "candidates": {"cand_1": {"keyword": "new demand"}},
    })
    assert stages is None
    assert "handoff" in error.lower() or "route" in error.lower()


def test_traditional_candidate_cannot_hide_finalist_by_setting_false(monkeypatch):
    hook = load_hook("finalist_self_report_rejected")
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
                "keyword": "candidate keyword",
                "is_finalist": False,
                "stage6_exact": {"status": "PASS", "validation_receipt_ref": "exact"},
                "intitle_observation": {"status": "PASS", "validation_receipt_ref": "intitle"},
                "kgr_intitle": {"status": "PASS", "validation_receipt_ref": "kgr"},
                "serp_review": {"status": "PASS", "validation_receipt_ref": "serp"},
            }
        },
    }
    valid, reason = hook._verify_completion_requirements(manifest)
    assert valid is False
    assert "finalist" in reason.lower() or "review" in reason.lower() or "disposition" in reason.lower()


def test_candidate_specific_stages_must_not_fallback_to_global_receipts(monkeypatch):
    hook = load_hook("candidate_global_fallback_rejected")
    monkeypatch.setattr(hook, "_verify_validation_receipt", lambda *args, **kwargs: (True, ""))
    manifest = {
        "run_id": "r-candidates",
        "route": "traditional",
        "status": "COMPLETE",
        "stages": {
            "discovery_autocomplete": {"status": "PASS", "validation_receipt_ref": "auto"},
            "discovery_handoff": {"status": "PASS", "validation_receipt_ref": "handoff"},
            "stage6_exact": {"status": "PASS", "validation_receipt_ref": "global-exact"},
            "intitle_observation": {"status": "PASS", "validation_receipt_ref": "global-intitle"},
            "kgr_intitle": {"status": "PASS", "validation_receipt_ref": "global-kgr"},
            "serp_review": {"status": "PASS", "validation_receipt_ref": "global-serp"},
        },
        "candidates": {"cand_a": {}, "cand_b": {}},
    }
    valid, reason = hook._verify_completion_requirements(manifest)
    assert valid is False
    assert "candidate" in reason.lower() or "stage6_exact" in reason.lower()


def test_verified_blocked_candidate_does_not_prevent_completed_batch(monkeypatch):
    hook = load_hook("blocked_candidate_terminal")
    monkeypatch.setattr(hook, "_verify_validation_receipt", lambda *args, **kwargs: (True, ""))
    monkeypatch.setattr(hook, "_verify_terminal_blocked_candidate", lambda *args, **kwargs: (True, ""))
    monkeypatch.setattr(hook, "_verified_exact_disposition", lambda *args, **kwargs: ("do_candidate", ""))
    monkeypatch.setattr(hook, "_verify_finalist_disposition", lambda *args, **kwargs: (True, ""))
    manifest = {
        "run_id": "r-mixed",
        "route": "traditional",
        "status": "COMPLETE",
        "stages": {
            "discovery_autocomplete": {"status": "PASS", "validation_receipt_ref": "auto"},
            "discovery_handoff": {"status": "PASS", "validation_receipt_ref": "handoff"},
        },
        "candidates": {
            "blocked": {
                "keyword": "blocked keyword",
                "terminal_status": "BLOCKED",
                "blocked_stage": "stage6_exact",
                "stage6_exact": {"status": "BLOCKED", "blocked_reason": "relay unavailable"},
            },
            "good": {
                "keyword": "good keyword",
                "terminal_status": "COMPLETE",
                "stage6_exact": {"status": "PASS", "validation_receipt_ref": "exact"},
                "intitle_observation": {"status": "PASS", "validation_receipt_ref": "intitle"},
                "kgr_intitle": {"status": "PASS", "validation_receipt_ref": "kgr"},
                "serp_review": {"status": "PASS", "validation_receipt_ref": "serp"},
                "finalist_trend": {"status": "PASS", "validation_receipt_ref": "trend"},
            },
        },
    }
    valid, reason = hook._verify_completion_requirements(manifest)
    assert valid is True, reason


def test_deterministic_exact_elimination_skips_kgr_and_serp(monkeypatch):
    hook = load_hook("exact_elimination_terminal")
    monkeypatch.setattr(hook, "_verify_validation_receipt", lambda *args, **kwargs: (True, ""))
    monkeypatch.setattr(
        hook, "_verified_exact_disposition", lambda *args, **kwargs: ("principle_eliminate_kd", "")
    )
    manifest = {
        "run_id": "r-eliminated",
        "route": "traditional",
        "status": "COMPLETE",
        "stages": {
            "discovery_autocomplete": {"status": "PASS", "validation_receipt_ref": "auto"},
            "discovery_handoff": {"status": "PASS", "validation_receipt_ref": "handoff"},
        },
        "candidates": {
            "eliminated": {
                "keyword": "eliminated keyword",
                "stage6_exact": {"status": "PASS", "validation_receipt_ref": "exact"},
            }
        },
    }
    valid, reason = hook._verify_completion_requirements(manifest)
    assert valid is True, reason
