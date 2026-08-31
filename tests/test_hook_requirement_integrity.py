import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "runtime" / "stage_hook.py"


def load_hook(name="hook_requirement_unit"):
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


def test_explicit_fake_marker_cannot_override_protected_inferred_stage(tmp_path):
    manifest = {
        "run_id": "r1",
        "route": "traditional",
        "status": "IN_PROGRESS",
        "stages": {
            "fake_stage": {"status": "PASS"},
            "stage6_exact": {"status": "BLOCKED", "blocked_reason": "real Exact evidence missing"},
        },
    }
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {
            "command": "SEO_STAGE_REQUIRE=fake_stage python3 skills/seo-keyword-selection/scripts/evaluate_candidates.py --input rows.json --stage exact"
        },
    }
    proc = run_hook(tmp_path, "pre", payload, manifest)
    assert proc.returncode == 2
    assert "stage6_exact" in proc.stderr


def test_complete_cannot_use_unknown_fake_requirement(monkeypatch):
    hook = load_hook("fake_requirement_unit")
    monkeypatch.setattr(hook, "_verify_validation_receipt", lambda *args, **kwargs: (True, ""))
    manifest = {
        "run_id": "r2",
        "route": "traditional",
        "status": "COMPLETE",
        "stages": {"fake_stage": {"status": "PASS"}},
    }
    valid, reason = hook._verify_completion_requirements(manifest)
    assert valid is False
    assert "discovery_autocomplete" in reason or "required" in reason.lower()


def test_traditional_route_only_autocomplete_and_exact_is_denied(monkeypatch):
    hook = load_hook("traditional_partial_unit")
    monkeypatch.setattr(hook, "_verify_validation_receipt", lambda *args, **kwargs: (True, ""))
    manifest = {
        "run_id": "r_trad_partial",
        "route": "traditional",
        "status": "COMPLETE",
            "stages": {
                "discovery_autocomplete": {"status": "PASS"},
                "discovery_coverage": {"status": "PASS", "validation_receipt_ref": "coverage"},
                "discovery_handoff": {"status": "PASS", "coverage_receipt_ref": "coverage"},
        },
        "candidates": {
            "cand": {"keyword": "candidate keyword", "stage6_exact": {"status": "PASS"}}
        },
    }
    monkeypatch.setattr(hook, "_verified_exact_disposition", lambda *args, **kwargs: ("do_candidate", ""))
    valid, reason = hook._verify_completion_requirements(manifest)
    assert valid is False
    assert "intitle_observation" in reason


def test_traditional_candidate_can_complete_without_optional_serp(monkeypatch):
    hook = load_hook("traditional_optional_serp_unit")
    monkeypatch.setattr(hook, "_verify_validation_receipt", lambda *args, **kwargs: (True, ""))
    monkeypatch.setattr(hook, "_verified_exact_disposition", lambda *args, **kwargs: ("do_candidate", ""))
    monkeypatch.setattr(hook, "_verify_finalist_disposition", lambda *args, **kwargs: (False, ""))
    manifest = {
        "run_id": "r_trad_optional_serp",
        "route": "traditional",
        "status": "COMPLETE",
        "stages": {
            "discovery_autocomplete": {"status": "PASS"},
            "discovery_coverage": {"status": "PASS", "validation_receipt_ref": "coverage"},
            "discovery_handoff": {"status": "PASS", "coverage_receipt_ref": "coverage"},
        },
        "candidates": {
            "cand": {
                "keyword": "candidate keyword",
                "stage6_exact": {"status": "PASS"},
                "intitle_observation": {"status": "PASS"},
                "kgr_intitle": {"status": "PASS"},
            }
        },
    }

    valid, reason = hook._verify_completion_requirements(manifest)

    assert valid is True, reason


def test_traditional_candidate_can_record_optional_serp_unavailable(monkeypatch):
    hook = load_hook("traditional_serp_unavailable_unit")
    monkeypatch.setattr(hook, "_verify_validation_receipt", lambda *args, **kwargs: (True, ""))
    monkeypatch.setattr(hook, "_verified_exact_disposition", lambda *args, **kwargs: ("do_candidate", ""))
    monkeypatch.setattr(hook, "_verify_finalist_disposition", lambda *args, **kwargs: (False, ""))
    manifest = {
        "run_id": "r_trad_serp_unavailable",
        "route": "traditional",
        "status": "COMPLETE",
        "stages": {
            "discovery_autocomplete": {"status": "PASS"},
            "discovery_coverage": {"status": "PASS", "validation_receipt_ref": "coverage"},
            "discovery_handoff": {"status": "PASS", "coverage_receipt_ref": "coverage"},
        },
        "candidates": {
            "cand": {
                "keyword": "candidate keyword",
                "stage6_exact": {"status": "PASS"},
                "intitle_observation": {"status": "PASS"},
                "kgr_intitle": {"status": "PASS"},
                "serp_review": {
                    "status": "BLOCKED",
                    "blocked_reason": "Google returned /sorry/; no fallback used",
                },
            }
        },
    }

    valid, reason = hook._verify_completion_requirements(manifest)

    assert valid is True, reason


def test_optional_serp_cannot_terminally_block_candidate():
    hook = load_hook("traditional_serp_terminal_candidate_rejected")
    reason = "Google returned /sorry/; no fallback used"
    manifest = {
        "run_id": "r_trad_serp_terminal_candidate",
        "route": "traditional",
        "status": "COMPLETE",
        "candidates": {
            "cand": {
                "keyword": "candidate keyword",
                "terminal_status": "BLOCKED",
                "blocked_stage": "serp_review",
                "blocked_reason": reason,
                "serp_review": {"status": "BLOCKED", "blocked_reason": reason},
            }
        },
    }

    valid, message = hook._verify_terminal_blocked_candidate(
        manifest, "cand", manifest["candidates"]["cand"]
    )

    assert valid is False
    assert "optional" in message.lower()


