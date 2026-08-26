import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "runtime" / "codex_stage_hook.py"


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


def test_pretooluse_allows_valid_contract(tmp_path):
    manifest = {
        "run_id": "r1",
        "route": "traditional",
        "status": "IN_PROGRESS",
        "stages": {"stage6_exact": {"status": "PASS", "blocked_reason": ""}},
    }
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "SEO_STAGE_REQUIRE=stage6_exact python3 downstream.py"},
    }
    result = run_hook(tmp_path, "pre", payload, manifest)
    assert result.returncode == 0


def test_pretooluse_can_gate_one_candidate_without_blocking_others(tmp_path):
    manifest = {
        "run_id": "r1",
        "route": "traditional",
        "status": "IN_PROGRESS",
        "stages": {},
        "candidates": {
            "good": {"stage6_exact": {"status": "PASS", "blocked_reason": ""}},
            "bad": {"stage6_exact": {"status": "BLOCKED", "blocked_reason": "relay failed"}},
        },
    }
    base = {"hook_event_name": "PreToolUse", "tool_name": "Bash"}
    good = dict(base, tool_input={"command": "SEO_STAGE_REQUIRE=stage6_exact SEO_CANDIDATE_ID=good python3 downstream.py"})
    bad = dict(base, tool_input={"command": "SEO_STAGE_REQUIRE=stage6_exact SEO_CANDIDATE_ID=bad python3 downstream.py"})
    assert run_hook(tmp_path, "pre", good, manifest).returncode == 0
    assert run_hook(tmp_path, "pre", bad, manifest).returncode == 2


def test_stop_blocks_incomplete_active_run(tmp_path):
    manifest = {"run_id": "r1", "route": "traditional", "status": "IN_PROGRESS", "stages": {}}
    payload = {"hook_event_name": "Stop", "stop_hook_active": False, "last_assistant_message": "done"}
    result = run_hook(tmp_path, "stop", payload, manifest)
    assert result.returncode == 2
    assert "IN_PROGRESS" in result.stderr


def test_stop_allows_blocked_run_to_end(tmp_path):
    manifest = {"run_id": "r1", "route": "traditional", "status": "BLOCKED", "stages": {}}
    payload = {"hook_event_name": "Stop", "stop_hook_active": False, "last_assistant_message": "blocked"}
    assert run_hook(tmp_path, "stop", payload, manifest).returncode == 0


def test_stop_hook_active_prevents_recursive_block(tmp_path):
    manifest = {"run_id": "r1", "route": "traditional", "status": "IN_PROGRESS", "stages": {}}
    payload = {"hook_event_name": "Stop", "stop_hook_active": True, "last_assistant_message": "continuing"}
    assert run_hook(tmp_path, "stop", payload, manifest).returncode == 0
