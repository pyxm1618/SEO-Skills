import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "runtime" / "codex_stage_hook.py"


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
            "discovery_handoff": {"status": "PASS"},
        },
        "candidates": {
            "cand": {"stage6_exact": {"status": "PASS"}}
        },
    }
    monkeypatch.setattr(hook, "_verified_exact_disposition", lambda *args, **kwargs: ("do_candidate", ""))
    valid, reason = hook._verify_completion_requirements(manifest)
    assert valid is False
    assert "intitle_observation" in reason


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
            "discovery_handoff": {"status": "PASS"},
        },
        "candidates": {
            "cand_1": {
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
