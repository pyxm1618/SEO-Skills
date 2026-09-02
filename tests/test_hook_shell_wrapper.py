"""Behavioural contract for the hook's shell wrapper.

tests/test_claude_hooks_config.py asserts the wrapper's shape; this file runs
it. Both halves matter and they fail for opposite reasons:

- Without the environment guards, `git rev-parse` fails outside the repository,
  `python3` is handed a path that does not exist, and its exit code 2 is
  indistinguishable from the gate's deny code -- every Bash call in every other
  project is blocked.
- With a guard that is too broad (wrapping the whole command in `|| exit 0`),
  real denials are swallowed too and the gate silently becomes decorative.

So each case below pins an exit code on both sides of that line.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / ".codex" / "hooks.json"

UNRELATED = "npm run build"
PROTECTED = "python3 runtime/collectors/google_live_collector.py intitle --keyword x"

pytestmark = pytest.mark.skipif(
    shutil.which("python3") is None or shutil.which("git") is None,
    reason="wrapper contract needs python3 and git on PATH",
)


def _command(event="PreToolUse"):
    return json.loads(HOOKS.read_text(encoding="utf-8"))["hooks"][event][0]["hooks"][0]["command"]


def _run(cwd, tool_command=UNRELATED, manifest=None, event="PreToolUse"):
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": tool_command}})
    env = dict(os.environ)
    # Never let a test read or write the repository's real .seo-run/active.json.
    env["SEO_RUN_MANIFEST"] = str(manifest) if manifest else str(Path(cwd) / "no-such-manifest.json")
    return subprocess.run(
        _command(event),
        shell=True,
        cwd=str(cwd),
        input=payload,
        capture_output=True,
        text=True,
        env=env,
    ).returncode


def test_outside_any_git_repository_the_wrapper_allows(tmp_path):
    assert _run(tmp_path) == 0


def test_inside_an_unrelated_git_repository_the_wrapper_allows(tmp_path):
    subprocess.run(["git", "init", "-q", "."], cwd=str(tmp_path), check=True, capture_output=True)
    assert _run(tmp_path) == 0


def test_unrelated_command_in_this_repository_is_allowed():
    assert _run(ROOT) == 0


def test_unrelated_command_is_allowed_from_a_subdirectory():
    assert _run(ROOT / "runtime") == 0


def test_protected_command_is_still_denied():
    """The guards must not swallow a real denial."""
    assert _run(ROOT, tool_command=PROTECTED) == 2


def test_damaged_manifest_does_not_block_unrelated_commands(tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text('{"schema":"seo-run-manifest/v1", BROKEN', encoding="utf-8")
    assert _run(ROOT, manifest=broken) == 0


def test_damaged_manifest_still_fails_closed_for_protected_commands(tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text('{"schema":"seo-run-manifest/v1", BROKEN', encoding="utf-8")
    assert _run(ROOT, tool_command=PROTECTED, manifest=broken) == 2


def test_stop_allows_when_no_run_is_active():
    assert _run(ROOT, event="Stop") == 0


def test_stop_denies_an_in_progress_run(tmp_path):
    manifest = tmp_path / "active.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": "seo-run-manifest/v1",
                "run_id": "wrapper-contract",
                "status": "IN_PROGRESS",
                "route": "traditional",
                "stages": {},
                "candidates": {},
            }
        ),
        encoding="utf-8",
    )
    assert _run(ROOT, manifest=manifest, event="Stop") == 2


def test_stop_outside_the_repository_allows(tmp_path):
    assert _run(tmp_path, event="Stop") == 0
