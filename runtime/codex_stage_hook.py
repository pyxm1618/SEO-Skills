#!/usr/bin/env python3
"""Codex project hook for SEO production-stage execution integrity.

Protected transitions infer their prerequisite stage from the command. PASS
records require validator receipts bound to the current validator source and
report bytes, then their collector evidence is revalidated. COMPLETE is derived
from canonical route/candidate lifecycle state rather than agent-supplied
completion lists. This is a workflow-correctness gate, not an OS security
boundary against a malicious local principal.
"""

import hashlib
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VALIDATOR_PATH = ROOT / "stage_validator.py"
EVALUATOR_PATH = ROOT.parent / "skills" / "seo-keyword-selection" / "scripts" / "evaluate_candidates.py"
REQUIRE_RE = re.compile(r"(?:^|\s)SEO_STAGE_REQUIRE=([A-Za-z0-9_.-]+)")
CANDIDATE_RE = re.compile(r"(?:^|\s)SEO_CANDIDATE_ID=([^\s]+)")

PROTECTED_COMMAND_RULES = (
    (re.compile(r"\bstage_validator\.py\b.*--stage(?:=|\s+)discovery_handoff\b"), "discovery_coverage"),
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
    "discovery_semrush_competitor_organic": "semrush_competitor_organic",
    "stage6_exact": "semrush_exact",
    "intitle_observation": "google_intitle",
    "serp_review": "google_serp",
    "finalist_trend": "google_trends",
}
CANONICAL_STAGES = frozenset(
    set(STAGE_EVIDENCE_TYPES) | {"kgr_intitle", "discovery_coverage", "discovery_handoff"}
)
TRADITIONAL_SHARED_STAGES = ("discovery_autocomplete", "discovery_coverage", "discovery_handoff")
EXACT_TERMINAL_STATUSES = frozenset({"principle_eliminate_volume", "principle_eliminate_kd", "excluded_manual"})
CONFIRMED_EMERGING_STATUSES = frozenset({"emerging", "breakout"})


def _load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _validator():
    return _load_module(VALIDATOR_PATH, "seo_stage_validator_hook")


def _evaluator():
    return _load_module(EVALUATOR_PATH, "seo_candidate_evaluator_hook")


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
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"SEO run manifest invalid: {exc}", file=sys.stderr)
        raise SystemExit(2)
    if not isinstance(value, dict):
        print("SEO run manifest invalid: root must be an object", file=sys.stderr)
        raise SystemExit(2)
    return value


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
    return stage_match.group(1) if stage_match else None, candidate_match.group(1) if candidate_match else None


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
    protected_stage = _protected_requirement(payload)
    return protected_stage or explicit_stage, candidate_id


def _stage_record(manifest, stage, candidate_id=None):
    if candidate_id:
        candidates = manifest.get("candidates")
        if not isinstance(candidates, dict):
            return None
        candidate = candidates.get(candidate_id)
        return candidate.get(stage) if isinstance(candidate, dict) else None
    stages = manifest.get("stages")
    return stages.get(stage) if isinstance(stages, dict) else None


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _read_json_ref(value, label):
    if isinstance(value, dict):
        return value
    ref = str(value or "").strip()
    if not ref:
        raise ValueError(f"{label} missing")
    path = Path(ref)
    if not path.is_file():
        raise ValueError(f"{label} file missing")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be an object")
    return payload


def _norm_keyword(value):
    return " ".join(str(value or "").split()).casefold()


def _verify_current_evidence(report, stage):
    rows = report.get("complete")
    if not isinstance(rows, list) or not rows:
        return False, "validation report contains no complete rows"
    if report.get("candidate_id") is not None and len(rows) != 1:
        return False, "candidate-bound validation report must contain exactly one complete row"
    validator = _validator()
    try:
        contracts = json.loads((ROOT / "stage_contracts.json").read_text(encoding="utf-8"))
        for row in rows:
            errors = validator.validate_stage(stage, row, contracts, production=True)
            if errors:
                return False, "underlying evidence invalid: " + " | ".join(errors)
    except Exception as exc:
        return False, f"underlying evidence invalid: {exc}"
    if stage == "discovery_handoff":
        if len(rows) != 1:
            return False, "discovery handoff validation must contain exactly one coverage-bound row"
        return _verify_handoff_coverage_report(rows[0])
    return True, ""


