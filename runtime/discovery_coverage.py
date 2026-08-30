#!/usr/bin/env python3
"""Validate the finite coverage ledger for a Traditional Discovery run.

This module deliberately owns a ledger and a final gate, not a crawler. Source
collectors remain responsible for obtaining real observations; this module
checks that every required acquisition remains represented, that branch seeds
are observed candidates, and that a complete ledger is eligible for handoff.
"""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BINDING_PATH = ROOT / "evidence_binding.py"
STAGE_VALIDATOR_PATH = ROOT / "stage_validator.py"

PASS = "PASS"
BLOCKED = "BLOCKED"
NOT_RUN = "NOT_RUN"
UNKNOWN = "UNKNOWN"
NOT_CONFIGURED = "not_configured"
FULL_DISCOVERY = "full"
DIAGNOSTIC_DISCOVERY = "diagnostic_google_only"

DEFAULT_MAX_BRANCH_DEPTH = 1
DEFAULT_MAX_BRANCH_SEEDS = 20
VALID_ACQUISITION_STATUSES = frozenset({PASS, BLOCKED, NOT_RUN, UNKNOWN})
VALID_DISCOVERY_MODES = frozenset({FULL_DISCOVERY, DIAGNOSTIC_DISCOVERY})
INPUT_MANIFEST_SCHEMA = "seo-discovery-input/v1"
ROOT_HANDOFF_SCHEMA = "seo-root-natural-seeds/v1"
VALID_ANALYSIS_STATUSES = frozenset({"COMPLETE", BLOCKED, NOT_RUN, UNKNOWN})

SOURCE_EVIDENCE_TYPES = {
    "google_autocomplete": "google_autocomplete",
    "semrush_ideas": "semrush_ideas",
    "semrush_competitor_organic": "semrush_competitor_organic",
}

# Step 4 low-risk cleaning only. Opportunity judgement belongs to selection, so
# there is deliberately no "low volume"/"too competitive" style exclusion here.
EXCLUSION_RULE_CODES = frozenset(
    {"brand_or_navigation", "semantic_drift", "non_target_language_or_market"}
)
VALID_ROW_DISPOSITIONS = frozenset({"kept", "dedupe_of", "excluded"})


class CoverageContractError(ValueError):
    """Raised when a branch declaration cannot be made safely."""


def _norm_keyword(value):
    return " ".join(str(value or "").split()).casefold()


def _text(value):
    return str(value or "").strip()


def _status(record):
    if not isinstance(record, dict):
        return ""
    return _text(record.get("status")).upper()


def _reason(record):
    if not isinstance(record, dict):
        return ""
    return _text(record.get("blocked_reason") or record.get("reason"))


def _receipt_ref(record):
    if not isinstance(record, dict):
        return ""
    return _text(record.get("evidence_receipt_ref") or record.get("receipt_ref"))


def _candidate_receipt_ref(candidate):
    return _text(candidate.get("evidence_receipt_ref") or candidate.get("evidence_ref"))


def _candidate_fingerprint(candidate):
    return (
        _text(candidate.get("candidate_id")),
        _norm_keyword(candidate.get("keyword")),
        _text(candidate.get("source")),
        _norm_keyword(candidate.get("source_seed")),
        _text(candidate.get("competitor_domain")).casefold(),
        _candidate_receipt_ref(candidate),
    )


def _analysis_fingerprint(analysis):
    return (
        _text(analysis.get("candidate_id")),
        _text(analysis.get("analysis_status")).upper(),
        analysis.get("branch_required"),
        _text(analysis.get("analysis_reason")),
    )


def _positive_int(value, default, label, issue):
    if value is None:
        return default
    try:
        number = _strict_positive_integer(value)
    except (TypeError, ValueError):
        issue(f"{label}:must_be_positive_integer")
        return default
    return number


def _strict_positive_integer(value):
    if isinstance(value, bool):
        raise ValueError("value must be a positive integer")
    if isinstance(value, int):
        number = value
    elif isinstance(value, str) and value.strip().isdigit():
        number = int(value.strip())
    else:
        raise ValueError("value must be a positive integer")
    if number <= 0:
        raise ValueError("value must be a positive integer")
    return number


def _strict_nonnegative_integer(value):
    if isinstance(value, bool):
        raise ValueError("value must be a non-negative integer")
    if isinstance(value, int):
        number = value
    elif isinstance(value, str) and value.strip().isdigit():
        number = int(value.strip())
    else:
        raise ValueError("value must be a non-negative integer")
    if number < 0:
        raise ValueError("value must be a non-negative integer")
    return number


def _binding():
    spec = importlib.util.spec_from_file_location("seo_discovery_coverage_binding", BINDING_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _observed_keywords(normalized, evidence_type):
    if evidence_type == "google_autocomplete":
        return [_norm_keyword(value) for value in normalized.get("suggestions", [])]
    return [_norm_keyword(row.get("keyword")) for row in normalized.get("rows", []) if isinstance(row, dict)]


def _file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _validate_root_handoff_receipt(manifest):
    receipt_path = Path(_text(manifest.get("root_handoff_receipt_ref")))
    if not receipt_path.is_file():
        return ["input_manifest.root_handoff_receipt_ref:file_missing"]
    expected_hash = _text(manifest.get("root_handoff_receipt_sha256"))
    try:
        actual_hash = _file_sha256(receipt_path)
    except OSError as exc:
        return [f"input_manifest.root_handoff_receipt_ref:unreadable:{exc}"]
    if actual_hash != expected_hash:
        return ["input_manifest.root_handoff_receipt_sha256:hash_mismatch"]
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"input_manifest.root_handoff_receipt_ref:invalid_json:{exc}"]
    if not isinstance(receipt, dict):
        return ["input_manifest.root_handoff_receipt_ref:must_be_object"]
    issues = []
    if receipt.get("schema") != ROOT_HANDOFF_SCHEMA:
        issues.append("input_manifest.root_handoff_receipt_ref:schema_mismatch")
    if receipt.get("status") != PASS:
        issues.append("input_manifest.root_handoff_receipt_ref:status_must_be_PASS")
    if _norm_keyword(receipt.get("batch_id")) != _norm_keyword(manifest.get("batch_id")):
        issues.append("input_manifest.root_handoff_receipt_ref:batch_id_mismatch")
    if receipt.get("seed_plan") != manifest.get("seed_plan"):
        issues.append("input_manifest.root_handoff_receipt_ref:seed_plan_mismatch")
    return issues