def test_optional_serp_cannot_terminally_block_run():
    hook = load_hook("traditional_serp_terminal_run_rejected")
    reason = "Google returned /sorry/; no fallback used"
    manifest = {
        "run_id": "r_trad_serp_terminal_run",
        "route": "traditional",
        "status": "BLOCKED",
        "blocked_stage": "serp_review",
        "blocked_reason": reason,
        "stages": {"serp_review": {"status": "BLOCKED", "blocked_reason": reason}},
    }

    valid, message = hook._verify_blocked_run(manifest)

    assert valid is False
    assert "optional" in message.lower()


def test_optional_serp_pass_is_verified_when_present(monkeypatch):
    hook = load_hook("traditional_optional_serp_pass_verification_unit")
    monkeypatch.setattr(hook, "_verify_validation_receipt", lambda *args, **kwargs: (True, ""))
    monkeypatch.setattr(hook, "_verified_exact_disposition", lambda *args, **kwargs: ("do_candidate", ""))
    monkeypatch.setattr(hook, "_verify_finalist_disposition", lambda *args, **kwargs: (False, ""))
    monkeypatch.setattr(
        hook,
        "_verify_candidate_receipt",
        lambda _manifest, _candidate_id, _candidate, _record, stage: (False, "tampered")
        if stage == "serp_review"
        else (True, ""),
    )
    manifest = {
        "run_id": "r_trad_optional_serp_invalid",
        "route": "traditional",
        "status": "COMPLETE",
        "stages": {
            "discovery_autocomplete": {"status": "PASS"},
            "discovery_coverage": {"status": "PASS", "validation_receipt_ref": "coverage"},
            "discovery_handoff": {"status": "PASS", "coverage_receipt_ref": "coverage"},
        },
        "candidates": {
            "cand": {
                "keyword": "candidate keyword",
                "stage6_exact": {"status": "PASS"},
                "intitle_observation": {"status": "PASS"},
                "kgr_intitle": {"status": "PASS"},
                "serp_review": {"status": "PASS", "validation_receipt_ref": "serp"},
            }
        },
    }

    valid, reason = hook._verify_completion_requirements(manifest)

    assert valid is False
    assert "serp_review" in reason
    assert "tampered" in reason


def test_exact_eliminated_candidate_still_verifies_claimed_optional_serp_pass(monkeypatch):
    hook = load_hook("traditional_eliminated_optional_serp_verification_unit")
    monkeypatch.setattr(
        hook, "_verified_exact_disposition", lambda *args, **kwargs: ("principle_eliminate_volume", "")
    )
    monkeypatch.setattr(
        hook, "_verify_candidate_receipt", lambda *args, **kwargs: (False, "tampered")
    )
    manifest = {
        "run_id": "r_trad_eliminated_optional_serp_invalid",
        "route": "traditional",
        "status": "COMPLETE",
        "candidates": {
            "cand": {
                "keyword": "candidate keyword",
                "stage6_exact": {"status": "PASS"},
                "serp_review": {"status": "PASS", "validation_receipt_ref": "serp"},
            }
        },
    }

    valid, reason = hook._verify_candidate_completion(
        manifest, "cand", manifest["candidates"]["cand"]
    )

    assert valid is False
    assert "serp_review" in reason
    assert "tampered" in reason


def test_emerging_route_only_exact_is_denied(monkeypatch):
    hook = load_hook("emerging_partial_unit")
    monkeypatch.setattr(hook, "_verify_route_attestation", lambda *args, **kwargs: (True, ""))
    monkeypatch.setattr(hook, "_verify_validation_receipt", lambda *args, **kwargs: (True, ""))
    monkeypatch.setattr(hook, "_verified_exact_disposition", lambda *args, **kwargs: ("do_candidate", ""))
    manifest = {
        "run_id": "r_emerg_partial",
        "route": "emerging",
        "status": "COMPLETE",
        "stages": {"emerging_radar_run": {"status": "PASS"}},
        "candidates": {"cand": {"stage6_exact": {"status": "PASS"}}},
    }
    valid, reason = hook._verify_completion_requirements(manifest)
    assert valid is False
    assert "intitle_observation" in reason


def test_finalist_without_trends_is_denied(monkeypatch):
    hook = load_hook("finalist_missing_trend_unit")
    monkeypatch.setattr(hook, "_verify_validation_receipt", lambda *args, **kwargs: (True, ""))
    monkeypatch.setattr(hook, "_verified_exact_disposition", lambda *args, **kwargs: ("do_candidate", ""))
    monkeypatch.setattr(hook, "_verify_finalist_disposition", lambda *args, **kwargs: (True, ""))
    manifest = {
        "run_id": "r_trad_finalist_missing_trends",
        "route": "traditional",
        "status": "COMPLETE",
            "stages": {
                "discovery_autocomplete": {"status": "PASS"},
                "discovery_coverage": {"status": "PASS", "validation_receipt_ref": "coverage"},
                "discovery_handoff": {"status": "PASS", "coverage_receipt_ref": "coverage"},
        },
        "candidates": {
            "cand_1": {
                "keyword": "candidate keyword",
                "stage6_exact": {"status": "PASS"},
                "intitle_observation": {"status": "PASS"},
                "kgr_intitle": {"status": "PASS"},
                "serp_review": {"status": "PASS"},
            }
        },
    }
    valid, reason = hook._verify_completion_requirements(manifest)
    assert valid is False
    assert "finalist_trend" in reason