def _verify_handoff_coverage_report(handoff_row):
    coverage_ref = str(handoff_row.get("coverage_receipt_ref") or "").strip()
    if not coverage_ref:
        return False, "discovery handoff lacks coverage_receipt_ref"
    coverage_record = {"status": "PASS", "validation_receipt_ref": coverage_ref}
    coverage_report, reason = _load_validation_report(coverage_record, "discovery_coverage")
    if coverage_report is None:
        return False, f"discovery handoff coverage receipt is not verified: {reason}"
    rows = coverage_report.get("complete")
    if not isinstance(rows, list) or len(rows) != 1:
        return False, "discovery coverage report must contain exactly one complete ledger"
    coverage_row = rows[0]
    if coverage_row.get("coverage_status") != "PASS" or coverage_row.get("formal_handoff_allowed") is not True:
        return False, "discovery coverage is not eligible for formal handoff"
    if _norm_keyword(coverage_row.get("batch_id")) != _norm_keyword(handoff_row.get("batch_id")):
        return False, "discovery handoff batch_id differs from coverage ledger"
    return True, ""


def _load_validation_report(record, stage, candidate_id=None):
    if stage not in CANONICAL_STAGES:
        return None, f"unknown/non-canonical stage: {stage}"
    if not isinstance(record, dict) or record.get("status") != "PASS":
        return None, "stage status is not PASS"
    receipt_ref = str(record.get("validation_receipt_ref") or "").strip()
    if not receipt_ref:
        return None, "PASS lacks validation receipt"
    receipt_path = Path(receipt_ref)
    if not receipt_path.is_file():
        return None, "validation receipt file is missing"
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, "validation receipt is invalid JSON"
    if receipt.get("schema") != "seo-stage-validation/v1":
        return None, "validation receipt schema mismatch"
    if receipt.get("stage") != stage or receipt.get("status") != "PASS":
        return None, "validation receipt stage/status mismatch"
    if candidate_id is not None and receipt.get("candidate_id") != candidate_id:
        return None, "validation receipt candidate mismatch"
    if candidate_id is None and receipt.get("candidate_id") not in (None, ""):
        return None, "global validation receipt must not be candidate-bound"
    if receipt.get("validator_source_sha256") != _sha256(VALIDATOR_PATH):
        return None, "validation receipt validator source hash mismatch"

    report_ref = str(receipt.get("report_ref") or "").strip()
    report_path = Path(report_ref)
    if not report_path.is_file():
        return None, "validation report file is missing"
    if _sha256(report_path) != receipt.get("report_sha256"):
        return None, "validation report hash mismatch"
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, "validation report is invalid JSON"
    if report.get("stage") != stage or report.get("status") != "PASS":
        return None, "validation report stage/status mismatch"
    if report.get("production") is not True:
        return None, "validation report was not produced in production mode"
    if report.get("blocked_count") != 0 or int(report.get("complete_count") or 0) < 1:
        return None, "validation report is not complete"
    if candidate_id is not None and report.get("candidate_id") != candidate_id:
        return None, "validation report candidate mismatch"
    if candidate_id is None and report.get("candidate_id") not in (None, ""):
        return None, "global validation report must not be candidate-bound"
    if report.get("validation_receipt_ref") != str(receipt_path):
        return None, "validation report is not bound to this receipt"
    valid, reason = _verify_current_evidence(report, stage)
    if not valid:
        return None, reason
    return report, ""


def _verify_validation_receipt(record, stage, candidate_id=None):
    report, reason = _load_validation_report(record, stage, candidate_id)
    return report is not None, reason


def _verify_route_attestation(manifest):
    """Backward-compatible name: verify an emerging monitor handoff, not crypto."""
    route = str(manifest.get("route") or "").strip().lower()
    if route == "traditional":
        return True, ""
    if route != "emerging":
        return False, f"COMPLETE has unknown or missing route: {route or 'missing'}"
    candidates = manifest.get("candidates")
    if not isinstance(candidates, dict) or not candidates:
        return False, "emerging route requires candidate set"
    try:
        routed = _read_json_ref(manifest.get("route_handoff_ref"), "emerging route handoff")
    except Exception as exc:
        return False, f"emerging route handoff invalid: {exc}"
    routes = routed.get("routes")
    if not isinstance(routes, list):
        return False, "emerging route handoff must contain routes"

    valid_routes = {}
    for item in routes:
        if not isinstance(item, dict) or item.get("route") != "selection_handoff":
            continue
        if item.get("status") not in CONFIRMED_EMERGING_STATUSES or item.get("root_relation") != "existing_root":
            continue
        handoff = item.get("handoff")
        if not isinstance(handoff, dict):
            continue
        keyword = _norm_keyword(handoff.get("keyword") or item.get("keyword"))
        root_id = str(handoff.get("root_id") or "").strip()
        status = handoff.get("status") or item.get("status")
        if keyword and root_id and status in CONFIRMED_EMERGING_STATUSES:
            valid_routes.setdefault(keyword, []).append(item)

    for candidate_id, candidate in candidates.items():
        if not isinstance(candidate, dict):
            return False, f"emerging candidate={candidate_id} record is invalid"
        keyword = _norm_keyword(candidate.get("keyword"))
        if not keyword:
            return False, f"emerging candidate={candidate_id} lacks keyword"
        matches = valid_routes.get(keyword, [])
        if len(matches) != 1:
            return False, f"emerging candidate={candidate_id} requires exactly one confirmed selection_handoff"
    return True, ""