def _validate_source_receipts(manifest, inventory_candidates, production, issue):
    """Bind the manifest to its complete source-receipt set and reconcile every observed row.

    The Candidate inventory is the denominator for the whole run, so it may not be
    curated away before signing. Every row a bound receipt actually returned must be
    accounted for exactly once: kept as a Candidate, recorded as a duplicate of a kept
    Candidate, or excluded under a supported cleaning rule.
    """

    receipts = manifest.get("source_receipts")
    if not isinstance(receipts, list) or not receipts:
        issue("input_manifest.source_receipts:complete_receipt_set_required")
        return

    candidates_by_id = {
        _text(candidate.get("candidate_id")): candidate
        for candidate in inventory_candidates
        if isinstance(candidate, dict) and _text(candidate.get("candidate_id"))
    }

    receipt_refs = []
    normalized_by_ref = {}
    for index, record in enumerate(receipts):
        label = f"input_manifest.source_receipts[{index}]"
        if not isinstance(record, dict):
            issue(f"{label}:must_be_object")
            continue
        evidence_type = _text(record.get("evidence_type"))
        ref = _text(record.get("evidence_receipt_ref"))
        if evidence_type not in SOURCE_EVIDENCE_TYPES:
            issue(f"{label}.evidence_type:must_be_real_observed_source")
            continue
        if not ref:
            issue(f"{label}.evidence_receipt_ref:required")
            continue
        if ref in receipt_refs:
            issue(f"{label}.evidence_receipt_ref:duplicate")
            continue
        receipt_refs.append(ref)
        if evidence_type == "semrush_competitor_organic":
            identity_field, identity = "competitor_domain", record.get("competitor_domain")
        else:
            identity_field, identity = "seed", record.get("seed")
        if not _text(identity):
            issue(f"{label}.{identity_field}:required")
            continue
        if production:
            normalized = _verify_receipt(
                ref, SOURCE_EVIDENCE_TYPES[evidence_type], identity_field, identity, label, issue
            )
            if normalized is not None:
                normalized_by_ref[ref] = (evidence_type, normalized)

    for index, candidate in enumerate(inventory_candidates):
        if not isinstance(candidate, dict):
            continue
        ref = _candidate_receipt_ref(candidate)
        if ref and ref not in receipt_refs:
            issue(
                f"input_manifest.candidate_inventory.candidates[{index}]"
                ".evidence_receipt_ref:not_in_source_receipts"
            )

    if not production:
        return

    inventory = manifest.get("candidate_inventory")
    row_ledger = inventory.get("row_ledger") if isinstance(inventory, dict) else None
    if not isinstance(row_ledger, list):
        issue("input_manifest.candidate_inventory:row_ledger_required_for_source_receipts")
        return

    prefix = "input_manifest.candidate_inventory.row_ledger"
    ledger_by_ref = _index_row_ledger(row_ledger, prefix, issue)
    kept_candidate_ids = _reconcile_row_ledger(
        normalized_by_ref, ledger_by_ref, candidates_by_id, prefix, issue
    )
    if set(candidates_by_id) - kept_candidate_ids:
        issue("input_manifest.candidate_inventory:candidates_without_a_kept_source_row")


def _index_row_ledger(row_ledger, prefix, issue):
    indexed = {}
    for index, record in enumerate(row_ledger):
        label = f"{prefix}[{index}]"
        if not isinstance(record, dict):
            issue(f"{label}:must_be_object")
            continue
        ref = _text(record.get("evidence_receipt_ref"))
        if not ref:
            issue(f"{label}.evidence_receipt_ref:required")
        elif ref in indexed:
            issue(f"{label}.evidence_receipt_ref:duplicate")
        else:
            indexed[ref] = record
    return indexed


def _reconcile_row_ledger(normalized_by_ref, ledger_by_ref, candidates_by_id, prefix, issue):
    """Account for every observed row exactly once and return the kept candidate ids."""

    kept_candidate_ids = set()
    if set(ledger_by_ref) != set(normalized_by_ref):
        issue(f"{prefix}:must_cover_exact_source_receipt_set")
    for ref, (evidence_type, normalized) in normalized_by_ref.items():
        record = ledger_by_ref.get(ref)
        if record is None:
            continue
        label = f"{prefix}[{ref}]"
        observed = _observed_keywords(normalized, SOURCE_EVIDENCE_TYPES[evidence_type])
        rows = record.get("rows")
        if not isinstance(rows, list):
            issue(f"{label}.rows:must_be_list")
            continue
        declared = [
            _norm_keyword(row.get("keyword")) if isinstance(row, dict) else None for row in rows
        ]
        if declared != observed:
            issue(f"{label}.rows:must_match_observed_source_rows_in_order")
            continue
        for position, row in enumerate(rows):
            row_label = f"{label}.rows[{position}]"
            disposition = _text(row.get("disposition"))
            if disposition not in VALID_ROW_DISPOSITIONS:
                issue(f"{row_label}.disposition:must_be_kept_dedupe_of_or_excluded")
                continue
            if disposition == "excluded":
                if _text(row.get("rule_code")) not in EXCLUSION_RULE_CODES:
                    issue(f"{row_label}.rule_code:must_be_supported_cleaning_rule")
                if not _text(row.get("reason")):
                    issue(f"{row_label}.reason:required")
                continue
            candidate = candidates_by_id.get(_text(row.get("candidate_id")))
            if candidate is None:
                issue(f"{row_label}.candidate_id:must_resolve_to_inventory_candidate")
                continue
            # Recompute the duplicate relation rather than trusting the declaration.
            if _norm_keyword(candidate.get("keyword")) != observed[position]:
                issue(f"{row_label}.candidate_id:keyword_differs_from_observed_row")
                continue
            if disposition == "kept":
                if _candidate_receipt_ref(candidate) != ref:
                    issue(f"{row_label}.candidate_id:kept_candidate_must_cite_this_receipt")
                elif _text(row.get("candidate_id")) in kept_candidate_ids:
                    issue(f"{row_label}.candidate_id:kept_more_than_once")
                else:
                    kept_candidate_ids.add(_text(row.get("candidate_id")))
    return kept_candidate_ids


