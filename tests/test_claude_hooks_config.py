import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLAUDE = ROOT / ".claude" / "settings.json"
CODEX = ROOT / ".codex" / "hooks.json"
SCRIPT_RE = re.compile(r"runtime/[A-Za-z0-9_.-]+\.py")


def _claude():
    return json.loads(CLAUDE.read_text(encoding="utf-8"))["hooks"]


def _codex():
    return json.loads(CODEX.read_text(encoding="utf-8"))["hooks"]


def _command(hooks, event):
    return hooks[event][0]["hooks"][0]["command"]


def _every_command():
    for hooks in (_claude(), _codex()):
        for event, groups in hooks.items():
            for group in groups:
                for entry in group["hooks"]:
                    yield event, entry["command"]


def test_pretooluse_is_scoped_to_bash_and_runs_from_git_root():
    group = _claude()["PreToolUse"][0]
    assert group.get("matcher") == "^Bash$"
    command = group["hooks"][0]["command"]
    assert "git rev-parse --show-toplevel" in command
    assert 'cd "$ROOT"' in command
    assert command.endswith("exec python3 runtime/stage_hook.py pre")


def test_stop_and_subagent_stop_run_from_git_root():
    hooks = _claude()
    for event in ("Stop", "SubagentStop"):
        command = _command(hooks, event)
        assert "git rev-parse --show-toplevel" in command, event
        assert 'cd "$ROOT"' in command, event
        assert command.endswith("exec python3 runtime/stage_hook.py stop"), event


def test_subagent_stop_gate_is_present():
    # Claude Code's Stop event does not fire for subagents. Without SubagentStop
    # a SEO run executed inside a subagent would escape the completeness gate.
    assert "SubagentStop" in _claude()


def test_claude_and_codex_hook_commands_do_not_drift():
    claude, codex = _claude(), _codex()
    for event in ("PreToolUse", "Stop"):
        assert _command(claude, event) == _command(codex, event), event
    assert claude["PreToolUse"][0]["matcher"] == codex["PreToolUse"][0]["matcher"]


def test_every_wired_hook_script_exists_on_disk():
    # The gate is fail-closed, so a command pointing at a missing script makes
    # every Bash call in that session fail, including the one needed to repair
    # it. Renaming the hook without updating both configs is exactly that.
    seen = set()
    for event, command in _every_command():
        for script in SCRIPT_RE.findall(command):
            seen.add(script)
            assert (ROOT / script).is_file(), f"{event}: {script} is missing"
    assert seen, "no hook commands were inspected"


def test_wrappers_bail_out_before_invoking_a_hook_that_cannot_run():
    """Unmet environment preconditions must exit 0, not fall through to python3.

    Without these guards, running outside the repository makes `git rev-parse`
    fail, `cd ""` a no-op, and python3 exit 2 on a path that does not exist --
    the same code the gate uses to deny, so every Bash call is refused. That is
    the root cause behind both the hook-rename lockout and the ~/Downloads TCC
    outage: the gate had not denied anything, it had failed to start.

    The opposite mistake is just as bad: wrapping the whole command in
    `|| exit 0` swallows real denials and leaves a gate that only ever allows.
    tests/test_hook_shell_wrapper.py pins the exit codes on both sides.
    """
    for event, command in _every_command():
        assert "git rev-parse --show-toplevel 2>/dev/null) || exit 0" in command, event
        assert '[ -f "$ROOT/runtime/stage_hook.py" ] || exit 0' in command, event
        assert "command -v python3 >/dev/null 2>&1 || exit 0" in command, event
