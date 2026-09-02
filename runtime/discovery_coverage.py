#!/usr/bin/env python3
"""Compatibility wrapper for Discovery Coverage with mandatory Google SERP expansions.

The legacy coverage engine remains unchanged and is loaded from
``discovery_coverage_legacy.py``. This wrapper adds the new source to the
candidate/evidence registry, requires an expansion check for every required Seed
and Branch Seed, reconciles expansion rows, and preserves the legacy public API.
"""

import copy
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LEGACY_PATH = ROOT / "discovery_coverage_legacy.py"


def _load_legacy():
    spec = importlib.util.spec_from_file_location("seo_discovery_coverage_legacy", LEGACY_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_legacy = _load_legacy()

# Re-export stable constants used by tests and callers.
PASS = _legacy.PASS
BLOCKED = _legacy.BLOCKED
NOT_RUN = _legacy.NOT_RUN
UNKNOWN = _legacy.UNKNOWN
NOT_CONFIGURED = _legacy.NOT_CONFIGURED
FULL_DISCOVERY = _legacy.FULL_DISCOVERY
DIAGNOSTIC_DISCOVERY = _legacy.DIAGNOSTIC_DISCOVERY
DEFAULT_MAX_BRANCH_DEPTH = _legacy.DEFAULT_MAX_BRANCH_DEPTH
DEFAULT_MAX_BRANCH_SEEDS = _legacy.DEFAULT_MAX_BRANCH_SEEDS
VALID_ACQUISITION_STATUSES = _legacy.VALID_ACQUISITION_STATUSES
VALID_DISCOVERY_MODES = _legacy.VALID_DISCOVERY_MODES
INPUT_MANIFEST_SCHEMA = _legacy.INPUT_MANIFEST_SCHEMA
ROOT_HANDOFF_SCHEMA = _legacy.ROOT_HANDOFF_SCHEMA
VALID_ANALYSIS_STATUSES = _legacy.VALID_ANALYSIS_STATUSES
EXCLUSION_RULE_CODES = _legacy.EXCLUSION_RULE_CODES
VALID_ROW_DISPOSITIONS = _legacy.VALID_ROW_DISPOSITIONS
CoverageContractError = _legacy.CoverageContractError

SOURCE_EVIDENCE_TYPES = _legacy.SOURCE_EVIDENCE_TYPES
SOURCE_EVIDENCE_TYPES["google_serp_expansions"] = "google_serp_expansions"

# Patch only the source-row interpretation needed by the legacy manifest logic.
_legacy_observed_keywords = _legacy._observed_keywords


def _observed_keywords(normalized, evidence_type):
    if evidence_type == "google_serp_expansions":
        return [
            _legacy._norm_keyword(value)
            for field in ("people_also_ask", "related_searches")
            for value in normalized.get(field, [])
        ]
    return _legacy_observed_keywords(normalized, evidence_type)


_legacy._observed_keywords = _observed_keywords


def _text(value):
    return _legacy._text(value)


def _norm_keyword(value):
    return _legacy._norm_keyword(value)


def _status(record):
    return _legacy._status(record)


def _receipt_ref(record):
    return _legacy._receipt_ref(record)


def _candidate_receipt_ref(candidate):
    return _legacy._candidate_receipt_ref(candidate)


def _issue_once(errors, message):
    if message not in errors:
        errors.append(message)


def _verify_expansion_record(record, seed, label, production, errors):
    if not isinstance(record, dict):
        _issue_once(errors, f"{label}:expansions:record_required")
        return False, None
    status = _status(record)
    if status not in VALID_ACQUISITION_STATUSES:
        _issue_once(errors, f"{label}:expansions:invalid_status:{status or 'missing'}")
        return False, None
    if status != PASS:
        reason = _legacy._reason(record)
        if not reason:
            _issue_once(errors, f"{label}:expansions:{status}_requires_blocked_reason")
        _issue_once(
            errors,
            f"{label}:expansions:status={status or 'missing'}:{reason or 'unreviewed'}",
        )
        return False, None
    ref = _receipt_ref(record)
    if not ref:
        _issue_once(errors, f"{label}:expansions:PASS_requires_evidence_receipt")
        return False, None
    if not production:
        return True, None
    try:
        normalized = _legacy._binding().verify_receipt_ref(ref, "google_serp_expansions")
    except Exception as exc:
        _issue_once(errors, f"{label}:expansions:evidence_receipt_invalid:{exc}")
        return False, None
    if _norm_keyword(normalized.get("seed")) != _norm_keyword(seed):
        _issue_once(errors, f"{label}:expansions:evidence_identity_mismatch")
        return False, normalized
    return True, normalized


def _manifest_receipt_refs(ledger):
    upstream = ledger.get("upstream_input") if isinstance(ledger, dict) else None
    receipts = upstream.get("source_receipts") if isinstance(upstream, dict) else None
    if not isinstance(receipts, list):
        return set()
    return {
        _text(item.get("evidence_receipt_ref"))
        for item in receipts
        if isinstance(item, dict) and _text(item.get("evidence_receipt_ref"))
    }


def _expansion_counts_and_errors(ledger, production=False):
    errors = []
    root_required = 0
    root_pass = 0
    branch_required = 0
    branch_pass = 0
    branch_normalized = {}

    required_seeds = ledger.get("required_seeds") if isinstance(ledger, dict) else None
    if not isinstance(required_seeds, list):
        required_seeds = []
    frozen_receipts = _manifest_receipt_refs(ledger)
    for index, item in enumerate(required_seeds):
        root_required += 1
        if not isinstance(item, dict):
            _issue_once(errors, f"required_seed[{index}]:must_be_object")
            continue
        seed = _text(item.get("seed"))
        passed, _normalized = _verify_expansion_record(
            item.get("expansions"), seed, f"required_seed[{index}]", production, errors
        )
        if passed:
            root_pass += 1
            ref = _receipt_ref(item.get("expansions"))
            if ref and ref not in frozen_receipts:
                _issue_once(
                    errors,
                    f"required_seed[{index}]:expansions:receipt_not_frozen_in_input_manifest",
                )

    branches = ledger.get("required_branch_seeds") if isinstance(ledger, dict) else None
    if not isinstance(branches, list):
        branches = []
    for index, branch in enumerate(branches):
        branch_required += 1
        if not isinstance(branch, dict):
            _issue_once(errors, f"required_branch_seed[{index}]:must_be_object")
            continue
        seed = _text(branch.get("branch_seed"))
        passed, normalized = _verify_expansion_record(
            branch.get("expansions"),
            seed,
            f"required_branch_seed[{index}]",
            production,
            errors,
        )
        if passed:
            branch_pass += 1
            ref = _receipt_ref(branch.get("expansions"))
            if production and ref and normalized is not None:
                branch_normalized[ref] = normalized

    return {
        "expansions_required_count": root_required,
        "expansions_pass_count": root_pass,
        "branch_expansions_required_count": branch_required,
        "branch_expansions_pass_count": branch_pass,
        "expansions_total_required_count": root_required + branch_required,
        "expansions_total_pass_count": root_pass + branch_pass,
    }, errors, branch_normalized


def _validate_branch_expansion_rows(ledger, branch_normalized, errors):
    if not branch_normalized:
        return
    row_ledger = ledger.get("branch_row_ledger")
    if not isinstance(row_ledger, list):
        _issue_once(errors, "branch_row_ledger:required_for_branch_expansion_acquisitions")
        return
    by_ref = {
        _text(record.get("evidence_receipt_ref")): record
        for record in row_ledger
        if isinstance(record, dict) and _text(record.get("evidence_receipt_ref"))
    }
    candidates = {
        _text(candidate.get("candidate_id")): candidate
        for candidate in ledger.get("branch_candidates", [])
        if isinstance(candidate, dict) and _text(candidate.get("candidate_id"))
    }
    expansion_candidate_ids = {
        candidate_id
        for candidate_id, candidate in candidates.items()
        if _text(candidate.get("source")) == "google_serp_expansions"
    }
    kept = set()
    for ref, normalized in branch_normalized.items():
        record = by_ref.get(ref)
        if record is None:
            _issue_once(errors, f"branch_row_ledger[{ref}]:required_for_expansion_receipt")
            continue
        rows = record.get("rows")
        if not isinstance(rows, list):
            _issue_once(errors, f"branch_row_ledger[{ref}].rows:must_be_list")
            continue
        observed = _observed_keywords(normalized, "google_serp_expansions")
        declared = [
            _norm_keyword(row.get("keyword")) if isinstance(row, dict) else None
            for row in rows
        ]
        if declared != observed:
            _issue_once(errors, f"branch_row_ledger[{ref}].rows:must_match_observed_source_rows_in_order")
            continue
        for pos, row in enumerate(rows):
            label = f"branch_row_ledger[{ref}].rows[{pos}]"
            if not isinstance(row, dict):
                _issue_once(errors, f"{label}:must_be_object")
                continue
            disposition = _text(row.get("disposition"))
            if disposition not in VALID_ROW_DISPOSITIONS:
                _issue_once(errors, f"{label}.disposition:must_be_kept_dedupe_of_or_excluded")
                continue
            if disposition == "excluded":
                if _text(row.get("rule_code")) not in EXCLUSION_RULE_CODES:
                    _issue_once(errors, f"{label}.rule_code:must_be_supported_cleaning_rule")
                if not _text(row.get("reason")):
                    _issue_once(errors, f"{label}.reason:required")
                continue
            candidate_id = _text(row.get("candidate_id"))
            candidate = candidates.get(candidate_id)
            if candidate is None:
                _issue_once(errors, f"{label}.candidate_id:must_resolve_to_branch_candidate")
                continue
            if _norm_keyword(candidate.get("keyword")) != observed[pos]:
                _issue_once(errors, f"{label}.candidate_id:keyword_differs_from_observed_row")
                continue
            if disposition == "kept":
                if _text(candidate.get("source")) != "google_serp_expansions":
                    _issue_once(errors, f"{label}.candidate_id:kept_candidate_source_mismatch")
                elif _candidate_receipt_ref(candidate) != ref:
                    _issue_once(errors, f"{label}.candidate_id:kept_candidate_must_cite_this_receipt")
                else:
                    kept.add(candidate_id)
    if expansion_candidate_ids - kept:
        _issue_once(errors, "branch_candidates:expansion_candidates_without_a_kept_branch_source_row")


def _legacy_projection(ledger):
    """Remove expansion-only branch rows before invoking the unchanged legacy engine."""
    projected = copy.deepcopy(ledger)
    projected["branch_candidates"] = [
        item
        for item in projected.get("branch_candidates", [])
        if not isinstance(item, dict) or _text(item.get("source")) != "google_serp_expansions"
    ]
    expansion_refs = {
        _receipt_ref(branch.get("expansions"))
        for branch in projected.get("required_branch_seeds", [])
        if isinstance(branch, dict) and _receipt_ref(branch.get("expansions"))
    }
    projected["branch_row_ledger"] = [
        record
        for record in projected.get("branch_row_ledger", [])
        if not isinstance(record, dict)
        or _text(record.get("evidence_receipt_ref")) not in expansion_refs
    ]
    return projected


def validate_input_manifest(manifest, production=False):
    return _legacy.validate_input_manifest(manifest, production=production)


def summarize_coverage(ledger, production=False):
    projected = _legacy_projection(ledger) if isinstance(ledger, dict) else ledger
    summary = _legacy.summarize_coverage(projected, production=production)
    counts, expansion_errors, branch_normalized = _expansion_counts_and_errors(
        ledger, production=production
    )
    summary.update(counts)
    legacy_errors = _legacy.validate_coverage(projected, production=production)
    errors = list(legacy_errors)
    for error in expansion_errors:
        _issue_once(errors, error)
    if production and isinstance(ledger, dict):
        _validate_branch_expansion_rows(ledger, branch_normalized, errors)
    summary["blocked_reasons"] = errors
    summary["coverage_status"] = PASS if not errors else BLOCKED
    full_route = _text(ledger.get("discovery_mode") or FULL_DISCOVERY).casefold() == FULL_DISCOVERY if isinstance(ledger, dict) else False
    summary["formal_handoff_allowed"] = summary["coverage_status"] == PASS and full_route
    return summary


def validate_coverage(ledger, production=False):
    projected = _legacy_projection(ledger) if isinstance(ledger, dict) else ledger
    errors = list(_legacy.validate_coverage(projected, production=production))
    counts, expansion_errors, branch_normalized = _expansion_counts_and_errors(
        ledger, production=production
    )
    for error in expansion_errors:
        _issue_once(errors, error)
    if production and isinstance(ledger, dict):
        _validate_branch_expansion_rows(ledger, branch_normalized, errors)
    if isinstance(ledger, dict):
        for field, value in counts.items():
            if field in ledger and ledger[field] != value:
                _issue_once(errors, f"{field}:declared_value_does_not_match_ledger")
    return errors


def enrich_coverage(ledger):
    if not isinstance(ledger, dict):
        return ledger
    enriched = copy.deepcopy(ledger)
    enriched.update(summarize_coverage(enriched))
    return enriched


def validate_handoff_keywords(coverage_row, keywords):
    # Candidate source registration is patched above, and this legacy validator
    # already reconciles the exact first-round + branch candidate set.
    return _legacy.validate_handoff_keywords(coverage_row, keywords)


def add_required_branch_seed(*args, **kwargs):
    branch = _legacy.add_required_branch_seed(*args, **kwargs)
    branch["expansions"] = {
        "status": NOT_RUN,
        "blocked_reason": "branch Google expansion acquisition not run",
    }
    return branch


# Re-export helpers used by the test suite and existing callers.
for _name in (
    "_strict_positive_integer",
    "_strict_nonnegative_integer",
    "_candidate_fingerprint",
    "_analysis_fingerprint",
    "_binding",
    "_verify_receipt",
    "_index_row_ledger",
    "_reconcile_row_ledger",
):
    globals()[_name] = getattr(_legacy, _name)
