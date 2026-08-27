import importlib.util
import os
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


def test_external_helper_cannot_mint_issuance_or_create_workspace_secret(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SEO_ISSUANCE_SECRET", raising=False)
    binding = load_module("boundary_no_local_mint", BINDING)

    try:
        binding._mint_issuance_proof(
            "semrush_relay_collector",
            "semrush_exact",
            "a" * 64,
            "2026-08-27T00:00:00Z",
        )
    except Exception:
        pass
    else:
        raise AssertionError("ordinary helper code must not be able to mint a trusted issuance proof")

    assert not (tmp_path / ".seo-run" / ".issuance_secret").exists(), (
        "production trust material must never be generated in the agent-writable workspace"
    )


def test_attacker_controlled_env_secret_cannot_mint_trusted_issuance(monkeypatch):
    monkeypatch.setenv("SEO_ISSUANCE_SECRET", "attacker-controlled-secret")
    binding = load_module("boundary_env_secret", BINDING)
    try:
        binding._mint_issuance_proof(
            "stage_validator",
            "stage6_exact",
            "b" * 64,
            "2026-08-27T00:00:00Z",
        )
    except Exception:
        return
    raise AssertionError("an agent-controlled environment variable must not grant signing authority")


def test_agent_readable_workspace_secret_cannot_mint_trusted_issuance(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SEO_ISSUANCE_SECRET", raising=False)
    secret_dir = tmp_path / ".seo-run"
    secret_dir.mkdir()
    (secret_dir / ".issuance_secret").write_text("agent-readable-secret\n", encoding="utf-8")
    binding = load_module("boundary_workspace_secret", BINDING)
    try:
        binding._mint_issuance_proof(
            "google_live_collector",
            "google_intitle",
            "c" * 64,
            "2026-08-27T00:00:00Z",
        )
    except Exception:
        return
    raise AssertionError("an agent-readable workspace file must not grant signing authority")


def test_emerging_route_cannot_be_self_declared_without_trusted_route_attestation():
    hook = load_hook("route_attestation_required")
    stages, error = hook._infer_canonical_required_stages({
        "route": "emerging",
        "status": "COMPLETE",
        "candidates": {"cand_1": {}},
    })
    assert stages is None
    assert "attest" in error.lower() or "handoff" in error.lower() or "route" in error.lower()


def test_traditional_candidate_cannot_hide_finalist_by_setting_false(monkeypatch):
    hook = load_hook("finalist_self_report_rejected")
    monkeypatch.setattr(hook, "_verify_validation_receipt", lambda *args, **kwargs: (True, ""))
    manifest = {
        "route": "traditional",
        "status": "COMPLETE",
        "stages": {
            "discovery_autocomplete": {"status": "PASS", "validation_receipt_ref": "auto"},
            "discovery_handoff": {"status": "PASS", "validation_receipt_ref": "handoff"},
        },
        "candidates": {
            "cand_1": {
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
    assert "finalist" in reason.lower() or "trend" in reason.lower() or "disposition" in reason.lower()


def test_candidate_specific_stages_must_not_fallback_to_global_receipts(monkeypatch):
    hook = load_hook("candidate_global_fallback_rejected")
    monkeypatch.setattr(hook, "_verify_validation_receipt", lambda *args, **kwargs: (True, ""))
    manifest = {
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
        "candidates": {
            "cand_a": {"is_finalist": False},
            "cand_b": {"is_finalist": False},
        },
    }
    valid, reason = hook._verify_completion_requirements(manifest)
    assert valid is False
    assert "candidate" in reason.lower() or "stage6_exact" in reason.lower()


def test_verified_blocked_candidate_does_not_prevent_completed_batch(monkeypatch):
    hook = load_hook("blocked_candidate_terminal")
    monkeypatch.setattr(hook, "_verify_validation_receipt", lambda *args, **kwargs: (True, ""))
    # The repaired hook may use a dedicated helper for terminal BLOCKED receipts.
    monkeypatch.setattr(hook, "_verify_terminal_blocked_candidate", lambda *args, **kwargs: (True, ""), raising=False)
    manifest = {
        "route": "traditional",
        "status": "COMPLETE",
        "stages": {
            "discovery_autocomplete": {"status": "PASS", "validation_receipt_ref": "auto"},
            "discovery_handoff": {"status": "PASS", "validation_receipt_ref": "handoff"},
        },
        "candidates": {
            "blocked": {
                "terminal_status": "BLOCKED",
                "blocked_stage": "stage6_exact",
                "stage6_exact": {"status": "BLOCKED", "validation_receipt_ref": "blocked-receipt"},
            },
            "good": {
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
        hook,
        "_verified_exact_disposition",
        lambda *args, **kwargs: ("principle_eliminate_kd", ""),
        raising=False,
    )
    manifest = {
        "route": "traditional",
        "status": "COMPLETE",
        "stages": {
            "discovery_autocomplete": {"status": "PASS", "validation_receipt_ref": "auto"},
            "discovery_handoff": {"status": "PASS", "validation_receipt_ref": "handoff"},
        },
        "candidates": {
            "eliminated": {
                "stage6_exact": {"status": "PASS", "validation_receipt_ref": "exact"},
            }
        },
    }
    valid, reason = hook._verify_completion_requirements(manifest)
    assert valid is True, reason