def _infer_canonical_required_stages(manifest):
    route = str(manifest.get("route") or "").strip().lower()
    if route == "traditional":
        return list(TRADITIONAL_SHARED_STAGES), ""
    if route == "emerging":
        valid, reason = _verify_route_attestation(manifest)
        if not valid:
            return None, reason
        return [], ""
    return None, f"COMPLETE has unknown or missing route: {route or 'missing'}"


def _verified_exact_disposition(manifest, candidate_id):
    record = _stage_record(manifest, "stage6_exact", candidate_id)
    report, reason = _load_validation_report(record, "stage6_exact", candidate_id)
    if report is None:
        return None, reason
    rows = report.get("complete") or []
    if len(rows) != 1:
        return None, "candidate Exact validation must contain exactly one row"
    try:
        evaluated = _evaluator().normalize(rows[0], "exact")
    except Exception as exc:
        return None, f"candidate Exact disposition cannot be derived: {exc}"
    status = str(evaluated.get("mechanical_status") or "").strip()
    if not status:
        return None, "candidate Exact disposition is missing"
    return status, ""


def _verify_finalist_disposition(manifest, candidate_id, candidate):
    trend = _stage_record(manifest, "finalist_trend", candidate_id)
    if isinstance(trend, dict) and trend.get("status") == "PASS":
        valid, reason = _verify_validation_receipt(trend, "finalist_trend", candidate_id)
        if not valid:
            return None, reason
        return True, ""

    review = candidate.get("finalist_review")
    if not isinstance(review, dict):
        return None, "candidate finalist review missing"
    if not isinstance(review.get("is_finalist"), bool):
        return None, "candidate finalist review requires boolean is_finalist"
    reason = str(review.get("reason") or "").strip()
    if not reason:
        return None, "candidate finalist review requires reason"
    return review["is_finalist"], ""


def _verify_terminal_blocked_candidate(manifest, candidate_id, candidate):
    stage = str(candidate.get("blocked_stage") or "").strip()
    if stage not in CANONICAL_STAGES:
        return False, "terminal BLOCKED candidate lacks canonical blocked_stage"
    record = _stage_record(manifest, stage, candidate_id)
    if not isinstance(record, dict) or record.get("status") != "BLOCKED":
        return False, f"terminal BLOCKED candidate stage {stage} is not BLOCKED"
    stage_reason = str(record.get("blocked_reason") or "").strip()
    candidate_reason = str(candidate.get("blocked_reason") or "").strip()
    reason = stage_reason or candidate_reason
    if not reason:
        return False, "terminal BLOCKED candidate lacks real blocked reason"
    if stage_reason and candidate_reason and stage_reason != candidate_reason:
        return False, "terminal BLOCKED candidate reason differs from blocked stage"
    if not str(manifest.get("run_id") or "").strip():
        return False, "terminal BLOCKED candidate requires run_id"
    return True, ""


def _verify_blocked_run(manifest):
    run_id = str(manifest.get("run_id") or "").strip()
    if not run_id:
        return False, "BLOCKED run requires run_id"
    stage = str(manifest.get("blocked_stage") or "").strip()
    reason = str(manifest.get("blocked_reason") or "").strip()
    if stage not in CANONICAL_STAGES:
        return False, "BLOCKED run requires canonical blocked_stage"
    if not reason:
        return False, "BLOCKED run requires blocked_reason"
    route = str(manifest.get("route") or "").strip().lower()
    if route and route not in {"traditional", "emerging"}:
        return False, f"BLOCKED run has unknown route: {route}"
    record = _stage_record(manifest, stage)
    if not isinstance(record, dict) or record.get("status") != "BLOCKED":
        return False, f"BLOCKED run stage {stage} is not recorded as BLOCKED"
    stage_reason = str(record.get("blocked_reason") or "").strip()
    if not stage_reason:
        return False, f"BLOCKED run stage {stage} lacks blocked_reason"
    if stage_reason != reason:
        return False, f"BLOCKED run reason differs from stage {stage} blocker"
    return True, ""