def validate_input_manifest(manifest, production=False):
    """Validate the finite Root/Natural Seeds handoff consumed by Coverage."""

    issues = []

    def issue(message):
        if message not in issues:
            issues.append(message)

    if not isinstance(manifest, dict):
        return ["input_manifest:must_be_object"]
    if _text(manifest.get("schema")) != INPUT_MANIFEST_SCHEMA:
        issue(f"input_manifest.schema:must_equal:{INPUT_MANIFEST_SCHEMA}")
    if not _text(manifest.get("batch_id")):
        issue("input_manifest.batch_id:required")
    root_receipt_ref = _text(manifest.get("root_handoff_receipt_ref"))
    if not root_receipt_ref:
        issue("input_manifest.root_handoff_receipt_ref:required")
    elif production:
        for error in _validate_root_handoff_receipt(manifest):
            issue(error)
    root_receipt_hash = _text(manifest.get("root_handoff_receipt_sha256"))
    if len(root_receipt_hash) != 64 or any(character not in "0123456789abcdefABCDEF" for character in root_receipt_hash):
        issue("input_manifest.root_handoff_receipt_sha256:must_be_sha256")

    seed_plan = manifest.get("seed_plan")
    if not isinstance(seed_plan, dict):
        issue("input_manifest.seed_plan:must_be_object")
    else:
        try:
            original_seed_count = _strict_positive_integer(seed_plan.get("original_seed_count"))
        except (TypeError, ValueError):
            original_seed_count = None
            issue("input_manifest.seed_plan.original_seed_count:must_be_positive_integer")
        seeds = seed_plan.get("seeds")
        if not isinstance(seeds, list):
            issue("input_manifest.seed_plan.seeds:must_be_list")
            seeds = []
        if original_seed_count is not None and len(seeds) != original_seed_count:
            issue("input_manifest.seed_plan:original_seed_count_mismatch")
        seen_seeds = set()
        for index, seed in enumerate(seeds):
            seed_key = _norm_keyword(seed)
            if not seed_key:
                issue(f"input_manifest.seed_plan.seeds[{index}]:must_be_nonempty")
            elif seed_key in seen_seeds:
                issue(f"input_manifest.seed_plan.seeds[{index}]:duplicate")
            else:
                seen_seeds.add(seed_key)

    candidate_inventory = manifest.get("candidate_inventory")
    inventory_candidates = []
    if not isinstance(candidate_inventory, dict):
        issue("input_manifest.candidate_inventory:must_be_object")
    else:
        try:
            original_candidate_count = _strict_nonnegative_integer(
                candidate_inventory.get("original_candidate_count")
            )
        except (TypeError, ValueError):
            original_candidate_count = None
            issue("input_manifest.candidate_inventory.original_candidate_count:must_be_nonnegative_integer")
        inventory_candidates = candidate_inventory.get("candidates")
        if not isinstance(inventory_candidates, list):
            issue("input_manifest.candidate_inventory.candidates:must_be_list")
            inventory_candidates = []
        if original_candidate_count is not None and len(inventory_candidates) != original_candidate_count:
            issue("input_manifest.candidate_inventory:original_candidate_count_mismatch")
        seen_candidate_ids = set()
        for index, candidate in enumerate(inventory_candidates):
            label = f"input_manifest.candidate_inventory.candidates[{index}]"
            if not isinstance(candidate, dict):
                issue(f"{label}:must_be_object")
                continue
            candidate_id = _text(candidate.get("candidate_id"))
            keyword = _norm_keyword(candidate.get("keyword"))
            source = _text(candidate.get("source"))
            source_seed = _norm_keyword(candidate.get("source_seed"))
            receipt_ref = _candidate_receipt_ref(candidate)
            if not candidate_id:
                issue(f"{label}.candidate_id:required")
            elif candidate_id in seen_candidate_ids:
                issue(f"{label}.candidate_id:duplicate")
            else:
                seen_candidate_ids.add(candidate_id)
            if not keyword:
                issue(f"{label}.keyword:required")
            if source not in SOURCE_EVIDENCE_TYPES:
                issue(f"{label}.source:must_be_real_observed_source")
            if not source_seed:
                issue(f"{label}.source_seed:required")
            if source == "semrush_competitor_organic" and not _text(candidate.get("competitor_domain")):
                issue(f"{label}.competitor_domain:required")
            if not receipt_ref:
                issue(f"{label}.evidence_receipt_ref:required")

    _validate_source_receipts(manifest, inventory_candidates, production, issue)

    candidate_analysis = manifest.get("candidate_analysis")
    if not isinstance(candidate_analysis, list):
        issue("input_manifest.candidate_analysis:must_be_list")
    else:
        expected_ids = {
            _text(candidate.get("candidate_id"))
            for candidate in inventory_candidates
            if isinstance(candidate, dict) and _text(candidate.get("candidate_id"))
        }
        seen_analysis_ids = set()
        for index, analysis in enumerate(candidate_analysis):
            label = f"input_manifest.candidate_analysis[{index}]"
            if not isinstance(analysis, dict):
                issue(f"{label}:must_be_object")
                continue
            candidate_id = _text(analysis.get("candidate_id"))
            status = _text(analysis.get("analysis_status")).upper()
            if not candidate_id:
                issue(f"{label}.candidate_id:required")
            elif candidate_id in seen_analysis_ids:
                issue(f"{label}.candidate_id:duplicate")
            else:
                seen_analysis_ids.add(candidate_id)
            if status not in VALID_ANALYSIS_STATUSES:
                issue(f"{label}.analysis_status:invalid_status:{status or 'missing'}")
            if not isinstance(analysis.get("branch_required"), bool):
                issue(f"{label}.branch_required:must_be_boolean")
            if not _text(analysis.get("analysis_reason")):
                issue(f"{label}.analysis_reason:required")
        if seen_analysis_ids != expected_ids:
            issue("input_manifest.candidate_analysis:must_cover_exact_candidate_inventory")

    return issues


def _verify_receipt(ref, evidence_type, identity_field, identity, label, issue):
    if not ref:
        issue(f"{label}:evidence_receipt_ref:required")
        return None
    try:
        normalized = _binding().verify_receipt_ref(ref, evidence_type)
    except Exception as exc:
        issue(f"{label}:evidence_receipt_invalid:{exc}")
        return None
    if identity_field is not None:
        actual = normalized.get(identity_field)
        if identity_field == "competitor_domain":
            matches = _text(actual).casefold() == _text(identity).casefold()
        else:
            matches = _norm_keyword(actual) == _norm_keyword(identity)
        if not matches:
            issue(f"{label}:evidence_identity_mismatch")
    return normalized


def _load_verified_input_manifest(receipt_ref, issue):
    """Load the exact production validator report for the upstream manifest."""

    receipt_path = Path(_text(receipt_ref))
    if not receipt_path.is_file():
        issue("upstream_input:validation_receipt:file_missing")
        return None
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        issue(f"upstream_input:validation_receipt:invalid_json:{exc}")
        return None
    if not isinstance(receipt, dict):
        issue("upstream_input:validation_receipt:must_be_object")
        return None
    if receipt.get("schema") != "seo-stage-validation/v1":
        issue("upstream_input:validation_receipt:schema_mismatch")
        return None
    if receipt.get("stage") != "discovery_input_manifest" or receipt.get("status") != PASS:
        issue("upstream_input:validation_receipt:stage_or_status_mismatch")
        return None
    if receipt.get("candidate_id") not in (None, ""):
        issue("upstream_input:validation_receipt:must_be_global")
        return None
    try:
        if receipt.get("validator_source_sha256") != _file_sha256(STAGE_VALIDATOR_PATH):
            issue("upstream_input:validation_receipt:validator_source_mismatch")
            return None
        report_path = Path(_text(receipt.get("report_ref")))
        if not report_path.is_file():
            issue("upstream_input:validation_receipt:report_file_missing")
            return None
        if receipt.get("report_sha256") != _file_sha256(report_path):
            issue("upstream_input:validation_receipt:report_hash_mismatch")
            return None
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        issue(f"upstream_input:validation_receipt:report_invalid:{exc}")
        return None
    if not isinstance(report, dict):
        issue("upstream_input:validation_receipt:report_must_be_object")
        return None
    if report.get("stage") != "discovery_input_manifest" or report.get("status") != PASS:
        issue("upstream_input:validation_receipt:report_stage_or_status_mismatch")
        return None
    if report.get("production") is not True:
        issue("upstream_input:validation_receipt:report_must_be_production")
        return None
    if report.get("validation_receipt_ref") != str(receipt_path):
        issue("upstream_input:validation_receipt:report_receipt_ref_mismatch")
        return None
    complete = report.get("complete")
    if report.get("complete_count") != 1 or report.get("blocked_count") != 0:
        issue("upstream_input:validation_receipt:report_must_contain_one_complete_row")
        return None
    if not isinstance(complete, list) or len(complete) != 1 or not isinstance(complete[0], dict):
        issue("upstream_input:validation_receipt:complete_row_missing")
        return None
    manifest = complete[0]
    manifest_errors = validate_input_manifest(manifest, production=True)
    for error in manifest_errors:
        issue(f"upstream_input:receipt_manifest:{error}")
    return manifest if not manifest_errors else None


