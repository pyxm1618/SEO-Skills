import importlib.util
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
COVERAGE = ROOT / "runtime" / "discovery_coverage.py"
STAGE_VALIDATOR = ROOT / "runtime" / "stage_validator.py"
CONTRACTS = ROOT / "runtime" / "stage_contracts.json"
HOOK = ROOT / "runtime" / "codex_stage_hook.py"
GOOGLE_COLLECTOR = ROOT / "runtime" / "collectors" / "google_live_collector.py"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_hook(name):
    return load_module(name, HOOK)


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
    source = "google_autocomplete" if candidate_id == "candidate-alcohol" else "semrush_ideas"
    item = {
        "branch_seed": branch_seed,
        "parent_seed": parent_seed,
        "originating_candidate_id": candidate_id,
        "source": source,
        "evidence_ref": f"evidence/{candidate_id}-{'google' if source == 'google_autocomplete' else 'semrush'}.receipt.json",
        "branch_reason": "distinct observed demand branch",
        "analysis_status": "required",
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
            "source_seed": "wedding calculator",
            "evidence_receipt_ref": "evidence/candidate-alcohol-google.receipt.json",
        },
        {
            "candidate_id": "candidate-timeline",
            "keyword": "wedding timeline calculator",
            "source": "semrush_ideas",
            "source_seed": "wedding calculator",
            "evidence_receipt_ref": "evidence/candidate-timeline-semrush.receipt.json",
        },
    ]
    upstream_input = {
        "schema": "seo-discovery-input/v1",
        "batch_id": "batch-1",
        "root_handoff_receipt_ref": "evidence/root-handoff.receipt.json",
        "root_handoff_receipt_sha256": "0" * 64,
        "seed_plan": {
            "original_seed_count": 3,
            "seeds": ["wedding calculator", "wedding planner", "wedding budget"],
        },
        "candidate_inventory": {
            "original_candidate_count": len(observed),
            "candidates": [dict(candidate) for candidate in observed],
        },
        "candidate_analysis": [
            {
                "candidate_id": "candidate-alcohol",
                "analysis_status": "COMPLETE",
                "branch_required": True,
                "analysis_reason": "distinct observed demand branch",
            },
            {
                "candidate_id": "candidate-timeline",
                "analysis_status": "COMPLETE",
                "branch_required": True,
                "analysis_reason": "distinct observed demand branch",
            },
        ],
    }
    return {
        "batch_id": "batch-1",
        "discovery_mode": "full",
        "required_seeds": [
            _required_seed("wedding calculator"),
            _required_seed("wedding planner"),
            _required_seed("wedding budget"),
        ],
        "observed_candidates": observed,
        "upstream_input": upstream_input,
        "candidate_analysis": [
            {
                "candidate_id": "candidate-alcohol",
                "analysis_status": "COMPLETE",
                "branch_required": True,
                "analysis_reason": "distinct observed demand branch",
            },
            {
                "candidate_id": "candidate-timeline",
                "analysis_status": "COMPLETE",
                "branch_required": True,
                "analysis_reason": "distinct observed demand branch",
            },
        ],
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


def test_explicit_google_only_route_is_not_formal_full_handoff():
    coverage = load_module("discovery_coverage_diagnostic", COVERAGE)
    ledger = full_ledger()
    ledger["discovery_mode"] = "diagnostic_google_only"

    summary = coverage.summarize_coverage(ledger)

    assert summary["coverage_status"] == "BLOCKED"
    assert summary["formal_handoff_allowed"] is False
    assert any("not_full" in reason for reason in summary["blocked_reasons"])


def test_branch_promotion_derives_exact_keyword_from_observed_candidate():
    coverage = load_module("discovery_coverage_branch_promotion", COVERAGE)
    ledger = full_ledger()
    ledger["required_branch_seeds"] = []

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


def test_branch_promotion_rejects_invalid_safety_configuration():
    coverage = load_module("discovery_coverage_branch_config", COVERAGE)
    ledger = full_ledger()
    ledger["required_branch_seeds"] = []
    ledger["max_branch_seeds"] = "invalid"

    with pytest.raises(coverage.CoverageContractError, match="branch"):
        coverage.add_required_branch_seed(
            ledger,
            originating_candidate_id="candidate-alcohol",
            parent_seed="wedding calculator",
            branch_reason="invalid safety configuration must fail closed",
        )


def test_branch_promotion_enforces_depth_and_visited_parent_guards():
    coverage = load_module("discovery_coverage_branch_guards", COVERAGE)
    ledger = full_ledger()
    ledger["required_branch_seeds"] = []

    with pytest.raises(coverage.CoverageContractError, match="depth"):
        coverage.add_required_branch_seed(
            ledger,
            originating_candidate_id="candidate-alcohol",
            parent_seed="wedding calculator",
            branch_reason="depth limit must stop promotion",
            depth=2,
        )

    with pytest.raises(coverage.CoverageContractError, match="parent"):
        coverage.add_required_branch_seed(
            ledger,
            originating_candidate_id="candidate-alcohol",
            parent_seed="unvisited demand branch",
            branch_reason="unknown parents must not enter the branch queue",
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


def test_coverage_cannot_shrink_below_upstream_seed_and_candidate_inventory():
    coverage = load_module("discovery_coverage_upstream_inventory", COVERAGE)
    ledger = full_ledger()
    upstream_candidates = [dict(candidate) for candidate in ledger["observed_candidates"]]
    ledger["upstream_input"] = {
        "batch_id": "batch-1",
        "schema": "seo-discovery-input/v1",
        "root_handoff_receipt_ref": "evidence/root-handoff.receipt.json",
        "root_handoff_receipt_sha256": "0" * 64,
        "seed_plan": {
            "original_seed_count": 3,
            "seeds": ["wedding calculator", "wedding planner", "wedding budget"],
        },
        "candidate_inventory": {
            "original_candidate_count": len(upstream_candidates),
            "candidates": upstream_candidates,
        },
        "candidate_analysis": [
            {
                "candidate_id": candidate["candidate_id"],
                "analysis_status": "COMPLETE",
                "branch_required": True,
                "analysis_reason": "distinct observed demand branch",
            }
            for candidate in upstream_candidates
        ],
    }
    ledger["candidate_analysis"] = [
        {
            "candidate_id": candidate["candidate_id"],
            "analysis_status": "COMPLETE",
            "branch_required": True,
            "analysis_reason": "distinct observed demand branch",
        }
        for candidate in upstream_candidates
    ]
    ledger["required_seeds"] = ledger["required_seeds"][:1]
    ledger["observed_candidates"] = []
    ledger["required_branch_seeds"] = []

    errors = coverage.validate_coverage(ledger)

    assert errors
    assert any("upstream" in error.lower() or "inventory" in error.lower() for error in errors)


def test_branch_parent_must_match_candidate_source_seed_and_self_cycle_is_denied():
    coverage = load_module("discovery_coverage_branch_parent_provenance", COVERAGE)
    ledger = full_ledger()
    ledger["required_branch_seeds"][0]["parent_seed"] = "wedding planner"

    errors = coverage.validate_coverage(ledger)

    assert errors
    assert any("parent" in error.lower() or "provenance" in error.lower() for error in errors)

    cycle_ledger = full_ledger()
    cycle_ledger["required_branch_seeds"][0]["branch_seed"] = "wedding alcohol calculator"
    cycle_ledger["required_branch_seeds"][0]["parent_seed"] = "wedding alcohol calculator"

    cycle_errors = coverage.validate_coverage(cycle_ledger)

    assert cycle_errors
    assert any("cycle" in error.lower() or "parent" in error.lower() for error in cycle_errors)


def test_candidate_analysis_branch_decision_cannot_be_rewritten_in_coverage_ledger():
    coverage = load_module("discovery_coverage_authoritative_analysis", COVERAGE)
    ledger = full_ledger()
    ledger["candidate_analysis"][0]["branch_required"] = False

    errors = coverage.validate_coverage(ledger)

    assert errors
    assert any("authoritative" in error.lower() for error in errors)


def test_production_other_mandatory_source_must_have_verifiable_receipt():
    coverage = load_module("discovery_coverage_other_source_receipt", COVERAGE)
    ledger = full_ledger()
    ledger["other_mandatory_sources"] = [
        {
            "source_id": "related-searches",
            "evidence_type": "google_autocomplete",
            "status": "PASS",
            "evidence_receipt_ref": "does-not-exist.receipt.json",
        }
    ]

    errors = coverage.validate_coverage(ledger, production=True)

    assert errors
    assert any("other_mandatory_source" in error and "evidence" in error for error in errors)


def test_production_input_manifest_binds_root_receipt_to_seed_plan(tmp_path):
    coverage = load_module("discovery_input_root_receipt", COVERAGE)
    root_receipt = tmp_path / "root.receipt.json"
    root_receipt.write_text(
        json.dumps(
            {
                "schema": "seo-root-natural-seeds/v1",
                "status": "PASS",
                "batch_id": "batch-1",
                "seed_plan": {"original_seed_count": 1, "seeds": ["different seed"]},
            }
        ),
        encoding="utf-8",
    )
    manifest = {
        "schema": "seo-discovery-input/v1",
        "batch_id": "batch-1",
        "root_handoff_receipt_ref": str(root_receipt),
        "root_handoff_receipt_sha256": hashlib.sha256(root_receipt.read_bytes()).hexdigest(),
        "seed_plan": {"original_seed_count": 1, "seeds": ["wedding calculator"]},
        "candidate_inventory": {"original_candidate_count": 0, "candidates": []},
        "candidate_analysis": [],
    }

    errors = coverage.validate_input_manifest(manifest, production=True)

    assert any("root_handoff_receipt_ref:seed_plan_mismatch" in error for error in errors)


def test_production_handoff_rejects_nonexistent_coverage_receipt():
    validator = load_module("discovery_handoff_receipt_validation", STAGE_VALIDATOR)
    contracts = json.loads(CONTRACTS.read_text(encoding="utf-8"))
    payload = {
        "batch_id": "batch-1",
        "required_seed_count": 1,
        "autocomplete_pass_count": 1,
        "status": "PASS",
        "coverage_status": "PASS",
        "coverage_receipt_ref": "does-not-exist.receipt.json",
    }

    errors = validator.validate_stage("discovery_handoff", payload, contracts, production=True)

    assert errors
    assert any("coverage" in error.lower() and "receipt" in error.lower() for error in errors)


def test_competitor_stage_validator_keeps_top_level_envelope_intact():
    validator = load_module("competitor_stage_envelope", STAGE_VALIDATOR)
    contracts = json.loads(CONTRACTS.read_text(encoding="utf-8"))
    payload = {
        "competitor_domain": "competitor.example",
        "rows": [{"keyword": "wedding timeline"}],
        "observed_at": "2026-08-30T00:00:00Z",
        "metric_source": "Semrush",
        "metric_database": "us",
        "metric_stage": "competitor_organic",
        "relay_origin": "https://sem.3ue.com/",
        "provenance_ref": "capture.json",
    }

    complete, blocked = validator.validate_payload(
        "discovery_semrush_competitor_organic", payload, contracts
    )

    assert complete == [payload]
    assert blocked == []


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


def test_production_coverage_rejects_handwritten_source_receipts():
    coverage = load_module("discovery_coverage_production", COVERAGE)

    errors = coverage.validate_coverage(full_ledger(), production=True)

    assert errors
    assert any("evidence_receipt_invalid" in error for error in errors)
    assert any("upstream_input:validation_receipt_ref:required_for_production" in error for error in errors)


def test_production_coverage_requires_candidate_to_be_in_observed_source_payload(tmp_path):
    coverage = load_module("discovery_coverage_candidate_observation", COVERAGE)
    screenshot = tmp_path / "parent-google.png"
    screenshot.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
        b"\x00\x00\x00\x0aIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    observation = tmp_path / "parent-google.observation.json"
    observed_at = "2026-08-30T00:00:00+00:00"
    observation.write_text(
        json.dumps(
            {
                "page_url": "https://www.google.com/search?q=wedding+calculator",
                "seed": "wedding calculator",
                "suggestions": ["wedding alcohol calculator"],
                "country": "US",
                "language": "en",
                "observed_at": observed_at,
            }
        ),
        encoding="utf-8",
    )
    normalized = tmp_path / "parent-google.json"
    receipt = tmp_path / "parent-google.receipt.json"
    normalized.write_text(
        json.dumps(
            {
                "seed": "wedding calculator",
                "suggestions": ["wedding alcohol calculator"],
                "country": "US",
                "language": "en",
                "observed_at": observed_at,
                "source": "google_autocomplete",
                "evidence_ref": str(screenshot),
                "observation_ref": str(observation),
                "evidence_receipt_ref": str(receipt),
            }
        ),
        encoding="utf-8",
    )
    receipt.write_text(
        json.dumps(
            {
                "schema": "seo-observed-evidence/v2",
                "collector": "google_live_collector",
                "collector_source_sha256": hashlib.sha256(GOOGLE_COLLECTOR.read_bytes()).hexdigest(),
                "evidence_type": "google_autocomplete",
                "normalized_ref": str(normalized),
                "normalized_sha256": hashlib.sha256(normalized.read_bytes()).hexdigest(),
                "artifacts": [
                    {"role": "screenshot", "path": str(screenshot), "sha256": hashlib.sha256(screenshot.read_bytes()).hexdigest()},
                    {"role": "structured_observation", "path": str(observation), "sha256": hashlib.sha256(observation.read_bytes()).hexdigest()},
                ],
            }
        ),
        encoding="utf-8",
    )
    ledger = full_ledger()
    ledger["observed_candidates"][0]["evidence_receipt_ref"] = str(receipt)

    errors = coverage.validate_coverage(ledger, production=True)

    assert errors
    assert not any("observed_candidate[0]:evidence_identity_mismatch" in error for error in errors)


def test_discovery_handoff_contract_requires_coverage_receipt():
    validator = load_module("discovery_handoff_contract", STAGE_VALIDATOR)
    contracts = json.loads(CONTRACTS.read_text(encoding="utf-8"))
    payload = {
        "batch_id": "batch-1",
        "required_seed_count": 1,
        "autocomplete_pass_count": 1,
        "status": "PASS",
    }

    errors = validator.validate_stage("discovery_handoff", payload, contracts)

    assert any("coverage" in error for error in errors)


def _write_google_receipt(tmp_path):
    collector = ROOT / "runtime" / "collectors" / "google_live_collector.py"
    screenshot = tmp_path / "google.png"
    screenshot.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
        b"\x00\x00\x00\x0aIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    observed_at = "2026-08-30T00:00:00+00:00"
    observation = tmp_path / "google.observation.json"
    observation.write_text(
        json.dumps(
            {
                "page_url": "https://www.google.com/search?q=wedding+calculator",
                "seed": "wedding calculator",
                "suggestions": ["wedding alcohol calculator"],
                "country": "US",
                "language": "en",
                "observed_at": observed_at,
            }
        ),
        encoding="utf-8",
    )
    normalized = tmp_path / "google.json"
    receipt = tmp_path / "google.receipt.json"
    normalized.write_text(
        json.dumps(
            {
                "seed": "wedding calculator",
                "suggestions": ["wedding alcohol calculator"],
                "country": "US",
                "language": "en",
                "observed_at": observed_at,
                "source": "google_autocomplete",
                "evidence_ref": str(screenshot),
                "observation_ref": str(observation),
                "evidence_receipt_ref": str(receipt),
            }
        ),
        encoding="utf-8",
    )
    receipt.write_text(
        json.dumps(
            {
                "schema": "seo-observed-evidence/v2",
                "collector": "google_live_collector",
                "collector_source_sha256": hashlib.sha256(collector.read_bytes()).hexdigest(),
                "evidence_type": "google_autocomplete",
                "normalized_ref": str(normalized),
                "normalized_sha256": hashlib.sha256(normalized.read_bytes()).hexdigest(),
                "artifacts": [
                    {"role": "screenshot", "path": str(screenshot), "sha256": hashlib.sha256(screenshot.read_bytes()).hexdigest()},
                    {"role": "structured_observation", "path": str(observation), "sha256": hashlib.sha256(observation.read_bytes()).hexdigest()},
                ],
            }
        ),
        encoding="utf-8",
    )
    return normalized, receipt


def _write_ideas_receipt(tmp_path):
    semrush_path = ROOT / "runtime" / "collectors" / "semrush_relay_collector.py"
    semrush = load_module("discovery_coverage_ideas_fixture", semrush_path)
    capture = tmp_path / "semrush.capture.json"
    capture.write_text(json.dumps({"captured": True}), encoding="utf-8")
    descriptor = {
        "path": "/captured/current-path",
        "method": "POST",
        "body": {},
        "capture_observed_at": "2026-08-30T00:00:00+00:00",
        "capture_evidence_ref": str(capture),
        "mode": "ideas",
        "metric_database": "us",
        "seed": "wedding calculator",
    }
    response = {"jsonrpc": "2.0", "result": [{"phrase": "wedding cost calculator", "volume": 900, "difficulty": 22}]}
    observed_at = "2026-08-30T00:00:01+00:00"
    raw = tmp_path / "ideas.raw.json"
    raw.write_text(
        json.dumps(
            {
                "observed_at": observed_at,
                "relay_origin": "https://sem.3ue.com/",
                "request_method": descriptor["method"],
                "request_path": descriptor["path"],
                "capture_observed_at": descriptor["capture_observed_at"],
                "capture_evidence_ref": str(capture),
                "mode": "ideas",
                "metric_database": "us",
                "seed": descriptor["seed"],
                "response": response,
            }
        ),
        encoding="utf-8",
    )
    normalized = tmp_path / "ideas.json"
    receipt = tmp_path / "ideas.receipt.json"
    normalized.write_text(
        json.dumps(
            dict(
                semrush.normalize_ideas(response, descriptor, observed_at, str(raw)),
                evidence_receipt_ref=str(receipt),
            )
        ),
        encoding="utf-8",
    )
    receipt.write_text(
        json.dumps(
            {
                "schema": "seo-observed-evidence/v2",
                "collector": "semrush_relay_collector",
                "collector_source_sha256": hashlib.sha256(semrush_path.read_bytes()).hexdigest(),
                "evidence_type": "semrush_ideas",
                "normalized_ref": str(normalized),
                "normalized_sha256": hashlib.sha256(normalized.read_bytes()).hexdigest(),
                "artifacts": [
                    {"role": "relay_raw_response", "path": str(raw), "sha256": hashlib.sha256(raw.read_bytes()).hexdigest()},
                    {"role": "current_network_capture", "path": str(capture), "sha256": hashlib.sha256(capture.read_bytes()).hexdigest()},
                ],
            }
        ),
        encoding="utf-8",
    )
    return normalized, receipt


def _run_production_stage(stage, input_path, report_path):
    return subprocess.run(
        [
            sys.executable,
            str(STAGE_VALIDATOR),
            "--stage",
            stage,
            "--input",
            str(input_path),
            "--report",
            str(report_path),
            "--production",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def _write_input_manifest_receipt(tmp_path, manifest):
    root_receipt = tmp_path / "root-handoff.receipt.json"
    root_receipt.write_text(
        json.dumps(
            {
                "schema": "seo-root-natural-seeds/v1",
                "status": "PASS",
                "batch_id": manifest["batch_id"],
                "seed_plan": manifest["seed_plan"],
            }
        ),
        encoding="utf-8",
    )
    manifest["root_handoff_receipt_sha256"] = hashlib.sha256(root_receipt.read_bytes()).hexdigest()
    manifest_path = tmp_path / "input-manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    report_path = tmp_path / "input-manifest.report.json"
    result = _run_production_stage("discovery_input_manifest", manifest_path, report_path)
    assert result.returncode == 0, result.stderr
    return manifest_path, report_path.with_suffix(".receipt.json")


def test_production_coverage_receipt_binds_a_formal_handoff(tmp_path):
    google_input, google_receipt = _write_google_receipt(tmp_path)
    _ideas_input, ideas_receipt = _write_ideas_receipt(tmp_path)
    input_manifest = {
        "schema": "seo-discovery-input/v1",
        "batch_id": "batch-formal",
        "root_handoff_receipt_ref": str(tmp_path / "root-handoff.receipt.json"),
        "seed_plan": {
            "original_seed_count": 1,
            "seeds": ["wedding calculator"],
        },
        "candidate_inventory": {
            "original_candidate_count": 1,
            "candidates": [
                {
                    "candidate_id": "candidate-alcohol",
                    "keyword": "wedding alcohol calculator",
                    "source": "google_autocomplete",
                    "source_seed": "wedding calculator",
                    "evidence_receipt_ref": str(google_receipt),
                }
            ],
        },
        "candidate_analysis": [
            {
                "candidate_id": "candidate-alcohol",
                "analysis_status": "COMPLETE",
                "branch_required": False,
                "analysis_reason": "reviewed; no branch expansion required",
            }
        ],
    }
    _manifest_path, input_manifest_receipt = _write_input_manifest_receipt(tmp_path, input_manifest)
    ledger = {
        "batch_id": "batch-formal",
        "discovery_mode": "full",
        "required_seeds": [
            {
                "seed": "wedding calculator",
                "autocomplete": {"status": "PASS", "evidence_receipt_ref": str(google_receipt)},
                "semrush": {"status": "PASS", "evidence_receipt_ref": str(ideas_receipt)},
            }
        ],
        "observed_candidates": [
            {
                "candidate_id": "candidate-alcohol",
                "keyword": "wedding alcohol calculator",
                "source": "google_autocomplete",
                "source_seed": "wedding calculator",
                "evidence_receipt_ref": str(google_receipt),
            }
        ],
        "upstream_input": dict(input_manifest, validation_receipt_ref=str(input_manifest_receipt)),
        "candidate_analysis": [
            {
                "candidate_id": "candidate-alcohol",
                "analysis_status": "COMPLETE",
                "branch_required": False,
                "analysis_reason": "reviewed; no branch expansion required",
            }
        ],
        "required_branch_seeds": [],
        "competitor_sweep": {"configured": False, "domains": [], "status": "not_configured"},
        "other_mandatory_sources": [],
        "max_branch_depth": 1,
        "max_branch_seeds": 5,
    }
    ledger_path = tmp_path / "coverage-input.json"
    ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
    autocomplete_report = tmp_path / "autocomplete.report.json"
    coverage_report = tmp_path / "coverage.report.json"
    assert _run_production_stage("discovery_autocomplete", google_input, autocomplete_report).returncode == 0
    assert _run_production_stage("discovery_coverage", ledger_path, coverage_report).returncode == 0

    coverage_receipt = coverage_report.with_suffix(".receipt.json")
    handoff_input = tmp_path / "handoff-input.json"
    handoff_input.write_text(
        json.dumps(
            {
                "batch_id": "batch-formal",
                "required_seed_count": 1,
                "autocomplete_pass_count": 1,
                "status": "PASS",
                "coverage_status": "PASS",
                "coverage_receipt_ref": str(coverage_receipt),
            }
        ),
        encoding="utf-8",
    )
    handoff_report = tmp_path / "handoff.report.json"
    assert _run_production_stage("discovery_handoff", handoff_input, handoff_report).returncode == 0

    manifest = {
        "run_id": "formal-coverage-run",
        "route": "traditional",
        "status": "COMPLETE",
        "stages": {
            "discovery_autocomplete": {
                "status": "PASS",
                "validation_receipt_ref": str(autocomplete_report.with_suffix(".receipt.json")),
            },
            "discovery_coverage": {"status": "PASS", "validation_receipt_ref": str(coverage_receipt)},
            "discovery_handoff": {
                "status": "PASS",
                "validation_receipt_ref": str(handoff_report.with_suffix(".receipt.json")),
                "coverage_receipt_ref": str(coverage_receipt),
            },
        },
        "candidates": {},
    }
    manifest_path = tmp_path / "active.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    hook_result = subprocess.run(
        [sys.executable, str(HOOK), "stop"],
        input=json.dumps({"hook_event_name": "Stop", "stop_hook_active": False}),
        cwd=ROOT,
        env=dict(os.environ, SEO_RUN_MANIFEST=str(manifest_path)),
        capture_output=True,
        text=True,
    )

    assert hook_result.returncode == 0, hook_result.stderr


def test_production_coverage_cannot_shrink_a_verified_upstream_inventory(tmp_path):
    coverage = load_module("discovery_coverage_production_inventory", COVERAGE)
    _google_input, google_receipt = _write_google_receipt(tmp_path)
    input_manifest = {
        "schema": "seo-discovery-input/v1",
        "batch_id": "batch-shrink",
        "root_handoff_receipt_ref": str(tmp_path / "root-handoff.receipt.json"),
        "seed_plan": {
            "original_seed_count": 1,
            "seeds": ["wedding calculator"],
        },
        "candidate_inventory": {
            "original_candidate_count": 1,
            "candidates": [
                {
                    "candidate_id": "candidate-alcohol",
                    "keyword": "wedding alcohol calculator",
                    "source": "google_autocomplete",
                    "source_seed": "wedding calculator",
                    "evidence_receipt_ref": str(google_receipt),
                }
            ],
        },
        "candidate_analysis": [
            {
                "candidate_id": "candidate-alcohol",
                "analysis_status": "COMPLETE",
                "branch_required": False,
                "analysis_reason": "reviewed; no branch expansion required",
            }
        ],
    }
    _manifest_path, manifest_receipt = _write_input_manifest_receipt(tmp_path, input_manifest)
    ledger = {
        "batch_id": "batch-shrink",
        "discovery_mode": "full",
        "upstream_input": dict(input_manifest, validation_receipt_ref=str(manifest_receipt)),
        "required_seeds": [],
        "observed_candidates": [],
        "candidate_analysis": [],
        "required_branch_seeds": [],
        "competitor_sweep": {"configured": False, "domains": [], "status": "not_configured"},
        "other_mandatory_sources": [],
        "max_branch_depth": 1,
        "max_branch_seeds": 5,
    }

    errors = coverage.validate_coverage(ledger, production=True)

    assert any("required_seeds:count_below_upstream" in error for error in errors)
    assert any("observed_candidates:count_below_upstream" in error for error in errors)


def test_production_candidate_source_seed_must_match_observed_receipt(tmp_path):
    coverage = load_module("discovery_coverage_candidate_source_seed", COVERAGE)
    _google_input, google_receipt = _write_google_receipt(tmp_path)
    ledger = full_ledger()
    candidate = ledger["observed_candidates"][0]
    candidate["source_seed"] = "wedding planner"
    candidate["evidence_receipt_ref"] = str(google_receipt)
    ledger["upstream_input"]["candidate_inventory"]["candidates"][0] = dict(candidate)

    errors = coverage.validate_coverage(ledger, production=True)

    assert any("observed_candidate[0]:evidence_identity_mismatch" in error for error in errors)


def _handoff_manifest(coverage_receipt_ref="coverage.receipt.json"):
    return {
        "run_id": "traditional-coverage-run",
        "route": "traditional",
        "status": "COMPLETE",
        "stages": {
            "discovery_autocomplete": {"status": "PASS", "validation_receipt_ref": "autocomplete.receipt.json"},
            "discovery_coverage": {
                "status": "PASS",
                "validation_receipt_ref": "coverage.receipt.json",
            },
            "discovery_handoff": {
                "status": "PASS",
                "validation_receipt_ref": "handoff.receipt.json",
                "coverage_status": "PASS",
                "coverage_receipt_ref": coverage_receipt_ref,
            },
        },
        "candidates": {},
    }


def test_traditional_complete_requires_coverage_stage(monkeypatch):
    hook = load_hook("discovery_coverage_missing_hook")
    monkeypatch.setattr(hook, "_verify_validation_receipt", lambda *args, **kwargs: (True, ""))
    manifest = _handoff_manifest()
    manifest["stages"].pop("discovery_coverage")

    valid, reason = hook._verify_completion_requirements(manifest)

    assert valid is False
    assert "discovery_coverage" in reason


def test_handoff_cannot_reference_a_different_coverage_receipt(monkeypatch):
    hook = load_hook("discovery_coverage_binding_hook")
    monkeypatch.setattr(hook, "_verify_validation_receipt", lambda *args, **kwargs: (True, ""))
    manifest = _handoff_manifest(coverage_receipt_ref="wrong-coverage.receipt.json")

    valid, reason = hook._verify_completion_requirements(manifest)

    assert valid is False
    assert "coverage" in reason.lower()


def test_protected_handoff_command_requires_coverage_pass(monkeypatch):
    hook = load_hook("discovery_coverage_pretool_hook")
    monkeypatch.setattr(hook, "_verify_validation_receipt", lambda *args, **kwargs: (True, ""))
    manifest = _handoff_manifest()
    manifest["stages"]["discovery_coverage"] = {
        "status": "BLOCKED",
        "blocked_reason": "Semrush Ideas relay unavailable",
    }
    payload = {
        "tool_name": "Bash",
        "tool_input": {
            "command": "python3 runtime/stage_validator.py --stage discovery_handoff --input handoff.json"
        },
    }

    assert hook.pre_tool_use(payload, manifest) == 2
