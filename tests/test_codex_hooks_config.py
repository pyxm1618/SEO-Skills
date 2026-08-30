import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / ".codex" / "hooks.json"


def _hooks():
    return json.loads(HOOKS.read_text(encoding="utf-8"))["hooks"]


def test_pretooluse_is_scoped_to_bash_and_runs_from_git_root():
    group = _hooks()["PreToolUse"][0]
    assert group.get("matcher") == "^Bash$"
    command = group["hooks"][0]["command"]
    assert command.startswith('cd "$(git rev-parse --show-toplevel)" && ')
    assert command.endswith("python3 runtime/stage_hook.py pre")


def test_stop_runs_from_git_root():
    group = _hooks()["Stop"][0]
    command = group["hooks"][0]["command"]
    assert command.startswith('cd "$(git rev-parse --show-toplevel)" && ')
    assert command.endswith("python3 runtime/stage_hook.py stop")
