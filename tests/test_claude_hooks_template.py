"""Contract for the global wiring template merged into ~/.claude/settings.json.

The repository's own .claude/settings.json only covers sessions opened inside
this checkout. The skills are installed globally (~/.claude/skills symlinks)
and are used from other projects, so the gate needs a global entry as well or
it is absent exactly where the work happens.

The global wrapper therefore differs from the per-repository one: it does not
`cd`. The hook resolves `.seo-run/active.json` relative to the working
directory, so staying put is what lets each project own its run manifest.

The template intentionally names the conventional global install path
`$HOME/code/SEO-Skills`. Tests simulate that install layout with a temporary
HOME pointing back to the current checkout, so the contract is valid both on a
developer machine and on GitHub runners whose checkout lives elsewhere.
"""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "runtime" / "claude_hooks.template.json"
HOOK = ROOT / "runtime" / "stage_hook.py"
REQUIRED_EVENTS = ("PreToolUse", "Stop", "SubagentStop")
INSTALL_RELATIVE = Path("code") / "SEO-Skills"

UNRELATED = "npm run build"
PROTECTED = "python3 runtime/collectors/google_live_collector.py intitle --keyword x"

pytestmark = pytest.mark.skipif(
    shutil.which("python3") is None,
    reason="wrapper contract needs python3 on PATH",
)


def _hooks():
    return json.loads(TEMPLATE.read_text(encoding="utf-8"))["hooks"]


def _command(event="PreToolUse"):
    return _hooks()[event][0]["hooks"][0]["command"]


def _install_checkout(home):
    install = Path(home) / INSTALL_RELATIVE
    install.parent.mkdir(parents=True, exist_ok=True)
    install.symlink_to(ROOT, target_is_directory=True)
    return install


def _run(cwd, tool_command=UNRELATED, event="PreToolUse", manifest=None):
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": tool_command}})
    env = dict(os.environ)
    if manifest is None:
        # Exercise the default relative path so cwd-scoping is what is tested.
        env.pop("SEO_RUN_MANIFEST", None)
    else:
        env["SEO_RUN_MANIFEST"] = str(manifest)
    with tempfile.TemporaryDirectory(prefix="seo-hook-home-") as home:
        _install_checkout(home)
        env["HOME"] = home
        return subprocess.run(
            _command(event),
            shell=True,
            cwd=str(cwd),
            input=payload,
            capture_output=True,
            text=True,
            env=env,
        ).returncode


def test_every_required_event_is_present():
    hooks = _hooks()
    for event in REQUIRED_EVENTS:
        assert event in hooks, f"{event} missing; runs in that context would be unguarded"


def test_pretooluse_is_scoped_to_bash():
    assert _hooks()["PreToolUse"][0]["matcher"] == "^Bash$"


def test_subagent_stop_reuses_the_stop_entrypoint():
    """Stop only fires for the main agent; without this a subagent bypasses the gate."""
    assert _command("SubagentStop").endswith('exec python3 "$H" stop')


def test_commands_guard_their_preconditions():
    for event in REQUIRED_EVENTS:
        command = _command(event)
        assert '[ -f "$H" ] || exit 0' in command
        assert "command -v python3 >/dev/null 2>&1 || exit 0" in command


def test_commands_do_not_cd():
    """cd would resolve .seo-run/active.json against this repo, not the user's project."""
    for event in REQUIRED_EVENTS:
        assert "cd " not in _command(event)


def test_template_path_resolves_to_the_installed_checkout(tmp_path):
    command = _command()
    referenced = command.split('H="', 1)[1].split('"', 1)[0]
    home = tmp_path / "home"
    install = _install_checkout(home)
    resolved = Path(referenced.replace("$HOME", str(home))).resolve()
    assert resolved == HOOK.resolve(), (
        f"template path {referenced} does not resolve to {HOOK} under the supported "
        f"install layout {install}"
    )


def test_unrelated_command_is_allowed_anywhere(tmp_path):
    assert _run(tmp_path) == 0
    assert _run(ROOT) == 0


def test_protected_command_is_denied_without_a_run(tmp_path):
    assert _run(tmp_path, tool_command=PROTECTED) == 2


def test_manifest_is_resolved_against_the_current_project(tmp_path):
    """A run in the user's project must be seen without SEO_RUN_MANIFEST set."""
    project = tmp_path / "some-website"
    (project / ".seo-run").mkdir(parents=True)
    (project / ".seo-run" / "active.json").write_text(
        json.dumps(
            {
                "schema": "seo-run-manifest/v1",
                "run_id": "template-contract",
                "status": "IN_PROGRESS",
                "route": "traditional",
                "stages": {},
                "candidates": {},
            }
        ),
        encoding="utf-8",
    )
    assert _run(project, event="Stop") == 2
    # A sibling project with no run of its own stays untouched.
    other = tmp_path / "unrelated-project"
    other.mkdir()
    assert _run(other, event="Stop") == 0


def test_missing_script_allows_instead_of_blocking_every_command(tmp_path):
    """The rename/relocation case: guards must fail open, or all Bash dies everywhere."""
    command = _command().replace("$HOME/code/SEO-Skills", str(tmp_path / "moved-away"))
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": PROTECTED}})
    result = subprocess.run(
        command, shell=True, cwd=str(tmp_path), input=payload, capture_output=True, text=True
    )
    assert result.returncode == 0