def _authoritative_input(ledger, production, issue):
    upstream = ledger.get("upstream_input")
    if not isinstance(upstream, dict):
        issue("upstream_input:authoritative_root_natural_seed_manifest_required")
        return None
    manifest = upstream
    if production:
        receipt_ref = _text(upstream.get("validation_receipt_ref"))
        if not receipt_ref:
            issue("upstream_input:validation_receipt_ref:required_for_production")
        else:
            verified_manifest = _load_verified_input_manifest(receipt_ref, issue)
            if verified_manifest is not None:
                embedded = {key: value for key, value in upstream.items() if key != "validation_receipt_ref"}
                if embedded != verified_manifest:
                    issue("upstream_input:embedded_manifest_differs_from_verified_receipt")
                manifest = verified_manifest
    for error in validate_input_manifest(manifest, production=production):
        issue(f"upstream_input:{error}")
    if _norm_keyword(manifest.get("batch_id")) != _norm_keyword(ledger.get("batch_id")):
        issue("upstream_input.batch_id:must_match_coverage_batch_id")
    return manifest


def _validate_authoritative_inventory(manifest, ledger, required_seeds, observed_candidates, branches, issue):
    if not isinstance(manifest, dict):
        return
    seed_plan = manifest.get("seed_plan")
    if isinstance(seed_plan, dict) and isinstance(seed_plan.get("seeds"), list):
        expected_seed_keys = [_norm_keyword(seed) for seed in seed_plan["seeds"]]
        actual_seed_keys = [
            _norm_keyword(item.get("seed")) for item in required_seeds if isinstance(item, dict)
        ]
        if len(required_seeds) != len(expected_seed_keys):
            issue("required_seeds:count_below_upstream_original_seed_count")
        if actual_seed_keys != expected_seed_keys:
            issue("required_seeds:must_match_upstream_seed_inventory")

    candidate_inventory = manifest.get("candidate_inventory")
    if isinstance(candidate_inventory, dict) and isinstance(candidate_inventory.get("candidates"), list):
        expected_candidates = candidate_inventory["candidates"]
        actual_fingerprints = [_candidate_fingerprint(candidate) for candidate in observed_candidates if isinstance(candidate, dict)]
        expected_fingerprints = [_candidate_fingerprint(candidate) for candidate in expected_candidates if isinstance(candidate, dict)]
        if len(observed_candidates) != len(expected_candidates):
            issue("observed_candidates:count_below_upstream_original_candidate_count")
        if actual_fingerprints != expected_fingerprints:
            issue("observed_candidates:must_match_upstream_candidate_inventory")

        expected_ids = {
            _text(candidate.get("candidate_id"))
            for candidate in expected_candidates
            if isinstance(candidate, dict) and _text(candidate.get("candidate_id"))
        }
        authoritative_analyses = manifest.get("candidate_analysis")
        if not isinstance(authoritative_analyses, list):
            issue("candidate_analysis:authoritative_complete_inventory_state_required")
            authoritative_analyses = []
        authoritative_by_id = {}
        for analysis in authoritative_analyses:
            if isinstance(analysis, dict) and _text(analysis.get("candidate_id")):
                authoritative_by_id[_text(analysis.get("candidate_id"))] = analysis
        if set(authoritative_by_id) != expected_ids:
            issue("candidate_analysis:authoritative_state_must_cover_exact_upstream_inventory")

        analyses = ledger.get("candidate_analysis")
        if not isinstance(analyses, list):
            issue("candidate_analysis:complete_inventory_state_required")
            analyses = []
        analysis_by_id = {}
        for index, analysis in enumerate(analyses):
            label = f"candidate_analysis[{index}]"
            if not isinstance(analysis, dict):
                issue(f"{label}:must_be_object")
                continue
            candidate_id = _text(analysis.get("candidate_id"))
            if not candidate_id:
                issue(f"{label}.candidate_id:required")
            elif candidate_id in analysis_by_id:
                issue(f"{label}.candidate_id:duplicate")
            else:
                analysis_by_id[candidate_id] = analysis
        if set(analysis_by_id) != expected_ids:
            issue("candidate_analysis:must_cover_exact_upstream_candidate_inventory")
        if set(authoritative_by_id) == expected_ids and set(analysis_by_id) == expected_ids:
            authoritative_fingerprints = [_analysis_fingerprint(analysis) for analysis in authoritative_analyses]
            current_fingerprints = [_analysis_fingerprint(analysis) for analysis in analyses]
            if current_fingerprints != authoritative_fingerprints:
                issue("candidate_analysis:must_match_authoritative_state_order_and_values")
            for candidate_id in expected_ids:
                if _analysis_fingerprint(analysis_by_id[candidate_id]) != _analysis_fingerprint(
                    authoritative_by_id[candidate_id]
                ):
                    issue(f"candidate_analysis[{candidate_id}]:differs_from_authoritative_state")

        branches_by_candidate = {}
        for branch in branches:
            if isinstance(branch, dict):
                branches_by_candidate.setdefault(_text(branch.get("originating_candidate_id")), []).append(branch)
        for candidate_id in expected_ids:
            label = f"candidate_analysis[{candidate_id}]"
            analysis = authoritative_by_id.get(candidate_id)
            if analysis is None:
                continue
            status = _text(analysis.get("analysis_status")).upper()
            if status not in VALID_ANALYSIS_STATUSES:
                issue(f"{label}.analysis_status:invalid_status:{status or 'missing'}")
            if status != "COMPLETE":
                issue(f"{label}.analysis_status:must_be_COMPLETE")
            branch_required = analysis.get("branch_required")
            if not isinstance(branch_required, bool):
                issue(f"{label}.branch_required:must_be_boolean")
                continue
            if not _text(analysis.get("analysis_reason")):
                issue(f"{label}.analysis_reason:required")
            candidate_branches = branches_by_candidate.get(candidate_id, [])
            if branch_required and len(candidate_branches) != 1:
                issue(f"{label}.branch_required:must_have_exactly_one_branch_record")
            if not branch_required and candidate_branches:
                issue(f"{label}.branch_required:false_but_branch_record_present")


