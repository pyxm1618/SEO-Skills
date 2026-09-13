import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import pytest

ROOT = Path(__file__).resolve().parents[1]
TRENDS = ROOT / "runtime" / "collectors" / "google_trends_collector.py"
BINDING = ROOT / "runtime" / "evidence_binding.py"
PIPELINE = ROOT / "runtime" / "emerging_pipeline.py"
HOOK = ROOT / "runtime" / "stage_hook.py"
RUNNER = ROOT / "skills" / "emerging-keyword-monitor" / "scripts" / "run_emerging_radar.py"
EXPORTER = ROOT / "skills" / "emerging-keyword-monitor" / "scripts" / "export_to_sheet.py"


def load_module(name, path):
    scripts_dir = str(path.parent)
    inserted = scripts_dir not in sys.path
    if inserted:
        sys.path.insert(0, scripts_dir)
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        if inserted:
            sys.path.remove(scripts_dir)


def _trends_url(path, request):
    encoded = quote(json.dumps(request, separators=(",", ":")))
    return f"https://trends.google.com{path}?req={encoded}"


def _real_timeline_url(keyword="perfume for men", market="US"):
    request = {
        "time": "2025-09-12 2026-09-12",
        "resolution": "WEEK",
        "locale": "en",
        "comparisonItem": [
            {
                "geo": {"country": market},
                "complexKeywordsRestriction": {
                    "keyword": [{"type": "BROAD", "value": keyword}]
                },
            }
        ],
        "requestOptions": {"property": "", "backend": "IZG", "category": 0},
    }
    return _trends_url("/trends/api/widgetdata/multiline", request)


def _real_related_url(keyword="perfume for men", market="US"):
    request = {
        "restriction": {
            "geo": {"country": market},
            "time": "2025-09-12 2026-09-12",
            "originalTimeRangeForExploreUrl": "today 12-m",
            "complexKeywordsRestriction": {
                "keyword": [{"type": "BROAD", "value": keyword}]
            },
        },
        "keywordType": "QUERY",
        "metric": ["TOP", "RISING"],
        "trendinessSettings": {"compareTime": "2024-09-12 2025-09-12"},
        "requestOptions": {"property": "", "backend": "IZG", "category": 0},
    }
    return _trends_url("/trends/api/widgetdata/relatedsearches", request)


def _rising(*queries):
    return {
        "related_queries": [
            {
                "query": query,
                "relation_type": "rising",
                "rank": index + 1,
                "rising_value": 100 + index,
                "is_google_breakout": False,
                "source_url": "https://trends.google.com/related",
                "raw_evidence_ref": "related.json",
            }
            for index, query in enumerate(queries)
        ]
    }


def _timeline_payload(keyword, timeframe="today 12-m"):
    return {
        "keyword": keyword,
        "market": "US",
        "requested_timeframe": timeframe,
        "actual_resolution": "weekly",
        "observed_at": "2026-09-12T00:00:00Z",
        "source_url": "https://trends.google.com/trends/api/widgetdata/multiline",
        "raw_evidence_ref": f"{keyword}.json",
        "screenshot_ref": f"{keyword}.png",
        "verification_status": "verified",
        "delivery_eligible": True,
        "series": [
            {"time": "1788739200", "value": 10},
            {"time": "1789344000", "value": 20},
        ],
    }


def test_r1_real_google_timeline_request_structure_matches_without_weakening_binding():
    trends = load_module("pr39_r1_timeline", TRENDS)
    good = _real_timeline_url()

    assert trends.trends_response_matches_request(good, "perfume for men", "US", "today 12-m") is True
    assert trends.trends_response_matches_request(good, "perfume for women", "US", "today 12-m") is False
    assert trends.trends_response_matches_request(good, "perfume for men", "GB", "today 12-m") is False
    assert trends.trends_response_matches_request(good, "perfume for men", "US", "today 3-m") is False


def test_r1_real_google_related_request_prefers_request_window_semantics():
    trends = load_module("pr39_r1_related", TRENDS)
    good = _real_related_url()

    assert trends.trends_response_matches_request(
        good, "perfume for men", "US", "today 12-m", endpoint="related"
    ) is True
    assert trends.trends_response_matches_request(
        good, "perfume for men", "US", "today 3-m", endpoint="related"
    ) is False


def test_r2_trends_evidence_binding_registers_new_collector_as_issuer():
    binding = load_module("pr39_r2_binding", BINDING)

    for evidence_type in ("google_trends", "google_trends_related"):
        assert binding.EXPECTED_COLLECTORS[evidence_type] == "google_trends_collector"
        assert binding.COLLECTOR_FILES[evidence_type].name == "google_trends_collector.py"


