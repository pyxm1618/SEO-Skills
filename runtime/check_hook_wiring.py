#!/usr/bin/env python3
"""Report whether the SEO stage gate is actually wired and behaving.

The gate's worst failure mode is silence: a hook that is not wired, or whose
script path no longer resolves after the hook is renamed or the repository
moves, looks exactly like a hook that is wired and simply has nothing to
complain about. Both leave the agent free to skip real collection with no
visible sign. Renaming `codex_stage_hook.py` to `stage_hook.py` did exactly
this to the global wiring on 2026-09-01.

This check does not trust configuration alone. It resolves the wired command,
then runs it against a throwaway manifest and asserts the exit codes on both
sides of the line: unrelated work must be allowed everywhere, and protected
collection must be denied wherever there is no active run.

Exit code 0 means the gate is active; 1 means it is not.
"""

import argparse
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HOOK_PATH = ROOT / "stage_hook.py"
DEFAULT_SETTINGS = Path.home() / ".claude" / "settings.json"
REQUIRED_EVENTS = ("PreToolUse", "Stop", "SubagentStop")
SCRIPT_RE = re.compile(r'H="([^"]+)"')

UNRELATED = "npm run build"
PROTECTED = "python3 runtime/collectors/google_live_collector.py intitle --keyword x"

ALLOW, DENY = 0, 2


def _load_settings(path):
    if not path.exists():
        return None, f"{path} does not exist"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"{path} is unreadable: {exc}"
    if not isinstance(value, dict):
        return None, f"{path} root must be an object"
    return value, ""


def _wired_commands(settings):
    """Return {event: command} for every wired event, ignoring shape errors."""
    commands = {}
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return commands
    for event in REQUIRED_EVENTS:
        groups = hooks.get(event)
        if not isinstance(groups, list) or not groups:
            continue
        entries = groups[0].get("hooks") if isinstance(groups[0], dict) else None
        if not isinstance(entries, list) or not entries:
            continue
        command = entries[0].get("command") if isinstance(entries[0], dict) else None
        if isinstance(command, str) and command.strip():
            commands[event] = command
    return commands


def _referenced_script(command):
    match = SCRIPT_RE.search(command)
    if not match:
        return None
    return Path(os.path.expandvars(match.group(1))).expanduser()


def _run(command, cwd, tool_command, manifest):
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": tool_command}})
    env = dict(os.environ)
    env["SEO_RUN_MANIFEST"] = str(manifest)
    result = subprocess.run(
        command,
        shell=True,
        cwd=str(cwd),
        input=payload,
        capture_output=True,
        text=True,
        env=env,
    )
    return result.returncode


def _behaviour_checks(command):
    """Run the wired command over the cases that define a working gate.

    Wired globally the hook runs everywhere, so location is not what decides an
    outcome -- the command is. Protected collection must be denied in any
    project with no active run, and unrelated work allowed in every project.
    """
    findings = []
    with tempfile.TemporaryDirectory() as tmp:
        absent = Path(tmp) / "no-such-manifest.json"
        cases = (
            ("unrelated command, this repo", ROOT.parent, UNRELATED, ALLOW),
            ("unrelated command, other project", Path(tmp), UNRELATED, ALLOW),
            ("protected command, no active run", ROOT.parent, PROTECTED, DENY),
            ("protected command, other project", Path(tmp), PROTECTED, DENY),
        )
        for label, cwd, tool_command, expected in cases:
            actual = _run(command, cwd, tool_command, absent)
            findings.append((label, expected, actual))
    return findings


def check(settings_path=DEFAULT_SETTINGS):
    lines = ["SEO hook wiring check", f"  settings   {settings_path}"]
    settings, error = _load_settings(settings_path)
    if settings is None:
        lines.append(f"  {error}")
        lines.append("")
        lines.append("VERDICT: NOT WIRED - the gate never runs; nothing enforces real collection.")
        return 1, lines

    commands = _wired_commands(settings)
    missing = [event for event in REQUIRED_EVENTS if event not in commands]
    for event in REQUIRED_EVENTS:
        lines.append(f"  {event:<13} {'wired' if event in commands else 'MISSING'}")
    if not commands:
        lines.append("")
        lines.append("VERDICT: NOT WIRED - no SEO hooks in settings; the gate never runs.")
        return 1, lines

    command = commands.get("PreToolUse") or next(iter(commands.values()))
    script = _referenced_script(command)
    if script is None:
        lines.append("  script     could not be resolved from the wired command")
    else:
        lines.append(f"  script     {script} {'OK' if script.is_file() else 'MISSING'}")
        if not script.is_file():
            lines.append("")
            lines.append(
                "VERDICT: BROKEN - the wired script path does not exist. "
                "If the hook was renamed or the repository moved, update the command in settings."
            )
            return 1, lines
        if script.resolve() != HOOK_PATH.resolve():
            lines.append(f"  note       wired script is not this checkout ({HOOK_PATH})")

    lines.append("  behaviour")
    failures = 0
    for label, expected, actual in _behaviour_checks(command):
        verdict = "OK" if expected == actual else "FAILED"
        failures += expected != actual
        names = {ALLOW: "allow", DENY: "deny"}
        lines.append(
            f"    {label:<34} expected {names.get(expected, expected)}, "
            f"got {names.get(actual, actual)}  {verdict}"
        )

    lines.append("")
    if failures:
        lines.append("VERDICT: BROKEN - the gate is wired but does not behave correctly.")
        return 1, lines
    if missing:
        lines.append(
            f"VERDICT: PARTIAL - working, but {', '.join(missing)} not wired; "
            "runs in those contexts are unguarded."
        )
        return 1, lines
    lines.append("VERDICT: ACTIVE - the gate is wired and enforcing.")
    return 0, lines


def main():
    parser = argparse.ArgumentParser(description="Check that the SEO stage gate is wired and working.")
    parser.add_argument("--settings", help=f"settings file to inspect; defaults to {DEFAULT_SETTINGS}")
    args = parser.parse_args()
    settings_path = Path(args.settings).expanduser() if args.settings else DEFAULT_SETTINGS
    code, lines = check(settings_path)
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