def _validate_first_round_receipt_binding(manifest, required_seeds, competitor, issue):
    """Every first-round acquisition receipt must be frozen into the input manifest.

    Without this a whole source could pass Coverage on its own receipt while that
    receipt was never listed in the manifest, so its observed rows would never be
    reconciled against the Candidate inventory.
    """

    if not isinstance(manifest, dict):
        return
    receipts = manifest.get("source_receipts")
    if not isinstance(receipts, list):
        return
    bound = {
        _text(record.get("evidence_receipt_ref"))
        for record in receipts
        if isinstance(record, dict) and _text(record.get("evidence_receipt_ref"))
    }
    for index, item in enumerate(required_seeds):
        if not isinstance(item, dict):
            continue
        for key in ("autocomplete", "semrush"):
            record = item.get(key)
            if not isinstance(record, dict) or _status(record) != PASS:
                continue
            ref = _receipt_ref(record)
            if ref and ref not in bound:
                issue(f"required_seed[{index}]:{key}:receipt_not_frozen_in_input_manifest")
    if isinstance(competitor, dict) and competitor.get("configured") is True:
        domains = competitor.get("domains")
        if isinstance(domains, list):
            for index, record in enumerate(domains):
                if not isinstance(record, dict) or _status(record) != PASS:
                    continue
                ref = _receipt_ref(record)
                if ref and ref not in bound:
                    issue(f"competitor_sweep.domain[{index}]:receipt_not_frozen_in_input_manifest")


def _check_acquisition(item, key, label, evidence_type, identity_field, identity, production, issue):
    """Return the acquisition status and, in production, its verified payload."""

    record = item.get(key) if isinstance(item, dict) else None
    if not isinstance(record, dict):
        issue(f"{label}:{key}:record_required")
        return "", None
    status = _status(record)
    normalized = None
    if status not in VALID_ACQUISITION_STATUSES:
        issue(f"{label}:{key}:invalid_status:{status or 'missing'}")
        return status, None
    if status == PASS:
        ref = _receipt_ref(record)
        if not ref:
            issue(f"{label}:{key}:PASS_requires_evidence_receipt")
        elif production:
            normalized = _verify_receipt(
                ref, evidence_type, identity_field, identity, f"{label}:{key}", issue
            )
    else:
        reason = _reason(record)
        if not reason:
            issue(f"{label}:{key}:{status}_requires_blocked_reason")
        issue(f"{label}:{key}:status={status or 'missing'}:{reason or 'unreviewed'}")
    return status, normalized


