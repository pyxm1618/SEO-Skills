import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "runtime" / "codex_stage_hook.py"


def load_hook(name="codex_stage_hook_unit"):
    spec = importlib.util.spec_from_file_location(name, HOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def test_pretooluse_denies_invalid_preceding_stage(tmp_path):
    manifest = {
        "run_id": "r1",
        "route": "traditional",
        "status": "IN_PROGRESS",
        "stages": {"stage6_exact": {"status": "BLOCKED", "blocked_reason": "missing CPC"}},
    }
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "SEO_STAGE_REQUIRE=stage6_exact python3 downstream.py"},
    }
    result = run_hook(tmp_path, "pre", payload, manifest)
    assert result.returncode == 2
    assert "stage6_exact" in result.stderr
    assert "missing CPC" in result.stderr


def test_pretooluse_allows_valid_contract_mechanically_when_receipt_verifier_passes(monkeypatch):
    hook = load_hook("codex_stage_hook_allow_unit")
    monkeypatch.setattr(hook, "_verify_validation_receipt", lambda record, stage, candidate_id=None: (True, ""))
    manifest = {
        "run_id": "r1",
        "route": "traditional",
        "status": "IN_PROGRESS",
        "stages": {"stage6_exact": {"status": "PASS"}},
    }
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "SEO_STAGE_REQUIRE=stage6_exact python3 downstream.py"},
    }
    assert hook.pre_tool_use(payload, manifest) == 0


def test_pretooluse_can_gate_one_candidate_without_blocking_others_mechanically(monkeypatch):
    hook = load_hook("codex_stage_hook_candidate_unit")
    monkeypatch.setattr(
        hook,
        "_verify_validation_receipt",
        lambda record, stage, candidate_id=None: ((candidate_id == "good"), "synthetic unit verifier"),
    )
    manifest = {
        "run_id": "r1",
        "route": "traditional",
        "status": "IN_PROGRESS",
        "stages": {},
        "candidates": {
            "good": {"stage6_exact": {"status": "PASS"}},
            "bad": {"stage6_exact": {"status": "BLOCKED", "blocked_reason": "relay failed"}},
        },
    }
    base = {"hook_event_name": "PreToolUse", "tool_name": "Bash"}
    good = dict(base, tool_input={"command": "SEO_STAGE_REQUIRE=stage6_exact SEO_CANDIDATE_ID=good python3 downstream.py"})
    bad = dict(base, tool_input={"command": "SEO_STAGE_REQUIRE=stage6_exact SEO_CANDIDATE_ID=bad python3 downstream.py"})
    assert hook.pre_tool_use(good, manifest) == 0
    assert hook.pre_tool_use(bad, manifest) == 2


def test_stop_blocks_incomplete_active_run(tmp_path):
    manifest = {"run_id": "r1", "route": "traditional", "status": "IN_PROGRESS", "stages": {}}
    payload = {"hook_event_name": "Stop", "stop_hook_active": False, "last_assistant_message": "done"}
    result = run_hook(tmp_path, "stop", payload, manifest)
    assert result.returncode == 2
    assert "IN_PROGRESS" in result.stderr


def test_stop_rejects_bare_unattested_blocked_run(tmp_path):
    manifest = {"run_id": "r1", "route": "traditional", "status": "BLOCKED", "stages": {}}
    payload = {"hook_event_name": "Stop", "stop_hook_active": False, "last_assistant_message": "blocked"}
    result = run_hook(tmp_path, "stop", payload, manifest)
    assert result.returncode == 2
    assert "BLOCKED" in result.stderr


def test_stop_allows_self_verified_missing_broker_blocker(monkeypatch):
    hook = load_hook("blocked_run_missing_broker")

    class MissingBrokerBinding:
        @staticmethod
        def _trusted_broker_path():
            raise RuntimeError("trusted issuance broker unavailable")

        @staticmethod
        def verify_external_attestation(*_args, **_kwargs):
            raise AssertionError("missing-broker bootstrap must not require broker attestation")

    monkeypatch.setattr(hook, "_binding", lambda: MissingBrokerBinding())
    manifest = {
        "run_id": "r1",
        "route": "traditional",
        "status": "BLOCKED",
        "blocked_stage": "trust_boundary",
        "blocked_reason": "trusted issuance broker unavailable",
    }
    payload = {"hook_event_name": "Stop", "stop_hook_active": False}
    assert hook.stop(payload, manifest) == 0


