import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
COVERAGE = ROOT / "runtime" / "discovery_coverage.py"
STAGE_VALIDATOR = ROOT / "runtime" / "stage_validator.py"
CONTRACTS = ROOT / "runtime" / "stage_contracts.json"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _source_status(status="PASS", receipt=None, reason=None):
    value = {"status": status}
    if status == "PASS":
        value["evidence_receipt_ref"] = receipt or f"evidence/{status.lower()}.receipt.json"
    elif reason:
        value["blocked_reason"] = reason
    return value


def _required_seed(seed, autocomplete="PASS", semrush="PASS"):
    item = {"seed": seed}
    item["autocomplete"] = _source_status(autocomplete, f"evidence/{seed}-google.receipt.json", "Google blocked")
    item["semrush"] = _source_status(semrush, f"evidence/{seed}-semrush.receipt.json", "Semrush blocked")
    return item


def _branch(branch_seed, candidate_id, parent_seed="wedding calculator", depth=1, autocomplete="PASS", semrush="PASS"):
    item = {
        "branch_seed": branch_seed,
        "parent_seed": parent_seed,
        "originating_candidate_id": candidate_id,
        "branch_reason": "distinct observed demand branch",
        "depth": depth,
        "autocomplete": _source_status(autocomplete, f"evidence/{candidate_id}-google.receipt.json", "branch Google blocked"),
        "semrush": _source_status(semrush, f"evidence/{candidate_id}-semrush.receipt.json", "branch Semrush blocked"),
    }
    return item


def full_ledger():
    observed = [
        {
            "candidate_id": "candidate-alcohol",
            "keyword": "wedding alcohol calculator",
            "source": "google_autocomplete",
            "evidence_receipt_ref": "evidence/candidate-alcohol-google.receipt.json",
        },
        {
            "candidate_id": "candidate-timeline",
            "keyword": "wedding timeline calculator",
            "source": "semrush_ideas",
            "evidence_receipt_ref": "evidence/candidate-timeline-semrush.receipt.json",
        },
    ]
    return {
        "batch_id": "batch-1",
        "discovery_mode": "full",
        "required_seeds": [
            _required_seed("wedding calculator"),
            _required_seed("wedding planner"),
            _required_seed("wedding budget"),
        ],
        "observed_candidates": observed,
        "required_branch_seeds": [
            _branch("wedding alcohol calculator", "candidate-alcohol"),
            _branch("wedding timeline calculator", "candidate-timeline"),
        ],
        "competitor_sweep": {"configured": False, "domains": [], "status": "not_configured"},
        "other_mandatory_sources": [],
        "max_branch_depth": 1,
        "max_branch_seeds": 5,
    }


def test_full_coverage_counts_all_mandatory_work_and_allows_handoff():
    coverage = load_module("discovery_coverage_happy", COVERAGE)

    summary = coverage.summarize_coverage(full_ledger())

    assert summary["required_seed_count"] == 3
    assert summary["autocomplete_pass_count"] == 3
    assert summary["semrush_required_count"] == 3
    assert summary["semrush_pass_count"] == 3
    assert summary["required_branch_seed_count"] == 2
    assert summary["branch_seed_pass_count"] == 2
    assert summary["branch_autocomplete_pass_count"] == 2
    assert summary["branch_semrush_pass_count"] == 2
    assert summary["competitor_sweep_status"] == "not_configured"
    assert summary["coverage_status"] == "PASS"
    assert summary["formal_handoff_allowed"] is True
    assert coverage.validate_coverage(full_ledger()) == []


def test_missing_google_keeps_required_seed_in_ledger_and_blocks_coverage():
    coverage = load_module("discovery_coverage_google_missing", COVERAGE)
    ledger = full_ledger()
    ledger["required_seeds"][2] = _required_seed("wedding budget", autocomplete="BLOCKED")

    summary = coverage.summarize_coverage(ledger)

    assert len(ledger["required_seeds"]) == 3
    assert summary["required_seed_count"] == 3
    assert summary["autocomplete_pass_count"] == 2
    assert summary["coverage_status"] == "BLOCKED"
    assert any("autocomplete" in reason.lower() for reason in summary["blocked_reasons"])
    assert coverage.validate_coverage(ledger)


def test_full_route_does_not_silently_fallback_when_semrush_is_blocked():
    coverage = load_module("discovery_coverage_semrush_missing", COVERAGE)
    ledger = full_ledger()
    ledger["required_seeds"][1] = _required_seed("wedding planner", semrush="BLOCKED")

    summary = coverage.summarize_coverage(ledger)

    assert summary["semrush_required_count"] == 3
    assert summary["semrush_pass_count"] == 2
    assert summary["coverage_status"] == "BLOCKED"
    assert len(ledger["required_seeds"]) == 3
    assert any("semrush" in reason.lower() for reason in summary["blocked_reasons"])