def _analyze(ledger, production=False):
    issues = []
    blocked_reasons = []

    def issue(message):
        if message not in issues:
            issues.append(message)
        if message not in blocked_reasons:
            blocked_reasons.append(message)

    summary = {
        "required_seed_count": 0,
        "autocomplete_pass_count": 0,
        "semrush_required_count": 0,
        "semrush_pass_count": 0,
        "required_branch_seed_count": 0,
        "branch_seed_pass_count": 0,
        "branch_candidate_count": 0,
        "branch_autocomplete_pass_count": 0,
        "branch_semrush_required_count": 0,
        "branch_semrush_pass_count": 0,
        "semrush_total_required_count": 0,
        "semrush_total_pass_count": 0,
        "competitor_sweep_configured": False,
        "competitor_sweep_status": NOT_CONFIGURED,
        "competitor_required_count": 0,
        "competitor_pass_count": 0,
        "other_mandatory_sources": [],
        "coverage_status": BLOCKED,
        "formal_handoff_allowed": False,
        "blocked_reasons": [],
    }
    if not isinstance(ledger, dict):
        issue("ledger:must_be_object")
        summary["blocked_reasons"] = blocked_reasons
        return summary, issues

    mode = _text(ledger.get("discovery_mode") or FULL_DISCOVERY).casefold()
    if mode not in VALID_DISCOVERY_MODES:
        issue(f"discovery_mode:unsupported:{mode or 'missing'}")
    if mode != FULL_DISCOVERY:
        issue("discovery_mode:is_not_full; formal handoff is denied")
    full_route = mode == FULL_DISCOVERY
    authoritative_manifest = _authoritative_input(ledger, production, issue)

    required_seeds = ledger.get("required_seeds")
    if not isinstance(required_seeds, list):
        issue("required_seeds:must_be_list")
        required_seeds = []
    elif not required_seeds:
        issue("required_seeds:must_contain_at_least_one_seed")

    summary["required_seed_count"] = len(required_seeds)
    summary["semrush_required_count"] = len(required_seeds) if full_route else 0
    root_seed_keys = set()
    root_autocomplete_pass = 0
    root_semrush_pass = 0
    for index, item in enumerate(required_seeds):
        label = f"required_seed[{index}]"
        if not isinstance(item, dict):
            issue(f"{label}:must_be_object")
            continue
        seed = _text(item.get("seed"))
        seed_key = _norm_keyword(seed)
        if not seed_key:
            issue(f"{label}.seed:required")
        elif seed_key in root_seed_keys:
            issue(f"{label}.seed:duplicate")
        else:
            root_seed_keys.add(seed_key)
        autocomplete_status, _autocomplete_evidence = _check_acquisition(
            item,
            "autocomplete",
            label,
            "google_autocomplete",
            "seed",
            seed,
            production,
            issue,
        )
        if autocomplete_status == PASS:
            root_autocomplete_pass += 1
        if full_route:
            semrush_status, _semrush_evidence = _check_acquisition(
                item,
                "semrush",
                label,
                "semrush_ideas",
                "seed",
                seed,
                production,
                issue,
            )
            if semrush_status == PASS:
                root_semrush_pass += 1
        elif isinstance(item.get("semrush"), dict) and _status(item["semrush"]) == PASS:
            root_semrush_pass += 1

    summary["autocomplete_pass_count"] = root_autocomplete_pass
    summary["semrush_pass_count"] = root_semrush_pass

    observed_candidates = ledger.get("observed_candidates")
    if not isinstance(observed_candidates, list):
        issue("observed_candidates:must_be_list")
        observed_candidates = []
    candidate_by_id = {}
    for index, candidate in enumerate(observed_candidates):
        label = f"observed_candidate[{index}]"
        if not isinstance(candidate, dict):
            issue(f"{label}:must_be_object")
            continue
        candidate_id = _text(candidate.get("candidate_id"))
        keyword = _text(candidate.get("keyword"))
        source = _text(candidate.get("source"))
        source_seed = _text(candidate.get("source_seed"))
        ref = _candidate_receipt_ref(candidate)
        if not candidate_id:
            issue(f"{label}.candidate_id:required")
        elif candidate_id in candidate_by_id:
            issue(f"{label}.candidate_id:duplicate")
        else:
            candidate_by_id[candidate_id] = candidate
        if not _norm_keyword(keyword):
            issue(f"{label}.keyword:required")
        if source not in SOURCE_EVIDENCE_TYPES:
            issue(f"{label}.source:must_be_real_observed_source")
        if not source_seed:
            issue(f"{label}.source_seed:required")
        if not ref:
            issue(f"{label}.evidence_receipt_ref:required")
        normalized = None
        if production and source in SOURCE_EVIDENCE_TYPES and ref:
            identity_field = "competitor_domain" if source == "semrush_competitor_organic" else "seed"
            identity = candidate.get("competitor_domain") if identity_field == "competitor_domain" else source_seed
            if not _text(identity):
                field = "competitor_domain" if identity_field == "competitor_domain" else "source_seed"
                issue(f"{label}.{field}:required")
            normalized = _verify_receipt(
                ref,
                SOURCE_EVIDENCE_TYPES[source],
                identity_field,
                identity,
                label,
                issue,
            )
            if normalized is not None and _norm_keyword(keyword) not in _observed_keywords(
                normalized, SOURCE_EVIDENCE_TYPES[source]
            ):
                issue(f"{label}.keyword:not_present_in_observed_evidence")

    max_branch_depth = _positive_int(
        ledger.get("max_branch_depth"), DEFAULT_MAX_BRANCH_DEPTH, "max_branch_depth", issue
    )
    max_branch_seeds = _positive_int(
        ledger.get("max_branch_seeds"), DEFAULT_MAX_BRANCH_SEEDS, "max_branch_seeds", issue
    )

    branches = ledger.get("required_branch_seeds")
    if not isinstance(branches, list):
        issue("required_branch_seeds:must_be_list")
        branches = []
    summary["required_branch_seed_count"] = len(branches)
    summary["branch_semrush_required_count"] = len(branches) if full_route else 0
    if len(branches) > max_branch_seeds:
        issue(f"required_branch_seeds:branch_safety_limit_exceeded:{len(branches)}>{max_branch_seeds}")

    seen_branch_keys = set()
    depth_by_seed = {seed_key: 0 for seed_key in root_seed_keys}
    branch_normalized_by_ref = {}

    def _record_branch_evidence(record, evidence_type, normalized):
        if normalized is None or not isinstance(record, dict):
            return
        ref = _receipt_ref(record)
        if ref:
            branch_normalized_by_ref[ref] = (evidence_type, normalized)

    branch_autocomplete_pass = 0
    branch_semrush_pass = 0
    for index, branch in enumerate(branches):
        label = f"required_branch_seed[{index}]"
        if not isinstance(branch, dict):
            issue(f"{label}:must_be_object")
            continue
        branch_seed = _text(branch.get("branch_seed"))
        branch_key = _norm_keyword(branch_seed)
        parent_key = _norm_keyword(branch.get("parent_seed"))
        candidate_id = _text(branch.get("originating_candidate_id"))
        source = _text(branch.get("source"))
        branch_ref = _text(branch.get("evidence_ref"))
        depth = branch.get("depth")
        parent_is_visited = parent_key in root_seed_keys or parent_key in seen_branch_keys
        branch_is_new = bool(branch_key) and branch_key not in root_seed_keys and branch_key not in seen_branch_keys
        if not branch_key:
            issue(f"{label}.branch_seed:required")
        elif branch_key in root_seed_keys:
            issue(f"{label}.branch_seed:cycle_or_duplicate_with_required_seed")
        elif branch_key in seen_branch_keys:
            issue(f"{label}.branch_seed:duplicate")
        elif branch_key == parent_key:
            issue(f"{label}.branch_seed:cycle_with_parent_seed")
        if not parent_key:
            issue(f"{label}.parent_seed:required")
        elif not parent_is_visited:
            issue(f"{label}.parent_seed:not_in_visited_seed_set")
        if not candidate_id or candidate_id not in candidate_by_id:
            issue(f"{label}.originating_candidate_id:must_resolve_to_observed_candidate")
            candidate = None
        else:
            candidate = candidate_by_id[candidate_id]
        if not _text(branch.get("branch_reason")):
            issue(f"{label}.branch_reason:required_analysis")
        if _text(branch.get("analysis_status")).casefold() != "required":
            issue(f"{label}.analysis_status:must_be_required")
        try:
            declared_depth = _strict_positive_integer(depth)
        except (TypeError, ValueError):
            declared_depth = None
            issue(f"{label}.depth:must_be_positive_integer")
        # The visited parent chain, never the caller, decides the real depth.
        parent_depth = depth_by_seed.get(parent_key)
        effective_depth = declared_depth if parent_depth is None else parent_depth + 1
        if declared_depth is not None and parent_depth is not None and declared_depth != effective_depth:
            issue(f"{label}.depth:must_equal_parent_depth_plus_one:{declared_depth}!={effective_depth}")
        if effective_depth is not None and effective_depth > max_branch_depth:
            issue(f"{label}.depth:branch_safety_limit_exceeded:{effective_depth}>{max_branch_depth}")
        if candidate is not None:
            candidate_keyword = _text(candidate.get("keyword"))
            candidate_source = _text(candidate.get("source"))
            candidate_source_seed = _text(candidate.get("source_seed"))
            candidate_ref = _candidate_receipt_ref(candidate)
            if _norm_keyword(candidate_keyword) != branch_key:
                issue(f"{label}:branch_seed_not_equal_to_observed_candidate_keyword")
            if source != candidate_source:
                issue(f"{label}.source:provenance_mismatch")
            if branch_ref != candidate_ref:
                issue(f"{label}.evidence_ref:provenance_mismatch")
            if not candidate_source_seed:
                issue(f"{label}.candidate_source_seed:required")
            elif _norm_keyword(candidate_source_seed) != parent_key:
                issue(f"{label}.parent_seed:provenance_mismatch_with_candidate_source_seed")
        if branch_is_new and parent_is_visited:
            seen_branch_keys.add(branch_key)
            if effective_depth is not None:
                depth_by_seed[branch_key] = effective_depth
        autocomplete_status, autocomplete_evidence = _check_acquisition(
            branch,
            "autocomplete",
            label,
            "google_autocomplete",
            "seed",
            branch_seed,
            production,
            issue,
        )
        if autocomplete_status == PASS:
            branch_autocomplete_pass += 1
            _record_branch_evidence(
                branch.get("autocomplete"), "google_autocomplete", autocomplete_evidence
            )
        if full_route:
            semrush_status, semrush_evidence = _check_acquisition(
                branch,
                "semrush",
                label,
                "semrush_ideas",
                "seed",
                branch_seed,
                production,
                issue,
            )
            if semrush_status == PASS:
                branch_semrush_pass += 1
                _record_branch_evidence(branch.get("semrush"), "semrush_ideas", semrush_evidence)
        else:
            semrush_status = _status(branch.get("semrush"))
            if semrush_status == PASS:
                branch_semrush_pass += 1

    summary["branch_autocomplete_pass_count"] = branch_autocomplete_pass
    summary["branch_semrush_pass_count"] = branch_semrush_pass
    summary["branch_seed_pass_count"] = sum(
        1
        for branch in branches
        if isinstance(branch, dict)
        and _status(branch.get("autocomplete")) == PASS
        and (not full_route or _status(branch.get("semrush")) == PASS)
    )
    summary["semrush_total_required_count"] = (
        summary["semrush_required_count"] + summary["branch_semrush_required_count"]
    )
    summary["semrush_total_pass_count"] = summary["semrush_pass_count"] + summary["branch_semrush_pass_count"]

    # Branch acquisitions produce their own observed rows. They are reconciled here,
    # after the freeze, because a Branch Seed does not exist when the manifest is signed.
    branch_candidates = ledger.get("branch_candidates", [])
    if not isinstance(branch_candidates, list):
        issue("branch_candidates:must_be_list")
        branch_candidates = []
    branch_candidate_by_id = {}
    for index, candidate in enumerate(branch_candidates):
        label = f"branch_candidate[{index}]"
        if not isinstance(candidate, dict):
            issue(f"{label}:must_be_object")
            continue
        candidate_id = _text(candidate.get("candidate_id"))
        source_seed = _norm_keyword(candidate.get("source_seed"))
        if not candidate_id:
            issue(f"{label}.candidate_id:required")
        elif candidate_id in candidate_by_id or candidate_id in branch_candidate_by_id:
            issue(f"{label}.candidate_id:duplicate")
        else:
            branch_candidate_by_id[candidate_id] = candidate
        if not _norm_keyword(candidate.get("keyword")):
            issue(f"{label}.keyword:required")
        if _text(candidate.get("source")) not in SOURCE_EVIDENCE_TYPES:
            issue(f"{label}.source:must_be_real_observed_source")
        if not source_seed:
            issue(f"{label}.source_seed:required")
        elif source_seed not in seen_branch_keys:
            issue(f"{label}.source_seed:must_be_a_completed_branch_seed")
        if not _candidate_receipt_ref(candidate):
            issue(f"{label}.evidence_receipt_ref:required")
    summary["branch_candidate_count"] = len(branch_candidates)

    if production and (branch_normalized_by_ref or branch_candidate_by_id):
        branch_row_ledger = ledger.get("branch_row_ledger")
        if not isinstance(branch_row_ledger, list):
            issue("branch_row_ledger:required_for_branch_acquisitions")
        else:
            indexed = _index_row_ledger(branch_row_ledger, "branch_row_ledger", issue)
            kept = _reconcile_row_ledger(
                branch_normalized_by_ref,
                indexed,
                {**candidate_by_id, **branch_candidate_by_id},
                "branch_row_ledger",
                issue,
            )
            if set(branch_candidate_by_id) - kept:
                issue("branch_candidates:without_a_kept_branch_source_row")

    competitor = ledger.get("competitor_sweep")
    if not isinstance(competitor, dict):
        issue("competitor_sweep:must_be_object")
        competitor = {"configured": False, "domains": [], "status": NOT_CONFIGURED}
    configured = competitor.get("configured") is True
    domains = competitor.get("domains")
    summary["competitor_sweep_configured"] = configured
    if not configured:
        if domains not in (None, []):
            issue("competitor_sweep:domains_must_be_empty_when_not_configured")
        if _text(competitor.get("status")) != NOT_CONFIGURED:
            issue("competitor_sweep.status:must_be_not_configured")
        summary["competitor_sweep_status"] = NOT_CONFIGURED
    else:
        if not isinstance(domains, list) or not domains:
            issue("competitor_sweep.domains:configured_sweep_requires_domains")
            domains = []
        summary["competitor_required_count"] = len(domains)
        competitor_pass = 0
        for index, domain_record in enumerate(domains):
            label = f"competitor_sweep.domain[{index}]"
            if not isinstance(domain_record, dict):
                issue(f"{label}:must_be_object")
                continue
            domain = _text(domain_record.get("domain"))
            if not domain:
                issue(f"{label}.domain:required")
            status = _status(domain_record)
            if status not in VALID_ACQUISITION_STATUSES:
                issue(f"{label}.status:invalid_status:{status or 'missing'}")
            elif status == PASS:
                competitor_pass += 1
                ref = _receipt_ref(domain_record)
                if not ref:
                    issue(f"{label}:PASS_requires_evidence_receipt")
                elif production:
                    _verify_receipt(
                        ref,
                        "semrush_competitor_organic",
                        "competitor_domain",
                        domain,
                        label,
                        issue,
                    )
            else:
                reason = _reason(domain_record)
                if not reason:
                    issue(f"{label}:{status}_requires_blocked_reason")
                issue(f"{label}:status={status or 'missing'}:{reason or 'unreviewed'}")
        summary["competitor_pass_count"] = competitor_pass
        computed_competitor_status = PASS if domains and competitor_pass == len(domains) else BLOCKED
        summary["competitor_sweep_status"] = computed_competitor_status
        if _text(competitor.get("status")) != computed_competitor_status:
            issue(
                f"competitor_sweep.status:mismatch:{_text(competitor.get('status')) or 'missing'}!={computed_competitor_status}"
            )

    _validate_first_round_receipt_binding(authoritative_manifest, required_seeds, competitor, issue)

    _validate_authoritative_inventory(
        authoritative_manifest,
        ledger,
        required_seeds,
        observed_candidates,
        branches,
        issue,
    )

    other_sources = ledger.get("other_mandatory_sources")
    if not isinstance(other_sources, list):
        issue("other_mandatory_sources:must_be_list")
        other_sources = []
    summary["other_mandatory_sources"] = []
    for index, source in enumerate(other_sources):
        label = f"other_mandatory_source[{index}]"
        if not isinstance(source, dict):
            issue(f"{label}:must_be_object")
            continue
        source_id = _text(source.get("source_id"))
        evidence_type = _text(source.get("evidence_type"))
        status = _status(source)
        if not source_id:
            issue(f"{label}.source_id:required")
        if evidence_type not in SOURCE_EVIDENCE_TYPES:
            issue(f"{label}.evidence_type:must_be_supported_observed_source")
        if status not in VALID_ACQUISITION_STATUSES:
            issue(f"{label}.status:invalid_status:{status or 'missing'}")
        elif status == PASS:
            receipt_ref = _receipt_ref(source)
            if not receipt_ref:
                issue(f"{label}:PASS_requires_evidence_receipt")
            elif production and evidence_type in SOURCE_EVIDENCE_TYPES:
                _verify_receipt(receipt_ref, evidence_type, None, None, label, issue)
        elif status != PASS:
            reason = _reason(source)
            if not reason:
                issue(f"{label}:{status}_requires_blocked_reason")
            issue(f"{label}:status={status or 'missing'}:{reason or 'unreviewed'}")
        summary["other_mandatory_sources"].append({"source_id": source_id, "status": status})

    summary["blocked_reasons"] = list(blocked_reasons)
    summary["coverage_status"] = PASS if not issues else BLOCKED
    summary["formal_handoff_allowed"] = summary["coverage_status"] == PASS and full_route

    declared_fields = (
        "required_seed_count",
        "autocomplete_pass_count",
        "semrush_required_count",
        "semrush_pass_count",
        "required_branch_seed_count",
        "branch_seed_pass_count",
        "branch_candidate_count",
        "branch_autocomplete_pass_count",
        "branch_semrush_required_count",
        "branch_semrush_pass_count",
        "semrush_total_required_count",
        "semrush_total_pass_count",
        "competitor_sweep_configured",
        "competitor_sweep_status",
        "coverage_status",
        "formal_handoff_allowed",
    )
    for field in declared_fields:
        if field in ledger and ledger[field] != summary[field]:
            issue(f"{field}:declared_value_does_not_match_ledger")
    if "blocked_reasons" in ledger and ledger["blocked_reasons"] != summary["blocked_reasons"]:
        issue("blocked_reasons:declared_value_does_not_match_ledger")

    summary["blocked_reasons"] = list(blocked_reasons)
    summary["coverage_status"] = PASS if not issues else BLOCKED
    summary["formal_handoff_allowed"] = summary["coverage_status"] == PASS and full_route
    return summary, issues


