import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COVERAGE = ROOT / "runtime" / "discovery_coverage.py"
STAGE_VALIDATOR = ROOT / "runtime" / "stage_validator.py"
CONTRACTS = ROOT / "runtime" / "stage_contracts.json"
COVERAGE_TESTS = ROOT / "tests" / "test_discovery_coverage.py"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def contracts():
    return json.loads(CONTRACTS.read_text(encoding="utf-8"))


def expansion_row(**overrides):
    row = {
        "seed": "perfume finder",
        "people_also_ask": [],
        "related_searches": [],
        "expansion_count": 0,
        "result_status": "not_present",
        "market": "US",
        "language": "en",
        "observed_at": "2026-09-02T10:00:00Z",
        "source": "google_serp_expansions",
        "evidence_ref": "evidence/expansions-perfume-finder.png",
    }
    row.update(overrides)
    return row


def test_zero_expansions_is_a_valid_completed_check():
    validator = load(STAGE_VALIDATOR, "stage_validator_expansions_zero")
    errors = validator.validate_stage("discovery_expansions", expansion_row(), contracts())
    assert errors == []


def test_positive_expansions_are_marked_observed():
    validator = load(STAGE_VALIDATOR, "stage_validator_expansions_positive")
    row = expansion_row(
        people_also_ask=["How do I find a perfume that suits me?"],
        related_searches=["perfume finder by notes"],
        expansion_count=2,
        result_status="observed",
    )
    errors = validator.validate_stage("discovery_expansions", row, contracts())
    assert errors == []


def test_expansion_source_is_part_of_candidate_receipt_accounting():
    coverage = load(COVERAGE, "coverage_expansion_source")
    assert coverage.SOURCE_EVIDENCE_TYPES["google_serp_expansions"] == "google_serp_expansions"
    observed = coverage._observed_keywords(
        {
            "people_also_ask": ["How do I find a perfume that suits me?"],
            "related_searches": ["perfume finder by notes", "perfume finder quiz"],
        },
        "google_serp_expansions",
    )
    assert observed == [
        "how do i find a perfume that suits me?",
        "perfume finder by notes",
        "perfume finder quiz",
    ]


def test_missing_expansion_check_blocks_full_coverage():
    coverage = load(COVERAGE, "coverage_expansion_missing")
    fixtures = load(COVERAGE_TESTS, "coverage_existing_fixtures")
    ledger = fixtures.full_ledger()

    summary = coverage.summarize_coverage(ledger)

    assert summary["expansions_required_count"] == 3
    assert summary["expansions_pass_count"] == 0
    assert summary["coverage_status"] == "BLOCKED"
    assert summary["formal_handoff_allowed"] is False


def test_branch_promotion_initializes_expansion_check_as_not_run():
    coverage = load(COVERAGE, "coverage_branch_expansion")
    fixtures = load(COVERAGE_TESTS, "coverage_existing_branch_fixtures")
    ledger = fixtures.full_ledger()
    ledger["required_branch_seeds"] = []

    branch = coverage.add_required_branch_seed(
        ledger,
        originating_candidate_id="candidate-alcohol",
        parent_seed="wedding calculator",
        branch_reason="distinct observed demand branch",
    )

    assert branch["expansions"]["status"] == "NOT_RUN"
    assert branch["expansions"]["blocked_reason"]
