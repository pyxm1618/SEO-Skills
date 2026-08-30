#!/usr/bin/env python3
"""Validate the finite coverage ledger for a Traditional Discovery run.

This module deliberately owns a ledger and a final gate, not a crawler. Source
collectors remain responsible for obtaining real observations; this module
checks that every required acquisition remains represented, that branch seeds
are observed candidates, and that a complete ledger is eligible for handoff.
"""

import copy
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BINDING_PATH = ROOT / "evidence_binding.py"

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

SOURCE_EVIDENCE_TYPES = {
    "google_autocomplete": "google_autocomplete",
    "semrush_ideas": "semrush_ideas",
    "semrush_competitor_organic": "semrush_competitor_organic",
}


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


def _binding():
    spec = importlib.util.spec_from_file_location("seo_discovery_coverage_binding", BINDING_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _observed_keywords(normalized, evidence_type):
    if evidence_type == "google_autocomplete":
        return [_norm_keyword(value) for value in normalized.get("suggestions", [])]
    return [_norm_keyword(row.get("keyword")) for row in normalized.get("rows", []) if isinstance(row, dict)]


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


def _check_acquisition(item, key, label, evidence_type, identity_field, identity, production, issue):
    record = item.get(key) if isinstance(item, dict) else None
    if not isinstance(record, dict):
        issue(f"{label}:{key}:record_required")
        return ""
    status = _status(record)
    if status not in VALID_ACQUISITION_STATUSES:
        issue(f"{label}:{key}:invalid_status:{status or 'missing'}")
        return status
    if status == PASS:
        ref = _receipt_ref(record)
        if not ref:
            issue(f"{label}:{key}:PASS_requires_evidence_receipt")
        elif production:
            _verify_receipt(ref, evidence_type, identity_field, identity, f"{label}:{key}", issue)
    else:
        reason = _reason(record)
        if not reason:
            issue(f"{label}:{key}:{status}_requires_blocked_reason")
        issue(f"{label}:{key}:status={status or 'missing'}:{reason or 'unreviewed'}")
    return status


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
        autocomplete_status = _check_acquisition(
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
            semrush_status = _check_acquisition(
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
        if not ref:
            issue(f"{label}.evidence_receipt_ref:required")
        normalized = None
        if production and source in SOURCE_EVIDENCE_TYPES and ref:
            identity_field = "competitor_domain" if source == "semrush_competitor_organic" else None
            identity = candidate.get("competitor_domain") if identity_field else None
            if identity_field and not _text(identity):
                issue(f"{label}.competitor_domain:required")
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
        if not branch_key:
            issue(f"{label}.branch_seed:required")
        elif branch_key in root_seed_keys:
            issue(f"{label}.branch_seed:cycle_or_duplicate_with_required_seed")
        elif branch_key in seen_branch_keys:
            issue(f"{label}.branch_seed:duplicate")
        else:
            seen_branch_keys.add(branch_key)
        if not parent_key:
            issue(f"{label}.parent_seed:required")
        elif parent_key not in root_seed_keys and parent_key not in seen_branch_keys:
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
        if isinstance(depth, bool):
            issue(f"{label}.depth:must_be_positive_integer")
        else:
            try:
                parsed_depth = int(depth)
            except (TypeError, ValueError):
                parsed_depth = 0
                issue(f"{label}.depth:must_be_positive_integer")
            if parsed_depth <= 0:
                issue(f"{label}.depth:must_be_positive_integer")
            elif parsed_depth > max_branch_depth:
                issue(f"{label}.depth:branch_safety_limit_exceeded:{parsed_depth}>{max_branch_depth}")
        if candidate is not None:
            candidate_keyword = _text(candidate.get("keyword"))
            candidate_source = _text(candidate.get("source"))
            candidate_ref = _candidate_receipt_ref(candidate)
            if _norm_keyword(candidate_keyword) != branch_key:
                issue(f"{label}:branch_seed_not_equal_to_observed_candidate_keyword")
            if source != candidate_source:
                issue(f"{label}.source:provenance_mismatch")
            if branch_ref != candidate_ref:
                issue(f"{label}.evidence_ref:provenance_mismatch")
        autocomplete_status = _check_acquisition(
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
        if full_route:
            semrush_status = _check_acquisition(
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
        status = _status(source)
        if not source_id:
            issue(f"{label}.source_id:required")
        if status not in VALID_ACQUISITION_STATUSES:
            issue(f"{label}.status:invalid_status:{status or 'missing'}")
        elif status == PASS and not _receipt_ref(source):
            issue(f"{label}:PASS_requires_evidence_receipt")
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


def add_required_branch_seed(
    ledger,
    originating_candidate_id,
    parent_seed,
    branch_reason,
    depth=1,
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
    try:
        parsed_depth = _strict_positive_integer(depth)
    except (TypeError, ValueError) as exc:
        raise CoverageContractError("branch depth must be a positive integer") from exc

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
    if parsed_depth > max_branch_depth:
        raise CoverageContractError("branch depth exceeds the configured safety limit")
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
    if _norm_keyword(parent_seed) not in root_keys | existing_keys:
        raise CoverageContractError("parent seed must already be visited")

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