def summarize_coverage(ledger, production=False):
    """Return computed counts/status without removing any ledger entry."""

    return _analyze(ledger, production=production)[0]


def validate_coverage(ledger, production=False):
    """Return specific errors; a non-empty result denies formal handoff."""

    return _analyze(ledger, production=production)[1]


def enrich_coverage(ledger):
    """Copy a ledger and attach deterministic coverage counts for stage reports."""

    if not isinstance(ledger, dict):
        return ledger
    enriched = copy.deepcopy(ledger)
    summary = summarize_coverage(enriched)
    enriched.update(summary)
    return enriched


def validate_handoff_keywords(coverage_row, keywords):
    """Require the handoff word list to be exactly the verified Coverage candidates.

    That is the first-round inventory frozen in the manifest plus the Branch
    candidates reconciled against the branch acquisitions, so the handoff can
    neither drop a keyword Coverage verified nor add one it never saw.
    """

    if not isinstance(coverage_row, dict):
        return ["coverage_row:must_be_object"]
    candidates = coverage_row.get("observed_candidates")
    if not isinstance(candidates, list):
        return ["coverage_row.observed_candidates:must_be_list"]
    branch_candidates = coverage_row.get("branch_candidates", [])
    if not isinstance(branch_candidates, list):
        return ["coverage_row.branch_candidates:must_be_list"]
    if not isinstance(keywords, list) or not keywords:
        return ["keywords:complete_candidate_list_required"]

    errors = []
    expected = {
        _text(candidate.get("candidate_id")): _candidate_fingerprint(candidate)
        for candidate in list(candidates) + list(branch_candidates)
        if isinstance(candidate, dict) and _text(candidate.get("candidate_id"))
    }
    actual = {}
    for index, item in enumerate(keywords):
        label = f"keywords[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label}:must_be_object")
            continue
        candidate_id = _text(item.get("candidate_id"))
        if not candidate_id:
            errors.append(f"{label}.candidate_id:required")
        elif candidate_id in actual:
            errors.append(f"{label}.candidate_id:duplicate")
        else:
            actual[candidate_id] = _candidate_fingerprint(item)
    if set(actual) != set(expected):
        errors.append("keywords:must_cover_exact_coverage_candidate_inventory")
    for candidate_id in sorted(set(actual) & set(expected)):
        if actual[candidate_id] != expected[candidate_id]:
            errors.append(f"keywords[{candidate_id}]:differs_from_coverage_candidate")
    return errors