def test_r3_max_total_candidates_is_a_hard_request_cap():
    runner = load_module("pr39_r3_runner", RUNNER)
    calls = []

    def timeline(keyword, timeframe):
        calls.append((keyword, timeframe))
        return _timeline_payload(keyword, timeframe)

    result = runner.run_pipeline(
        lambda _anchor: _rising("perfume samples", "perfume for women", "perfume gift set"),
        domain="perfume",
        relation_gate=lambda *_: ("in_scope", "fixture in scope"),
        max_depth=1,
        max_total_candidates=1,
        timeline_fetcher=timeline,
        timeframe_specs=(("12m", "today 12-m"),),
        max_collection_retries=0,
    )

    assert len(calls) == 1
    overflow = [row for row in result["candidate_ledger"] if row.get("acquisition_reason") == "batch_candidate_limit"]
    assert len(overflow) == 2
    assert all(row["delivery_eligible"] is False for row in overflow)


def test_r4_carry_forward_preserves_parent_anchor_and_never_self_proves_relevance():
    runner = load_module("pr39_r4_runner", RUNNER)
    relation_calls = []
    timeline_calls = []

    def relation_gate(_domain, keyword, parent):
        relation_calls.append((keyword, parent))
        if keyword == parent:
            return "in_scope", "self-parent must never be sufficient"
        return "unknown", "historical parent remains unrelated"

    database = {
        "schema_version": 1,
        "records": [
            {
                "domain": "perfume",
                "keyword": "ai news today",
                "status": "watch",
                "observation_state": "watching",
                "domain_relation": "unknown",
                "domain_relation_reason": "parent anchor is unrelated",
                "parent_anchor": "perfume finder",
                "last_seen_at": "2026-09-01T00:00:00Z",
            }
        ],
    }

    result = runner.run_pipeline(
        lambda _anchor: {"related_queries": []},
        domain="perfume",
        relation_gate=relation_gate,
        max_depth=1,
        existing_database=database,
        timeline_fetcher=lambda keyword, timeframe: timeline_calls.append((keyword, timeframe)) or _timeline_payload(keyword, timeframe),
        timeframe_specs=(("12m", "today 12-m"),),
        max_collection_retries=0,
    )

    row = next(item for item in result["candidate_ledger"] if item["keyword"] == "ai news today")
    assert ("ai news today", "perfume finder") in relation_calls
    assert row["parent_anchor"] == "perfume finder"
    assert row["domain_relation"] == "unknown"
    assert timeline_calls == []


def test_r5_legacy_database_without_run_state_or_eligibility_is_production_blocked():
    exporter = load_module("pr39_r5_exporter", EXPORTER)
    legacy = {
        "schema_version": 1,
        "records": [{"domain": "perfume", "keyword": "legacy keyword", "status": "watch"}],
    }

    with pytest.raises(RuntimeError, match="status|eligib|legacy|production"):
        exporter.select_delivery_records(legacy)

    inspection = exporter.select_delivery_records(legacy, allow_blocked_dry_run=True)
    assert inspection["legacy_delivery_fallback"] is True
    assert inspection["run_status"] != "PASS"


def _observation(candidate_id="cand-1", keyword="perfume for men", day=10, value=20):
    return {
        "candidate_id": candidate_id,
        "domain": "perfume",
        "keyword": keyword,
        "domain_relation": "in_scope",
        "observed_at": f"2026-09-{day:02d}T00:00:00+00:00",
        "source": "google_trends",
        "source_type": "interest_over_time",
        "source_url": f"https://trends.google.com/trends/explore?q={keyword.replace(' ', '+')}",
        "signal_value": value,
        "signal_unit": "normalized_interest_index",
        "country": "US",
        "time_window": "90d",
        "metric_source": "google_trends",
        "metric_database": "US",
        "root_id": "root-perfume",
        "root_relation": "existing_root",
    }


def test_r6_canonical_pipeline_consumes_ledger_eligibility_and_explicit_empty_delivery(tmp_path):
    pipeline = load_module("pr39_r6_pipeline", PIPELINE)
    input_path = tmp_path / "observations.json"
    input_path.write_text(
        json.dumps([_observation(day=10), _observation(day=11, value=30), _observation(day=12, value=40)]),
        encoding="utf-8",
    )
    ledger_path = tmp_path / "ledger.json"
    ledger_path.write_text(
        json.dumps(
            [
                {
                    "candidate_id": "cand-1",
                    "domain": "perfume",
                    "keyword": "perfume for men",
                    "domain_relation": "in_scope",
                    "acquisition_status": "failed",
                    "verification_status": "pending_evidence",
                    "delivery_eligible": False,
                    "final_disposition": "pending_evidence",
                }
            ]
        ),
        encoding="utf-8",
    )

    receipt = pipeline.run_pipeline(
        input_path,
        tmp_path / "canonical",
        "2026-09-12",
        candidate_ledger_path=ledger_path,
    )
    classified = json.loads((tmp_path / "canonical" / "classified.json").read_text(encoding="utf-8"))

    assert classified["candidates"] == []
    assert receipt["reconciliation"]["classified_ids"] == []
    assert receipt["reconciliation"]["delivery_ids"] == []
    assert receipt["reconciliation"]["delivery_count"] == 0

    reconciliation = pipeline.reconcile_identity_sets(
        [{"candidate_id": "cand-1", "final_disposition": "monitor_record"}],
        [{"candidate_id": "cand-1"}],
        [{"candidate_id": "cand-1"}],
        [],
    )
    assert reconciliation["delivery_ids"] == []