def _verify_candidate_completion(manifest, candidate_id, candidate):
    if not isinstance(candidate, dict):
        return False, f"candidate={candidate_id} record is invalid"

    if str(candidate.get("terminal_status") or "").upper() == "BLOCKED":
        return _verify_terminal_blocked_candidate(manifest, candidate_id, candidate)

    exact_status, reason = _verified_exact_disposition(manifest, candidate_id)
    if exact_status is None:
        return False, f"candidate={candidate_id} stage6_exact is not verified: {reason}"
    if exact_status in EXACT_TERMINAL_STATUSES:
        return True, ""

    for stage in ("intitle_observation", "kgr_intitle", "serp_review"):
        record = _stage_record(manifest, stage, candidate_id)
        if not isinstance(record, dict) or record.get("status") != "PASS":
            return False, f"system required stage {stage} for candidate={candidate_id} is missing or not PASS"
        valid, stage_reason = _verify_validation_receipt(record, stage, candidate_id)
        if not valid:
            return False, f"system required stage {stage} for candidate={candidate_id} is not verified: {stage_reason}"

    is_finalist, reason = _verify_finalist_disposition(manifest, candidate_id, candidate)
    if is_finalist is None:
        return False, f"candidate={candidate_id} finalist disposition is not verified: {reason}"
    if is_finalist:
        trend = _stage_record(manifest, "finalist_trend", candidate_id)
        if not isinstance(trend, dict) or trend.get("status") != "PASS":
            return False, f"system required stage finalist_trend for candidate={candidate_id} is missing or not PASS"
        valid, stage_reason = _verify_validation_receipt(trend, "finalist_trend", candidate_id)
        if not valid:
            return False, f"system required stage finalist_trend for candidate={candidate_id} is not verified: {stage_reason}"
    return True, ""


def _verify_completion_requirements(manifest):
    shared_stages, error = _infer_canonical_required_stages(manifest)
    if error:
        return False, error

    for stage in shared_stages:
        record = _stage_record(manifest, stage)
        if not isinstance(record, dict) or record.get("status") != "PASS":
            return False, f"system required stage {stage} is missing or not PASS"
        valid, reason = _verify_validation_receipt(record, stage)
        if not valid:
            return False, f"system required stage {stage} is not verified: {reason}"

    if str(manifest.get("route") or "").strip().lower() == "traditional":
        coverage_record = _stage_record(manifest, "discovery_coverage")
        handoff_record = _stage_record(manifest, "discovery_handoff")
        coverage_ref = str(coverage_record.get("validation_receipt_ref") or "").strip()
        handoff_coverage_ref = str(handoff_record.get("coverage_receipt_ref") or "").strip()
        if not coverage_ref or not handoff_coverage_ref:
            return False, "discovery handoff must bind to the discovery coverage receipt"
        if coverage_ref != handoff_coverage_ref:
            return False, "discovery handoff coverage receipt differs from verified coverage stage"

    candidates = manifest.get("candidates")
    if not isinstance(candidates, dict):
        candidates = {}
    route = str(manifest.get("route") or "").strip().lower()
    if route == "emerging" and not candidates:
        return False, "emerging COMPLETE requires routed candidates"

    for candidate_id, candidate in candidates.items():
        valid, reason = _verify_candidate_completion(manifest, str(candidate_id), candidate)
        if not valid:
            return False, reason
    return True, ""


def pre_tool_use(payload, manifest):
    stage, candidate_id = _required_transition(payload)
    if not stage:
        return 0
    if stage not in CANONICAL_STAGES:
        print(f"SEO stage gate denied {stage}; unknown/non-canonical stage", file=sys.stderr)
        return 2
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
        valid, reason = _verify_blocked_run(manifest)
        if valid:
            return 0
        print(
            f"Active SEO production run {manifest.get('run_id', 'unknown')} cannot be BLOCKED: {reason}",
            file=sys.stderr,
        )
        return 2
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