def test_stop_rejects_non_bootstrap_blocker_without_attestation(monkeypatch):
    hook = load_hook("blocked_run_attestation_required")

    class TrustedBrokerBinding:
        @staticmethod
        def _trusted_broker_path():
            return Path("/trusted/seo-issuance-broker")

        @staticmethod
        def verify_external_attestation(*_args, **_kwargs):
            raise RuntimeError("run blocked attestation missing")

    monkeypatch.setattr(hook, "_binding", lambda: TrustedBrokerBinding())
    manifest = {
        "run_id": "r1",
        "route": "traditional",
        "status": "BLOCKED",
        "blocked_stage": "stage6_exact",
        "blocked_reason": "relay unavailable",
    }
    payload = {"hook_event_name": "Stop", "stop_hook_active": False}
    assert hook.stop(payload, manifest) == 2


def test_stop_allows_attested_run_blocker_and_binds_claims(monkeypatch):
    hook = load_hook("blocked_run_attested")
    seen = {}
    proof = {"schema": "seo-external-attestation/v1", "claims": {"opaque": True}}

    class TrustedBrokerBinding:
        @staticmethod
        def _trusted_broker_path():
            return Path("/trusted/seo-issuance-broker")

        @staticmethod
        def verify_external_attestation(actual_proof, kind, expected_claims):
            seen["proof"] = actual_proof
            seen["kind"] = kind
            seen["claims"] = expected_claims
            return True

    monkeypatch.setattr(hook, "_binding", lambda: TrustedBrokerBinding())
    manifest = {
        "run_id": "r1",
        "route": "traditional",
        "status": "BLOCKED",
        "blocked_stage": "stage6_exact",
        "blocked_reason": "relay unavailable",
        "blocked_attestation_ref": proof,
    }
    payload = {"hook_event_name": "Stop", "stop_hook_active": False}
    assert hook.stop(payload, manifest) == 0
    assert seen == {
        "proof": proof,
        "kind": "run_blocked",
        "claims": {
            "run_id": "r1",
            "route": "traditional",
            "terminal_status": "BLOCKED",
            "blocked_stage": "stage6_exact",
            "blocked_reason": "relay unavailable",
        },
    }


def test_stop_rejects_tampered_run_blocker_claims(monkeypatch):
    hook = load_hook("blocked_run_tampered")
    proof = {
        "schema": "seo-external-attestation/v1",
        "claims": {
            "run_id": "r1",
            "route": "traditional",
            "terminal_status": "BLOCKED",
            "blocked_stage": "stage6_exact",
            "blocked_reason": "original blocker",
        },
    }

    class TrustedBrokerBinding:
        @staticmethod
        def _trusted_broker_path():
            return Path("/trusted/seo-issuance-broker")

        @staticmethod
        def verify_external_attestation(actual_proof, kind, expected_claims):
            if actual_proof.get("claims") != expected_claims:
                raise RuntimeError("run blocked attestation rejected")
            return True

    monkeypatch.setattr(hook, "_binding", lambda: TrustedBrokerBinding())
    manifest = {
        "run_id": "r1",
        "route": "traditional",
        "status": "BLOCKED",
        "blocked_stage": "stage6_exact",
        "blocked_reason": "tampered blocker",
        "blocked_attestation_ref": proof,
    }
    payload = {"hook_event_name": "Stop", "stop_hook_active": False}
    assert hook.stop(payload, manifest) == 2


def test_stop_hook_active_prevents_recursive_block(tmp_path):
    manifest = {"run_id": "r1", "route": "traditional", "status": "IN_PROGRESS", "stages": {}}
    payload = {"hook_event_name": "Stop", "stop_hook_active": True, "last_assistant_message": "continuing"}
    assert run_hook(tmp_path, "stop", payload, manifest).returncode == 0
