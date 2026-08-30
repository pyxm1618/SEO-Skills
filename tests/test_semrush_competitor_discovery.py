import hashlib
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SEMRUSH = ROOT / "runtime" / "collectors" / "semrush_relay_collector.py"
BINDING = ROOT / "runtime" / "evidence_binding.py"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def response():
    return {
        "jsonrpc": "2.0",
        "result": {
            "keywords": [
                {"phrase": "wedding timeline", "volume": 900, "difficulty": 22},
                {"phrase": "wedding seating chart", "volume": 700, "difficulty": 30},
                {"phrase": "wedding planner template"},
            ]
        },
    }


def descriptor(**overrides):
    data = {
        "path": "/captured/current-path",
        "method": "POST",
        "body": {},
        "capture_observed_at": datetime.now(timezone.utc).isoformat(),
        "capture_evidence_ref": "evidence/current-network-capture.json",
        "mode": "competitor_organic",
        "metric_database": "us",
        "competitor_domain": "competitor.example",
    }
    data.update(overrides)
    return data


class FakePage:
    def __init__(self, payload):
        self.payload = payload

    def evaluate(self, _script, _args):
        return {"ok": True, "status": 200, "data": self.payload}


def test_competitor_relay_normalizes_observed_rows_without_estimating_missing_metrics():
    semrush = load_module("semrush_competitor_normalize", SEMRUSH)

    result = semrush.collect(FakePage(response()), descriptor())

    assert result["competitor_domain"] == "competitor.example"
    assert result["rows"] == [
        {"keyword": "wedding timeline", "volume": 900, "kd": 22},
        {"keyword": "wedding seating chart", "volume": 700, "kd": 30},
        {"keyword": "wedding planner template"},
    ]
    assert result["metric_source"] == "Semrush"
    assert result["metric_stage"] == "competitor_organic"
    assert result["metric_database"] == "us"
    assert result["relay_origin"] == "https://sem.3ue.com/"
    assert result["provenance_ref"] == "evidence/current-network-capture.json"


def test_competitor_descriptor_requires_domain_and_rejects_cross_origin(tmp_path):
    semrush = load_module("semrush_competitor_descriptor", SEMRUSH)
    capture = tmp_path / "capture.json"
    capture.write_text(json.dumps({"captured": True}), encoding="utf-8")

    missing_domain = descriptor(capture_evidence_ref=str(capture))
    missing_domain.pop("competitor_domain")
    path = tmp_path / "missing-domain.json"
    path.write_text(json.dumps(missing_domain), encoding="utf-8")
    with pytest.raises(RuntimeError, match="competitor_domain"):
        semrush.load_request(path)

    cross_origin = descriptor(capture_evidence_ref=str(capture), path="https://other.example/current-path")
    path = tmp_path / "cross-origin.json"
    path.write_text(json.dumps(cross_origin), encoding="utf-8")
    with pytest.raises(RuntimeError, match="sem.3ue.com"):
        semrush.load_request(path)


def test_competitor_schema_mismatch_fails_closed():
    semrush = load_module("semrush_competitor_schema", SEMRUSH)

    with pytest.raises(RuntimeError, match="schema"):
        semrush.normalize_competitor_organic(
            {"result": {"keywords": [{"volume": 10}]}},
            descriptor(),
            "2026-08-30T00:00:00+00:00",
        )


def test_competitor_raw_response_replays_through_existing_evidence_binding(tmp_path):
    semrush = load_module("semrush_competitor_replay_collector", SEMRUSH)
    binding = load_module("semrush_competitor_replay_binding", BINDING)
    capture = tmp_path / "capture.json"
    raw = tmp_path / "competitor.raw.json"
    capture.write_text(json.dumps({"captured": True}), encoding="utf-8")
    loaded = descriptor(capture_evidence_ref=str(capture))
    raw_payload = {
        "observed_at": "2026-08-30T00:00:00+00:00",
        "relay_origin": "https://sem.3ue.com/",
        "request_method": loaded["method"],
        "request_path": loaded["path"],
        "capture_observed_at": loaded["capture_observed_at"],
        "capture_evidence_ref": str(capture),
        "mode": "competitor_organic",
        "metric_database": "us",
        "competitor_domain": loaded["competitor_domain"],
        "response": response(),
    }
    raw.write_text(json.dumps(raw_payload), encoding="utf-8")
    normalized = semrush.normalize_competitor_organic(
        raw_payload["response"], loaded, raw_payload["observed_at"], str(raw)
    )

    binding._verify_semrush_semantics("semrush_competitor_organic", normalized, {
        "relay_raw_response": raw,
        "current_network_capture": capture,
    })


def test_competitor_evidence_type_has_same_hashable_artifact_policy():
    binding = load_module("semrush_competitor_artifact_policy", BINDING)
    assert binding.REQUIRED_ARTIFACT_ROLES["semrush_competitor_organic"] == {
        "relay_raw_response",
        "current_network_capture",
    }
    assert binding.EXPECTED_COLLECTORS["semrush_competitor_organic"] == "semrush_relay_collector"
