import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLAUDE = ROOT / ".claude" / "settings.json"
CODEX = ROOT / ".codex" / "hooks.json"
ROOT_PREFIX = 'cd "$(git rev-parse --show-toplevel)" && '


def _claude():
    return json.loads(CLAUDE.read_text(encoding="utf-8"))["hooks"]


def _codex():
    return json.loads(CODEX.read_text(encoding="utf-8"))["hooks"]


def _command(hooks, event):
    return hooks[event][0]["hooks"][0]["command"]


def test_pretooluse_is_scoped_to_bash_and_runs_from_git_root():
    group = _claude()["PreToolUse"][0]
    assert group.get("matcher") == "^Bash$"
    command = group["hooks"][0]["command"]
    assert command.startswith(ROOT_PREFIX)
    assert command.endswith("python3 runtime/stage_hook.py pre")


def test_stop_and_subagent_stop_run_from_git_root():
    hooks = _claude()
    for event in ("Stop", "SubagentStop"):
        command = _command(hooks, event)
        assert command.startswith(ROOT_PREFIX), event
        assert command.endswith("python3 runtime/stage_hook.py stop"), event


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
    for hooks in (_claude(), _codex()):
        for event, groups in hooks.items():
            for group in groups:
                for entry in group["hooks"]:
                    command = entry["command"]
                    script = command.split("python3 ", 1)[1].rsplit(" ", 1)[0]
                    seen.add(script)
                    assert (ROOT / script).is_file(), f"{event}: {script} is missing"
    assert seen, "no hook commands were inspected"