def add_required_branch_seed(
    ledger,
    originating_candidate_id,
    parent_seed,
    branch_reason,
    depth=None,
    branch_seed=None,
):
    """Promote an existing observed candidate, never an agent-created string."""

    if not isinstance(ledger, dict):
        raise CoverageContractError("coverage ledger must be an object")
    candidates = ledger.get("observed_candidates")
    if not isinstance(candidates, list):
        raise CoverageContractError("observed candidate ledger is required")
    candidate = next(
        (
            item
            for item in candidates
            if isinstance(item, dict) and _text(item.get("candidate_id")) == _text(originating_candidate_id)
        ),
        None,
    )
    if candidate is None:
        raise CoverageContractError("originating candidate is not an observed candidate")
    keyword = _text(candidate.get("keyword"))
    source = _text(candidate.get("source"))
    evidence_ref = _candidate_receipt_ref(candidate)
    if not _norm_keyword(keyword) or source not in SOURCE_EVIDENCE_TYPES or not evidence_ref:
        raise CoverageContractError("originating candidate lacks observed source or evidence provenance")
    if branch_seed is not None and _norm_keyword(branch_seed) != _norm_keyword(keyword):
        raise CoverageContractError("branch seed must equal the observed candidate keyword")
    if not _text(parent_seed):
        raise CoverageContractError("parent seed is required")
    if not _text(branch_reason):
        raise CoverageContractError("branch reason is required")

    branches = ledger.setdefault("required_branch_seeds", [])
    if not isinstance(branches, list):
        raise CoverageContractError("required branch seed ledger must be a list")
    try:
        max_branch_depth = _strict_positive_integer(
            ledger.get("max_branch_depth", DEFAULT_MAX_BRANCH_DEPTH)
        )
        max_branch_seeds = _strict_positive_integer(
            ledger.get("max_branch_seeds", DEFAULT_MAX_BRANCH_SEEDS)
        )
    except (TypeError, ValueError) as exc:
        raise CoverageContractError("branch safety budget must be a positive integer") from exc
    if len(branches) >= max_branch_seeds:
        raise CoverageContractError("branch safety budget is exhausted")
    candidate_key = _norm_keyword(keyword)
    existing_keys = {
        _norm_keyword(item.get("branch_seed"))
        for item in branches
        if isinstance(item, dict)
    }
    root_keys = {
        _norm_keyword(item.get("seed"))
        for item in ledger.get("required_seeds", [])
        if isinstance(item, dict)
    }
    if candidate_key in existing_keys or candidate_key in root_keys:
        raise CoverageContractError("branch seed would create a duplicate or cycle")

    # The visited parent chain, never the caller, decides the real depth.
    depth_by_seed = {key: 0 for key in root_keys}
    for item in branches:
        if not isinstance(item, dict):
            continue
        try:
            depth_by_seed[_norm_keyword(item.get("branch_seed"))] = _strict_positive_integer(item.get("depth"))
        except (TypeError, ValueError) as exc:
            raise CoverageContractError("existing branch ledger records an invalid depth") from exc
    parent_depth = depth_by_seed.get(_norm_keyword(parent_seed))
    if parent_depth is None:
        raise CoverageContractError("parent seed must already be visited")
    parsed_depth = parent_depth + 1
    if depth is not None:
        try:
            declared_depth = _strict_positive_integer(depth)
        except (TypeError, ValueError) as exc:
            raise CoverageContractError("branch depth must be a positive integer") from exc
        if declared_depth != parsed_depth:
            raise CoverageContractError("branch depth must equal parent depth plus one")
    if parsed_depth > max_branch_depth:
        raise CoverageContractError("branch depth exceeds the configured safety limit")

    branch = {
        "branch_seed": keyword,
        "parent_seed": _text(parent_seed),
        "originating_candidate_id": _text(originating_candidate_id),
        "source": source,
        "evidence_ref": evidence_ref,
        "branch_reason": _text(branch_reason),
        "analysis_status": "required",
        "depth": parsed_depth,
        "autocomplete": {"status": NOT_RUN, "blocked_reason": "branch Google acquisition not run"},
        "semrush": {"status": NOT_RUN, "blocked_reason": "branch Semrush acquisition not run"},
    }
    branches.append(branch)
    return branch
