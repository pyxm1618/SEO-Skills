#!/usr/bin/env python3
"""Compatibility shim. The gate now lives in runtime/stage_hook.py.

A host session loads its hook wiring at startup, so a session started before
the rename still invokes this path from memory even after
`.claude/settings.json` / `.codex/hooks.json` were repointed. Because the gate
is fail-closed, deleting this file outright makes every Bash call in such a
session fail, including the one needed to undo it.

This shim forwards to the real hook so old and new wiring behave identically.
Delete it once every session has restarted on the new path.
"""

import runpy
import sys
from pathlib import Path

TARGET = Path(__file__).resolve().parent / "stage_hook.py"

if not TARGET.is_file():
    print(f"SEO stage hook is missing: {TARGET}", file=sys.stderr)
    raise SystemExit(2)

sys.argv[0] = str(TARGET)
runpy.run_path(str(TARGET), run_name="__main__")