def test_branch_promotion_derives_exact_keyword_from_observed_candidate():
    coverage = load_module("discovery_coverage_branch_promotion", COVERAGE)
    ledger = full_ledger()

    branch = coverage.add_required_branch_seed(
        ledger,
        originating_candidate_id="candidate-alcohol",
        parent_seed="wedding calculator",
        branch_reason="the observed candidate opens a beverage-planning demand branch",
    )

    assert branch["branch_seed"] == "wedding alcohol calculator"
    assert branch["evidence_ref"] == "evidence/candidate-alcohol-google.receipt.json"
    assert branch["source"] == "google_autocomplete"
    assert ledger["required_branch_seeds"][-1] == branch

    with pytest.raises(coverage.CoverageContractError, match="observed candidate"):
        coverage.add_required_branch_seed(
            ledger,
            originating_candidate_id="missing-candidate",
            parent_seed="wedding calculator",
            branch_reason="cannot prove this candidate was observed",
        )


def test_branch_seed_cannot_cross_candidate_keyword_or_evidence():
    coverage = load_module("discovery_coverage_branch_provenance", COVERAGE)
    ledger = full_ledger()
    ledger["required_branch_seeds"].append(
        {
            "branch_seed": "wedding timeline calculator",
            "parent_seed": "wedding calculator",
            "originating_candidate_id": "candidate-alcohol",
            "evidence_ref": "evidence/candidate-timeline-semrush.receipt.json",
            "branch_reason": "cross-candidate provenance attack",
            "depth": 1,
            "autocomplete": _source_status("PASS", "evidence/x-google.receipt.json"),
            "semrush": _source_status("PASS", "evidence/x-semrush.receipt.json"),
        }
    )

    errors = coverage.validate_coverage(ledger)

    assert any("provenance" in error.lower() or "keyword" in error.lower() for error in errors)


def test_required_branch_blocked_cannot_be_removed_to_make_counts_pass():
    coverage = load_module("discovery_coverage_branch_blocked", COVERAGE)
    ledger = full_ledger()
    ledger["required_branch_seeds"][1] = _branch(
        "wedding timeline calculator", "candidate-timeline", semrush="BLOCKED"
    )

    summary = coverage.summarize_coverage(ledger)

    assert summary["required_branch_seed_count"] == 2
    assert summary["branch_seed_pass_count"] == 1
    assert summary["coverage_status"] == "BLOCKED"
    assert len(ledger["required_branch_seeds"]) == 2


def test_branch_cycles_duplicates_and_configured_budget_are_blocked():
    coverage = load_module("discovery_coverage_branch_safety", COVERAGE)
    ledger = full_ledger()
    ledger["max_branch_seeds"] = 2
    ledger["required_branch_seeds"] = [
        _branch("wedding calculator", "candidate-alcohol"),
        _branch("wedding timeline calculator", "candidate-timeline"),
        _branch("wedding timeline calculator", "candidate-timeline"),
    ]

    errors = coverage.validate_coverage(ledger)

    assert any("cycle" in error.lower() or "duplicate" in error.lower() for error in errors)
    assert any("limit" in error.lower() or "budget" in error.lower() for error in errors)


def test_competitor_not_configured_is_explicit_but_does_not_block_full_route():
    coverage = load_module("discovery_coverage_competitor_not_configured", COVERAGE)
    ledger = full_ledger()

    summary = coverage.summarize_coverage(ledger)

    assert summary["competitor_sweep_configured"] is False
    assert summary["competitor_sweep_status"] == "not_configured"
    assert summary["coverage_status"] == "PASS"


def test_configured_competitor_failure_blocks_full_route():
    coverage = load_module("discovery_coverage_competitor_blocked", COVERAGE)
    ledger = full_ledger()
    ledger["competitor_sweep"] = {
        "configured": True,
        "domains": [{"domain": "competitor.example", "status": "BLOCKED", "blocked_reason": "relay unavailable"}],
        "status": "BLOCKED",
    }

    summary = coverage.summarize_coverage(ledger)

    assert summary["competitor_sweep_configured"] is True
    assert summary["competitor_sweep_status"] == "BLOCKED"
    assert summary["coverage_status"] == "BLOCKED"
    assert any("competitor" in reason.lower() for reason in summary["blocked_reasons"])


def test_stage_validator_emits_computed_coverage_summary():
    coverage = load_module("discovery_coverage_stage_validator", COVERAGE)
    validator = load_module("discovery_coverage_validator", STAGE_VALIDATOR)
    contracts = json.loads(CONTRACTS.read_text(encoding="utf-8"))

    complete, blocked = validator.validate_payload("discovery_coverage", full_ledger(), contracts)

    assert blocked == []
    assert complete[0]["coverage_status"] == "PASS"
    assert complete[0]["required_seed_count"] == 3
    assert complete[0]["semrush_total_required_count"] == 5
    assert coverage.validate_coverage(complete[0]) == []