def test_r6_hook_rejects_candidate_ledger_tampering_after_receipt(tmp_path):
    pipeline = load_module("pr39_r6_pipeline_tamper", PIPELINE)
    hook = load_module("pr39_r6_hook", HOOK)
    input_path = tmp_path / "observations.json"
    input_path.write_text("[]", encoding="utf-8")
    ledger_path = tmp_path / "ledger.json"
    ledger_path.write_text(
        json.dumps(
            [
                {
                    "candidate_id": "cand-x",
                    "keyword": "unrelated clue",
                    "domain_relation": "out_of_scope",
                    "acquisition_status": "not_applicable",
                    "verification_status": "not_run",
                    "delivery_eligible": False,
                    "final_disposition": "excluded_out_of_scope",
                }
            ]
        ),
        encoding="utf-8",
    )
    receipt_path = tmp_path / "canonical" / "receipt.json"
    receipt = pipeline.run_pipeline(
        input_path,
        tmp_path / "canonical",
        "2026-09-12",
        candidate_ledger_path=ledger_path,
    )
    ledger_path.write_text("[]", encoding="utf-8")

    valid, reason = hook._verify_route_attestation(
        {
            "route": "emerging",
            "emerging_pipeline_receipt_ref": str(receipt_path),
            "route_handoff_ref": receipt["route_handoff_ref"],
            "candidates": {},
        }
    )
    assert valid is False
    assert "ledger" in reason.lower() or "reconciliation" in reason.lower() or "hash" in reason.lower()


def test_r7_valid_no_data_with_failed_required_screenshot_blocks_run():
    runner = load_module("pr39_r7_runner", RUNNER)

    def no_data_pending(_keyword, _timeframe):
        return {
            "acquisition_status": "valid_no_data",
            "verification_status": "pending_evidence",
            "screenshot_status": "failed",
            "failure_type": "screenshot_timeout",
            "raw_evidence_ref": "raw.json",
            "delivery_eligible": False,
            "series": [],
        }

    result = runner.run_pipeline(
        lambda _anchor: _rising("perfume samples"),
        domain="perfume",
        relation_gate=lambda *_: ("in_scope", "fixture in scope"),
        max_depth=1,
        timeline_fetcher=no_data_pending,
        timeframe_specs=(("12m", "today 12-m"),),
        max_collection_retries=0,
    )

    row = next(item for item in result["candidate_ledger"] if item["keyword"] == "perfume samples")
    assert result["status"] == "BLOCKED"
    assert row["acquisition_status"] == "failed"
    assert row["verification_status"] == "pending_evidence"
    assert any(blocker.get("failure_type") == "screenshot_timeout" for blocker in result["blockers"])


def test_r8_future_review_date_and_paused_state_gate_all_collection_sources():
    runner = load_module("pr39_r8_runner", RUNNER)
    calls = []
    database = {
        "schema_version": 1,
        "records": [
            {
                "domain": "perfume",
                "keyword": "perfume samples",
                "status": "watch",
                "observation_state": "watching",
                "monitoring_state": "retry_scheduled",
                "next_review_at": "2027-01-01T00:00:00+00:00",
                "parent_anchor": "perfume",
                "domain_relation": "in_scope",
                "domain_relation_reason": "historically reviewed in scope",
            },
            {
                "domain": "perfume",
                "keyword": "perfume gift set",
                "status": "watch",
                "observation_state": "watching",
                "monitoring_state": "paused_review",
                "next_review_at": None,
                "parent_anchor": "perfume",
                "domain_relation": "in_scope",
                "domain_relation_reason": "historically reviewed in scope",
            },
        ],
    }

    result = runner.run_pipeline(
        lambda _anchor: _rising("perfume samples", "perfume gift set"),
        domain="perfume",
        relation_gate=lambda *_: ("in_scope", "new discovery does not override monitoring workflow"),
        max_depth=1,
        existing_database=database,
        as_of=datetime(2026, 9, 12, 23, 59, tzinfo=timezone.utc),
        timeline_fetcher=lambda keyword, timeframe: calls.append((keyword, timeframe)) or _timeline_payload(keyword, timeframe),
        timeframe_specs=(("12m", "today 12-m"),),
        max_collection_retries=0,
    )

    assert calls == []
    rows = {row["keyword"]: row for row in result["candidate_ledger"]}
    assert rows["perfume samples"]["acquisition_status"] == "not_attempted"
    assert rows["perfume samples"]["acquisition_reason"] == "review_not_due"
    assert rows["perfume gift set"]["acquisition_status"] == "not_attempted"
    assert rows["perfume gift set"]["acquisition_reason"] == "paused_review"
