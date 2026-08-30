#!/usr/bin/env python3
"""Host-neutral project hook for SEO production-stage execution integrity.

This gate is shared by every host. Only the wiring is host-specific
(`.claude/settings.json`, `.codex/hooks.json`); the logic below is identical
for all of them, and a host without an equivalent hook mechanism is an
unsupported host rather than a released one.

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
EMERGING_PIPELINE_PATH = ROOT / "emerging_pipeline.py"
EMERGING_SCRIPT_PATHS = {
    "validate_observations.py": ROOT.parent / "skills" / "emerging-keyword-monitor" / "scripts" / "validate_observations.py",
    "birth_history.py": ROOT.parent / "skills" / "emerging-keyword-monitor" / "scripts" / "birth_history.py",
    "aggregate_signals.py": ROOT.parent / "skills" / "emerging-keyword-monitor" / "scripts" / "aggregate_signals.py",
    "classify_emergence.py": ROOT.parent / "skills" / "emerging-keyword-monitor" / "scripts" / "classify_emergence.py",
    "route_candidates.py": ROOT.parent / "skills" / "emerging-keyword-monitor" / "scripts" / "route_candidates.py",
}
EMERGING_THRESHOLDS_PATH = ROOT.parent / "skills" / "emerging-keyword-monitor" / "references" / "thresholds.json"
REQUIRE_RE = re.compile(r"(?:^|\s)SEO_STAGE_REQUIRE=([A-Za-z0-9_.-]+)")
CANDIDATE_RE = re.compile(r"(?:^|\s)SEO_CANDIDATE_ID=([^\s]+)")

PROTECTED_COMMAND_RULES = (
    (re.compile(r"\bstage_validator\.py\b.*--stage(?:=|\s+)discovery_handoff\b"), "discovery_coverage"),
    (re.compile(r"\bstage_validator\.py\b.*--stage(?:=|\s+)stage6_exact\b"), "stage6_exact"),
    (re.compile(r"\bstage_validator\.py\b.*--stage(?:=|\s+)intitle_observation\b"), "intitle_observation"),
    (re.compile(r"\bstage_validator\.py\b.*--stage(?:=|\s+)kgr_intitle\b"), "kgr_intitle"),
    (re.compile(r"\bstage_validator\.py\b.*--stage(?:=|\s+)serp_review\b"), "serp_review"),
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
    "trends_related": "google_trends_related",
    "trends_timeline": "google_trends",
}
CANONICAL_STAGES = frozenset(
    set(STAGE_EVIDENCE_TYPES)
    | {
        "kgr_intitle",
        "discovery_input_manifest",
        "discovery_coverage",
        "discovery_handoff",
        "emerging_radar_run",
    }
)
TRADITIONAL_SHARED_STAGES = ("discovery_autocomplete", "discovery_coverage", "discovery_handoff")
EXACT_TERMINAL_STATUSES = frozenset({"principle_eliminate_volume", "principle_eliminate_kd", "excluded_manual"})
CONFIRMED_EMERGING_STATUSES = frozenset({"emerging", "breakout"})
CANONICAL_EMERGING_SIGNAL_TYPES = frozenset({"net_new", "breakout", "emerging_variant", "unknown"})
CANDIDATE_SCOPED_STAGES = frozenset(
    {"stage6_exact", "intitle_observation", "kgr_intitle", "serp_review", "finalist_trend"}
)
GLOBAL_STAGES = frozenset({"discovery_autocomplete", "discovery_semrush_ideas", "discovery_handoff"})


def _load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _validator():
    return _load_module(VALIDATOR_PATH, "seo_stage_validator_hook")


def _evaluator():
    return _load_module(EVALUATOR_PATH, "seo_candidate_evaluator_hook")


def _emerging_pipeline():
    return _load_module(EMERGING_PIPELINE_PATH, "seo_emerging_pipeline_hook")


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


def _detection_text(value):
    """Normalize only a matching copy; never mutate the command sent to a tool."""
    joined = "\n".join(_flatten_strings(value or {}))
    joined = re.sub(r"\\[ \t]*\r?\n", " ", joined)
    joined = re.sub(r"\r?\n", " ", joined)
    return re.sub(r"\s+", " ", joined).strip()


def _explicit_requirement(tool_input):
    joined = _detection_text(tool_input)
    stage_match = REQUIRE_RE.search(joined)
    candidate_match = CANDIDATE_RE.search(joined)
    return stage_match.group(1) if stage_match else None, candidate_match.group(1) if candidate_match else None


def _protected_requirement(payload):
    tool_name = str(payload.get("tool_name") or "")
    if tool_name.lower() not in {"bash", "shell", "terminal", "command"}:
        return None
    joined = _detection_text(payload.get("tool_input"))
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
    candidate_id = str(candidate_id).strip() if candidate_id not in (None, "") else None
    if candidate_id is not None and receipt.get("candidate_id") != candidate_id:
        return None, "validation receipt candidate mismatch"
    if candidate_id is None and receipt.get("candidate_id") not in (None, ""):
        return None, "global validation receipt must not be candidate-bound"
    if candidate_id is not None:
        receipt_keyword = _norm_keyword(receipt.get("candidate_keyword"))
        if not receipt_keyword:
            return None, "candidate validation receipt lacks candidate keyword"
    elif receipt.get("candidate_keyword") not in (None, ""):
        return None, "global validation receipt must not contain candidate keyword"
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
    if candidate_id is not None:
        rows = report.get("complete")
        if not isinstance(rows, list) or len(rows) != 1:
            return None, "candidate-bound validation report must contain exactly one complete row"
        derived_keyword = _norm_keyword(rows[0].get("keyword")) if isinstance(rows[0], dict) else ""
        report_keyword = _norm_keyword(report.get("candidate_keyword"))
        receipt_keyword = _norm_keyword(receipt.get("candidate_keyword"))
        if not derived_keyword:
            return None, "candidate-bound validation row lacks keyword"
        if not report_keyword:
            return None, "candidate-bound validation report lacks candidate keyword"
        if report_keyword != derived_keyword:
            return None, "candidate validation report keyword is not derived from its complete row"
        if receipt_keyword != report_keyword:
            return None, "candidate validation receipt keyword mismatch"
    elif report.get("candidate_keyword") not in (None, ""):
        return None, "global validation report must not contain candidate keyword"
    if report.get("validation_receipt_ref") != str(receipt_path):
        return None, "validation report is not bound to this receipt"
    valid, reason = _verify_current_evidence(report, stage)
    if not valid:
        return None, reason
    return report, ""


def _verify_validation_receipt(record, stage, candidate_id=None, expected_keyword=None):
    report, reason = _load_validation_report(record, stage, candidate_id)
    if report is not None and candidate_id is not None:
        if not _norm_keyword(expected_keyword):
            return False, "manifest candidate keyword is missing"
        if _norm_keyword(report.get("candidate_keyword")) != _norm_keyword(expected_keyword):
            return False, "candidate validation keyword does not match manifest candidate"
    return report is not None, reason


def _verify_candidate_receipt(manifest, candidate_id, candidate, record, stage):
    if not isinstance(candidate, dict):
        return False, "manifest candidate record is missing"
    expected_keyword = _norm_keyword(candidate.get("keyword"))
    if not expected_keyword:
        return False, "manifest candidate keyword is missing"
    return _verify_validation_receipt(record, stage, candidate_id, expected_keyword)


def _verify_hashed_file(entry, label, expected_path=None):
    if not isinstance(entry, dict):
        return None, f"{label} metadata is missing"
    path_text = str(entry.get("path") or "").strip()
    if not path_text:
        return None, f"{label} path is missing"
    path = Path(path_text)
    if expected_path is not None and path.resolve() != Path(expected_path).resolve():
        return None, f"{label} path is not canonical"
    if not path.is_file():
        return None, f"{label} file is missing"
    expected_hash = str(entry.get("sha256") or "").strip()
    if not expected_hash:
        return None, f"{label} hash is missing"
    try:
        actual_hash = _sha256(path)
    except OSError as exc:
        return None, f"{label} cannot be read: {exc}"
    if actual_hash != expected_hash:
        return None, f"{label} hash mismatch"
    return path, ""


def _read_json_file(path, label):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} invalid JSON: {exc}") from exc


def _route_items(manifest):
    try:
        routed = _read_json_ref(manifest.get("route_handoff_ref"), "emerging route handoff")
    except Exception:
        return []
    routes = routed.get("routes")
    return routes if isinstance(routes, list) else []


def _verify_route_attestation(manifest):
    """Verify an Emerging handoff by replaying the complete monitor pipeline."""
    route = str(manifest.get("route") or "").strip().lower()
    if route == "traditional":
        return True, ""
    if route != "emerging":
        return False, f"COMPLETE has unknown or missing route: {route or 'missing'}"
    receipt_ref = str(manifest.get("emerging_pipeline_receipt_ref") or "").strip()
    if not receipt_ref:
        return False, "emerging route requires a complete pipeline receipt"
    receipt_path = Path(receipt_ref)
    try:
        receipt = _read_json_file(receipt_path, "emerging pipeline receipt")
    except Exception as exc:
        return False, str(exc)
    if not isinstance(receipt, dict) or receipt.get("schema") != "seo-emerging-pipeline/v1":
        return False, "emerging pipeline receipt schema mismatch"

    try:
        pipeline = _emerging_pipeline()
        as_of = pipeline.parse_as_of(str(receipt.get("as_of") or ""))
        input_path, input_reason = _verify_hashed_file(receipt.get("observation_input"), "emerging observation input")
        if input_path is None:
            return False, input_reason
        pipeline_path, reason = _verify_hashed_file(
            receipt.get("pipeline"), "emerging pipeline runner", EMERGING_PIPELINE_PATH
        )
        if pipeline_path is None:
            return False, reason
        scripts = receipt.get("scripts")
        if not isinstance(scripts, dict):
            return False, "emerging pipeline script hashes are missing"
        for name, expected_path in EMERGING_SCRIPT_PATHS.items():
            path, reason = _verify_hashed_file(scripts.get(name), f"emerging {name}", expected_path)
            if path is None:
                return False, reason
        thresholds_path, reason = _verify_hashed_file(
            receipt.get("thresholds"), "emerging thresholds", EMERGING_THRESHOLDS_PATH
        )
        if thresholds_path is None:
            return False, reason

        output_entries = receipt.get("outputs")
        if not isinstance(output_entries, dict):
            return False, "emerging pipeline output hashes are missing"
        output_paths = {}
        for name in ("validated", "aggregated", "classified", "routed"):
            output_path, reason = _verify_hashed_file(output_entries.get(name), f"emerging {name} output")
            if output_path is None:
                return False, reason
            output_paths[name] = output_path
        route_ref = str(manifest.get("route_handoff_ref") or "").strip()
        if not route_ref or Path(route_ref).resolve() != output_paths["routed"].resolve():
            return False, "manifest route_handoff_ref is not the attested routed output"

        saved_outputs = {
            name: _read_json_file(path, f"emerging {name} output") for name, path in output_paths.items()
        }
        for name, expected_type in (
            ("validated", dict),
            ("aggregated", dict),
            ("classified", dict),
            ("routed", dict),
        ):
            if not isinstance(saved_outputs[name], expected_type):
                return False, f"emerging {name} output must be an object"
        replayed = pipeline.replay_pipeline(input_path, as_of)
        for name in replayed:
            if saved_outputs[name] != replayed[name]:
                return False, f"emerging {name} output differs from deterministic replay"
    except Exception as exc:
        return False, f"emerging pipeline attestation invalid: {exc}"

    classified_candidates = saved_outputs["classified"].get("candidates")
    routes = saved_outputs["routed"].get("routes")
    if not isinstance(classified_candidates, list) or not isinstance(routes, list):
        return False, "emerging pipeline outputs have invalid candidate/route lists"
    for candidate in classified_candidates:
        if not isinstance(candidate, dict):
            return False, "emerging classified candidate is invalid"
        signal_type = candidate.get("signal_type")
        if signal_type is not None and signal_type not in CANONICAL_EMERGING_SIGNAL_TYPES:
            return False, f"emerging candidate has non-canonical signal_type={signal_type}"

    selection_routes = []
    for item in routes:
        if not isinstance(item, dict):
            return False, "emerging routed candidate is invalid"
        if item.get("route") != "selection_handoff":
            continue
        if item.get("status") not in CONFIRMED_EMERGING_STATUSES or item.get("root_relation") != "existing_root":
            return False, "selection_handoff has invalid status or root relation"
        handoff = item.get("handoff")
        if not isinstance(handoff, dict):
            return False, "selection_handoff lacks handoff object"
        keyword = _norm_keyword(item.get("keyword"))
        handoff_keyword = _norm_keyword(handoff.get("keyword"))
        root_id = str(handoff.get("root_id") or "").strip()
        status = str(handoff.get("status") or "").strip().lower()
        signal_type = handoff.get("signal_type")
        if not keyword or keyword != handoff_keyword or not root_id:
            return False, "selection_handoff keyword/root binding is invalid"
        if status not in CONFIRMED_EMERGING_STATUSES or status != str(item.get("status") or "").strip().lower():
            return False, "selection_handoff status binding is invalid"
        if signal_type not in CANONICAL_EMERGING_SIGNAL_TYPES - {"unknown"}:
            return False, "selection_handoff signal_type is not canonical"
        selection_routes.append(item)

    candidates = manifest.get("candidates")
    if candidates is None:
        candidates = {}
    if not isinstance(candidates, dict):
        return False, "emerging manifest candidates must be an object"
    if not candidates and selection_routes:
        return False, "selection_handoff lacks a manifest candidate binding"

    for candidate_id, candidate in candidates.items():
        if not isinstance(candidate, dict):
            return False, f"emerging candidate={candidate_id} record is invalid"
        keyword = _norm_keyword(candidate.get("keyword"))
        if not keyword:
            return False, f"emerging candidate={candidate_id} lacks keyword"
        matches = [item for item in routes if _norm_keyword(item.get("keyword")) == keyword]
        if len(matches) != 1:
            return False, f"emerging candidate={candidate_id} requires exactly one routed record"
        item = matches[0]
        if item.get("route") == "selection_handoff":
            handoff = item["handoff"]
            expected_root = str(candidate.get("root_id") or "").strip()
            expected_status = str(candidate.get("status") or "").strip().lower()
            if not expected_root or expected_root != str(handoff.get("root_id") or "").strip():
                return False, f"emerging candidate={candidate_id} root_id does not match handoff"
            if not expected_status or expected_status != str(handoff.get("status") or "").strip().lower():
                return False, f"emerging candidate={candidate_id} status does not match handoff"
        elif candidate.get("status") is not None:
            if str(candidate.get("status")).strip().lower() != str(item.get("status") or "").strip().lower():
                return False, f"emerging candidate={candidate_id} status does not match routed result"
        if candidate.get("route") is not None and candidate.get("route") != item.get("route"):
            return False, f"emerging candidate={candidate_id} route does not match routed result"
    return True, ""


def _infer_canonical_required_stages(manifest):
    route = str(manifest.get("route") or "").strip().lower()
    if route == "traditional":
        return list(TRADITIONAL_SHARED_STAGES), ""
    if route == "emerging":
        valid, reason = _verify_route_attestation(manifest)
        if not valid:
            return None, reason
        return ["emerging_radar_run"], ""
    return None, f"COMPLETE has unknown or missing route: {route or 'missing'}"


def _verified_exact_disposition(manifest, candidate_id):
    record = _stage_record(manifest, "stage6_exact", candidate_id)
    candidates = manifest.get("candidates")
    candidate = candidates.get(candidate_id) if isinstance(candidates, dict) else None
    expected_keyword = candidate.get("keyword") if isinstance(candidate, dict) else None
    report, reason = _load_validation_report(record, "stage6_exact", candidate_id)
    if report is None:
        return None, reason
    if not _norm_keyword(expected_keyword):
        return None, "manifest candidate keyword is missing"
    if _norm_keyword(report.get("candidate_keyword")) != _norm_keyword(expected_keyword):
        return None, "candidate validation keyword does not match manifest candidate"
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
        valid, reason = _verify_candidate_receipt(manifest, candidate_id, candidate, trend, "finalist_trend")
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
        valid, stage_reason = _verify_candidate_receipt(manifest, candidate_id, candidate, record, stage)
        if not valid:
            return False, f"system required stage {stage} for candidate={candidate_id} is not verified: {stage_reason}"

    is_finalist, reason = _verify_finalist_disposition(manifest, candidate_id, candidate)
    if is_finalist is None:
        return False, f"candidate={candidate_id} finalist disposition is not verified: {reason}"
    if is_finalist:
        trend = _stage_record(manifest, "finalist_trend", candidate_id)
        if not isinstance(trend, dict) or trend.get("status") != "PASS":
            return False, f"system required stage finalist_trend for candidate={candidate_id} is missing or not PASS"
        valid, stage_reason = _verify_candidate_receipt(manifest, candidate_id, candidate, trend, "finalist_trend")
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
        if any(item.get("route") == "selection_handoff" for item in _route_items(manifest) if isinstance(item, dict)):
            return False, "selection_handoff lacks routed candidate lifecycle records"
        return True, ""

    for candidate_id, candidate in candidates.items():
        if route == "emerging":
            routed_matches = [
                item
                for item in _route_items(manifest)
                if isinstance(item, dict) and _norm_keyword(item.get("keyword")) == _norm_keyword(candidate.get("keyword"))
            ]
            if len(routed_matches) == 1 and routed_matches[0].get("route") != "selection_handoff":
                continue
        valid, reason = _verify_candidate_completion(manifest, str(candidate_id), candidate)
        if not valid:
            return False, reason
    return True, ""


def pre_tool_use(payload, manifest):
    stage, candidate_id = _required_transition(payload)
    protected_stage = _protected_requirement(payload)
    if not stage:
        return 0
    if stage not in CANONICAL_STAGES:
        print(f"SEO stage gate denied {stage}; unknown/non-canonical stage", file=sys.stderr)
        return 2
    if manifest is None:
        print(f"SEO stage gate denied {stage}; active run manifest is missing", file=sys.stderr)
        return 2
    if stage in CANDIDATE_SCOPED_STAGES and protected_stage == stage and not candidate_id:
        print(
            f"SEO stage gate denied {stage}; SEO_CANDIDATE_ID is required before a validation receipt can be used",
            file=sys.stderr,
        )
        return 2
    if stage in GLOBAL_STAGES and candidate_id:
        print(f"SEO stage gate denied {stage}; global stages cannot use SEO_CANDIDATE_ID", file=sys.stderr)
        return 2
    record = _stage_record(manifest, stage, candidate_id)
    status = record.get("status") if isinstance(record, dict) else record
    if status == "PASS":
        if candidate_id:
            candidates = manifest.get("candidates")
            candidate = candidates.get(candidate_id) if isinstance(candidates, dict) else None
            valid, receipt_reason = _verify_candidate_receipt(manifest, candidate_id, candidate, record, stage)
        else:
            valid, receipt_reason = _verify_validation_receipt(record, stage)
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
        print("usage: stage_hook.py {pre|stop}", file=sys.stderr)
        return 2
    payload = _load_stdin()
    manifest = _load_manifest()
    return pre_tool_use(payload, manifest) if sys.argv[1] == "pre" else stop(payload, manifest)


if __name__ == "__main__":
    raise SystemExit(main())
