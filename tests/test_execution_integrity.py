import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = ROOT / "runtime" / "stage_validator.py"
CONTRACTS_PATH = ROOT / "runtime" / "stage_contracts.json"


def load_validator():
    spec = importlib.util.spec_from_file_location("stage_validator", VALIDATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def exact_row(**overrides):
    row = {
        "keyword": "wedding calculator",
        "volume": 1000,
        "kd": 20,
        "cpc": 0.20,
        "intent": "informational",
        "competition_level": "low",
        "trend": [1] * 12,
        "metric_source": "Semrush",
        "metric_database": "us",
        "metric_stage": "exact",
        "observed_at": "2026-08-26T10:00:00Z",
        "relay_origin": "https://sem.3ue.com/",
        "provenance_ref": "evidence/exact-wedding-calculator.json",
    }
    row.update(overrides)
    return row


def test_exactly_five_skills_and_discovery_exists():
    skills = sorted(p.name for p in (ROOT / "skills").iterdir() if p.is_dir() and (p / "SKILL.md").exists())
    assert skills == sorted([
        "keyword-root-library",
        "seo-keyword-discovery",
        "seo-keyword-selection",
        "seo-page-keyword-mapping",
        "emerging-keyword-monitor",
    ])


def test_selection_thresholds_are_byte_frozen():
    data = (ROOT / "skills" / "seo-keyword-selection" / "references" / "thresholds.json").read_bytes()
    assert hashlib.sha256(data).hexdigest() == "0496b841e48651cecd47e497960362966c6acf63334be802087dd612393ae97d"


def test_stage6_missing_required_metrics_fail():
    validator = load_validator()
    contracts = json.loads(CONTRACTS_PATH.read_text(encoding="utf-8"))
    for field in ("volume", "kd", "cpc"):
        row = exact_row()
        row.pop(field)
        errors = validator.validate_stage("stage6_exact", row, contracts)
        assert any(field in error for error in errors)


def test_stage6_wrong_relay_fails_and_full_evidence_passes():
    validator = load_validator()
    contracts = json.loads(CONTRACTS_PATH.read_text(encoding="utf-8"))
    wrong = validator.validate_stage(
        "stage6_exact",
        exact_row(relay_origin="https://example.com/"),
        contracts,
    )
    assert any("relay_origin" in error for error in wrong)
    assert validator.validate_stage("stage6_exact", exact_row(), contracts) == []


def test_kgr_contract_requires_real_google_intitle():
    validator = load_validator()
    contracts = json.loads(CONTRACTS_PATH.read_text(encoding="utf-8"))
    base = {
        "keyword": "travel checklist",
        "volume": 1000,
        "intitle_results": 50,
        "source": "Google",
        "market": "us",
        "observed_at": "2026-08-26T10:00:00Z",
        "evidence_ref": "evidence/intitle-travel-checklist.png",
    }
    assert validator.validate_stage("kgr_intitle", base, contracts) == []
    fake = dict(base, source="Bing")
    assert any("source" in error for error in validator.validate_stage("kgr_intitle", fake, contracts))
    missing = dict(base)
    missing.pop("intitle_results")
    assert any("intitle_results" in error for error in validator.validate_stage("kgr_intitle", missing, contracts))


def test_serp_contract_requires_real_top_ten_urls():
    validator = load_validator()
    contracts = json.loads(CONTRACTS_PATH.read_text(encoding="utf-8"))
    payload = {
        "keyword": "dream meaning",
        "source": "Google",
        "market": "us",
        "observed_at": "2026-08-26T10:00:00Z",
        "evidence_ref": "evidence/serp-dream-meaning.png",
        "results": [{"rank": i, "url": f"https://example{i}.com/"} for i in range(1, 11)],
    }
    assert validator.validate_stage("serp_review", payload, contracts) == []
    payload["results"] = payload["results"][:9]
    assert any("results" in error for error in validator.validate_stage("serp_review", payload, contracts))


def test_finalist_trend_is_conditional_and_keyword_planner_is_not_required():
    validator = load_validator()
    contracts = json.loads(CONTRACTS_PATH.read_text(encoding="utf-8"))
    finalist = {
        "keyword": "dream meaning",
        "is_finalist": True,
        "google_trends_source": "Google Trends",
        "google_trends_observed_at": "2026-08-26T10:00:00Z",
        "google_trends_evidence_ref": "evidence/trends-dream-meaning.png",
    }
    assert validator.validate_stage("finalist_trend", finalist, contracts) == []
    missing = {"keyword": "dream meaning", "is_finalist": True}
    assert validator.validate_stage("finalist_trend", missing, contracts)
    not_finalist = {"keyword": "dream meaning", "is_finalist": False}
    assert validator.validate_stage("finalist_trend", not_finalist, contracts) == []


def test_missing_zero_and_not_applicable_are_distinct_states():
    validator = load_validator()
    assert validator.value_state(None) == "missing"
    assert validator.value_state(0) == "value"
    assert validator.value_state("not_applicable") == "not_applicable"
