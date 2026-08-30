import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GOOGLE = ROOT / "runtime" / "collectors" / "google_live_collector.py"
VALIDATOR = ROOT / "runtime" / "stage_validator.py"
CONTRACTS = ROOT / "runtime" / "stage_contracts.json"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def google():
    return load_module("google_live_collector_related_red", GOOGLE)


def test_related_parser_keeps_top_separate_from_rising_and_preserves_breakout(google):
    rows = google.parse_trends_related(
        {
            "default": {
                "rankedList": [
                    {"rankedKeyword": [{"query": "wedding dress", "value": 100}]},
                    {
                        "rankedKeyword": [
                            {"query": "micro wedding", "value": "Breakout"},
                            {"query": "wedding content creator", "value": 650},
                        ]
                    },
                ]
            }
        }
    )

    assert rows[0]["query"] == "wedding dress"
    assert rows[0]["relation_type"] == "top"
    assert rows[1]["relation_type"] == "rising"
    assert rows[1]["google_rising_label"] == "Breakout"
    assert rows[1]["is_google_breakout"] is True
    assert rows[1]["rising_value"] is None


def test_related_parser_skips_malformed_rows_and_rejects_missing_payload(google):
    rows = google.parse_trends_related(
        {
            "default": {
                "rankedList": [
                    {
                        "rankedKeyword": [
                            {"query": "valid rising", "value": 20},
                            {"value": 40},
                            {"query": "", "value": 50},
                        ]
                    }
                ]
            }
        }
    )

    assert [row["query"] for row in rows] == ["valid rising"]

    with pytest.raises(RuntimeError, match="related"):
        google.parse_trends_related({})


def test_trends_related_stage_requires_real_payload_fields():
    validator = load_module("stage_validator_related_red", VALIDATOR)
    contracts = json.loads(CONTRACTS.read_text(encoding="utf-8"))
    payload = {
        "anchor": "wedding",
        "related_queries": [],
        "country": "US",
        "timeframe": "today 12-m",
        "observed_at": "2026-08-30T00:00:00Z",
        "source": "Google Trends",
        "source_type": "google_trends_related",
        "source_url": "https://trends.google.com/trends/explore",
        "raw_evidence_ref": "related.json",
        "screenshot_ref": "related.png",
        "evidence_receipt_ref": "related.receipt.json",
    }

    errors = validator.validate_stage("trends_related", payload, contracts)

    assert errors == []
