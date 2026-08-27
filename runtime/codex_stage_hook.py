#!/usr/bin/env python3
"""Codex project hook for SEO production-stage integrity.

Protected production transitions infer their required stage from the command
itself. SEO_STAGE_REQUIRE remains available as an explicit override/test helper,
but is not required for enforcement.
"""

import json
import os
import re
import sys
from pathlib import Path


REQUIRE_RE = re.compile(r"(?:^|\s)SEO_STAGE_REQUIRE=([A-Za-z0-9_.-]+)")
CANDIDATE_RE = re.compile(r"(?:^|\s)SEO_CANDIDATE_ID=([^\s]+)")

# Small, explicit map. This is an integrity gate, not a workflow engine.
PROTECTED_COMMAND_RULES = (
    (re.compile(r"\bstage_validator\.py\b.*--stage(?:=|\s+)discovery_handoff\b"), "discovery_autocomplete"),
    (re.compile(r"\bgoogle_live_collector\.py\b.*\bintitle\b"), "stage6_exact"),
    (re.compile(r"\bkgr_evidence_merge\.py\b"), "stage6_exact"),
    (re.compile(r"\bevaluate_candidates\.py\b.*--stage(?:=|\s+)exact\b"), "stage6_exact"),
    (re.compile(r"\bgoogle_live_collector\.py\b.*\bserp\b"), "kgr_intitle"),
    (re.compile(r"\bevaluate_candidates\.py\b.*--stage(?:=|\s+)final\b"), "kgr_intitle"),
    (re.compile(r"\bgoogle_live_collector\.py\b.*\btrends\b"), "serp_review"),
    (re.compile(r"\bstage_validator\.py\b.*--stage(?:=|\s+)finalist_trend\b"), "serp_review"),
)


def _load_stdin():
    raw = sys.stdin.read()
    return json.loads(raw) if raw.strip() else {}


def _manifest_path():
    override = os.environ.get("SEO_RUN_MANIFEST")
    if override:
        return Path(override)
    return Path(".seo-run/active.json")


def _load_manifest():
    path = _manifest_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"SEO run manifest invalid: {exc}", file=sys.stderr)
        raise SystemExit(2)
    return data


def _flatten_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _flatten_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _flatten_strings(item)


def _explicit_requirement(tool_input):
    joined = "\n".join(_flatten_strings(tool_input or {}))
    stage_match = REQUIRE_RE.search(joined)
    candidate_match = CANDIDATE_RE.search(joined)
    return (
        stage_match.group(1) if stage_match else None,
        candidate_match.group(1) if candidate_match else None,
    )


def _protected_requirement(payload):
    tool_name = str(payload.get("tool_name") or "")
    if tool_name.lower() not in {"bash", "shell", "terminal", "command"}:
        return None
    joined = "\n".join(_flatten_strings(payload.get("tool_input") or {}))
    for pattern, stage in PROTECTED_COMMAND_RULES:
        if pattern.search(joined):
            return stage
    return None


def _required_transition(payload):
    explicit_stage, candidate_id = _explicit_requirement(payload.get("tool_input"))
    return explicit_stage or _protected_requirement(payload), candidate_id


def _stage_record(manifest, stage, candidate_id=None):
    if candidate_id:
        return manifest.get("candidates", {}).get(candidate_id, {}).get(stage)
    return manifest.get("stages", {}).get(stage)


def pre_tool_use(payload, manifest):
    stage, candidate_id = _required_transition(payload)
    if not stage:
        return 0
    if manifest is None:
        print(
            f"SEO stage gate denied {stage}; active run manifest is missing",
            file=sys.stderr,
        )
        return 2
    record = _stage_record(manifest, stage, candidate_id)
    status = record.get("status") if isinstance(record, dict) else record
    if status == "PASS":
        return 0
    reason = record.get("blocked_reason", "") if isinstance(record, dict) else ""
    scope = f" candidate={candidate_id}" if candidate_id else ""
    detail = f": {reason}" if reason else ""
    print(
        f"SEO stage gate denied {stage}{scope}; status={status or 'NOT_RUN'}{detail}",
        file=sys.stderr,
    )
    return 2


def stop(payload, manifest):
    if manifest is None:
        return 0
    if payload.get("stop_hook_active") is True:
        return 0
    status = str(manifest.get("status") or "IN_PROGRESS")
    if status in {"COMPLETE", "BLOCKED"}:
        return 0
    print(
        f"Active SEO production run {manifest.get('run_id', 'unknown')} is {status}; "
        "finish required stages or mark the run BLOCKED with the real blocker before stopping.",
        file=sys.stderr,
    )
    return 2


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in {"pre", "stop"}:
        print("usage: codex_stage_hook.py {pre|stop}", file=sys.stderr)
        return 2
    payload = _load_stdin()
    manifest = _load_manifest()
    if sys.argv[1] == "pre":
        return pre_tool_use(payload, manifest)
    return stop(payload, manifest)


if __name__ == "__main__":
    raise SystemExit(main())
