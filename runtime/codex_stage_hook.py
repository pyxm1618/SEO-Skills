#!/usr/bin/env python3
"""Codex project hook for SEO production-stage integrity.

Protected production transitions infer their required stage from the command
itself. A stage PASS is trusted only when it references a hash-verified
production validation receipt whose underlying collector evidence is still
valid. COMPLETE is trusted only when explicit completion requirements point to
valid production stage receipts.
"""

import hashlib
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BINDING_PATH = ROOT / "evidence_binding.py"
REQUIRE_RE = re.compile(r"(?:^|\s)SEO_STAGE_REQUIRE=([A-Za-z0-9_.-]+)")
CANDIDATE_RE = re.compile(r"(?:^|\s)SEO_CANDIDATE_ID=([^\s]+)")

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

STAGE_EVIDENCE_TYPES = {
    "discovery_autocomplete": "google_autocomplete",
    "discovery_semrush_ideas": "semrush_ideas",
    "stage6_exact": "semrush_exact",
    "intitle_observation": "google_intitle",
    "serp_review": "google_serp",
    "finalist_trend": "google_trends",
}


def _binding():
    spec = importlib.util.spec_from_file_location("seo_evidence_binding_hook", BINDING_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_stdin():
    raw = sys.stdin.read()
    return json.loads(raw) if raw.strip() else {}


def _manifest_path():
    override = os.environ.get("SEO_RUN_MANIFEST")
    return Path(override) if override else Path(".seo-run/active.json")


def _load_manifest():
    path = _manifest_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"SEO run manifest invalid: {exc}", file=sys.stderr)
        raise SystemExit(2)


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


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _verify_current_evidence(report, stage):
    rows = report.get("complete")
    if not isinstance(rows, list) or not rows:
        return False, "validation report contains no complete rows"
    binding = _binding()
    try:
        for row in rows:
            if stage == "kgr_intitle":
                binding.verify_kgr_payload(row)
                continue
            if stage == "finalist_trend" and row.get("is_finalist") is not True:
                continue
            evidence_type = STAGE_EVIDENCE_TYPES.get(stage)
            if evidence_type:
                binding.verify_payload(row, evidence_type)
    except Exception as exc:
        return False, f"underlying evidence invalid: {exc}"
    return True, ""


def _verify_validation_receipt(record, stage, candidate_id=None):
    if not isinstance(record, dict) or record.get("status") != "PASS":
        return False, "stage status is not PASS"
    receipt_ref = str(record.get("validation_receipt_ref") or "").strip()
    if not receipt_ref:
        return False, "PASS lacks validation receipt"
    receipt_path = Path(receipt_ref)
    if not receipt_path.is_file():
        return False, "validation receipt file is missing"
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False, "validation receipt is invalid JSON"
    if receipt.get("schema") != "seo-stage-validation/v1":
        return False, "validation receipt schema mismatch"
    if receipt.get("stage") != stage or receipt.get("status") != "PASS":
        return False, "validation receipt stage/status mismatch"
    if candidate_id is not None and receipt.get("candidate_id") != candidate_id:
        return False, "validation receipt candidate mismatch"
    report_ref = str(receipt.get("report_ref") or "").strip()
    report_path = Path(report_ref)
    if not report_path.is_file():
        return False, "validation report file is missing"
    if _sha256(report_path) != receipt.get("report_sha256"):
        return False, "validation report hash mismatch"
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False, "validation report is invalid JSON"
    if report.get("stage") != stage or report.get("status") != "PASS":
        return False, "validation report stage/status mismatch"
    if report.get("production") is not True:
        return False, "validation report was not produced in production mode"
    if report.get("blocked_count") != 0 or int(report.get("complete_count") or 0) < 1:
        return False, "validation report is not complete"
    if candidate_id is not None and report.get("candidate_id") != candidate_id:
        return False, "validation report candidate mismatch"
    if report.get("validation_receipt_ref") != str(receipt_path):
        return False, "validation report is not bound to this receipt"
    valid, reason = _verify_current_evidence(report, stage)
    if not valid:
        return False, reason
    return True, ""


def _verify_completion_requirements(manifest):
    requirements = manifest.get("completion_requirements")
    if not isinstance(requirements, list) or not requirements:
        return False, "COMPLETE lacks explicit completion_requirements"
    for index, requirement in enumerate(requirements):
        if not isinstance(requirement, dict):
            return False, f"completion requirement {index} is invalid"
        stage = str(requirement.get("stage") or "").strip()
        candidate_id = requirement.get("candidate_id")
        if not stage:
            return False, f"completion requirement {index} lacks stage"
        record = _stage_record(manifest, stage, candidate_id)
        valid, reason = _verify_validation_receipt(record, stage, candidate_id)
        if not valid:
            scope = f" candidate={candidate_id}" if candidate_id else ""
            return False, f"required {stage}{scope} is not verified: {reason}"
    return True, ""


def pre_tool_use(payload, manifest):
    stage, candidate_id = _required_transition(payload)
    if not stage:
        return 0
    if manifest is None:
        print(f"SEO stage gate denied {stage}; active run manifest is missing", file=sys.stderr)
        return 2
    record = _stage_record(manifest, stage, candidate_id)
    status = record.get("status") if isinstance(record, dict) else record
    if status == "PASS":
        valid, receipt_reason = _verify_validation_receipt(record, stage, candidate_id)
        if valid:
            return 0
        scope = f" candidate={candidate_id}" if candidate_id else ""
        print(f"SEO stage gate denied {stage}{scope}; PASS validation receipt invalid: {receipt_reason}", file=sys.stderr)
        return 2
    reason = record.get("blocked_reason", "") if isinstance(record, dict) else ""
    scope = f" candidate={candidate_id}" if candidate_id else ""
    detail = f": {reason}" if reason else ""
    print(f"SEO stage gate denied {stage}{scope}; status={status or 'NOT_RUN'}{detail}", file=sys.stderr)
    return 2


def stop(payload, manifest):
    if manifest is None:
        return 0
    if payload.get("stop_hook_active") is True:
        return 0
    status = str(manifest.get("status") or "IN_PROGRESS")
    if status == "BLOCKED":
        return 0
    if status == "COMPLETE":
        valid, reason = _verify_completion_requirements(manifest)
        if valid:
            return 0
        print(
            f"Active SEO production run {manifest.get('run_id', 'unknown')} cannot be COMPLETE: {reason}",
            file=sys.stderr,
        )
        return 2
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
    return pre_tool_use(payload, manifest) if sys.argv[1] == "pre" else stop(payload, manifest)


if __name__ == "__main__":
    raise SystemExit(main())
