import importlib.util
import json
import sys
from pathlib import Path
from urllib.parse import quote

import pytest

ROOT = Path(__file__).resolve().parents[3]
SKILL_ROOT = ROOT / "skills" / "emerging-keyword-monitor"
RUNNER = SKILL_ROOT / "scripts" / "run_emerging_radar.py"
RADAR = SKILL_ROOT / "scripts" / "radar_discovery.py"
DATABASE = SKILL_ROOT / "scripts" / "update_emerging_database.py"
EXPORTER = SKILL_ROOT / "scripts" / "export_to_sheet.py"
GOOGLE = ROOT / "runtime" / "collectors" / "google_live_collector.py"


def load_module(name, path):
    scripts_dir = str(path.parent)
    inserted = scripts_dir not in sys.path
    if inserted:
        sys.path.insert(0, scripts_dir)
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if inserted:
            sys.path.remove(scripts_dir)


def timeline_payload(keyword="perfume", market="US", timeframe="today 12-m"):
    return {
        "keyword": keyword,
        "market": market,
        "requested_timeframe": timeframe,
        "actual_resolution": "weekly",
        "observed_at": "2026-09-12T00:00:00Z",
        "source_url": "https://trends.google.com/trends/api/widgetdata/multiline",
        "raw_evidence_ref": f"{keyword}-{timeframe}.json",
        "screenshot_ref": f"{keyword}-{timeframe}.png",
        "series": [
            {"time": "1788739200", "value": 10},
            {"time": "1789344000", "value": 20},
        ],
    }


def rising(*queries):
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


class TimelineResponse:
    status = 200

    def __init__(self, keyword="perfume", market="US", timeframe="today 12-m"):
        request = {
            "comparisonItem": [{"keyword": keyword, "geo": market, "time": timeframe}],
            "category": 0,
            "property": "",
        }
        self.url = (
            "https://trends.google.com/trends/api/widgetdata/multiline?req="
            + quote(json.dumps(request, separators=(",", ":")))
        )

    def text(self):
        payload = {
            "default": {
                "timelineData": [
                    {"time": "1788739200", "formattedTime": "Sep 7, 2026", "value": [10]},
                    {"time": "1789344000", "formattedTime": "Sep 14, 2026", "value": [20]},
                ]
            }
        }
        return ")]}'\n" + json.dumps(payload)


class TimelineBody:
    def inner_text(self, timeout=5000):
        return "Interest over time"


class ScreenshotTimeoutPage:
    def __init__(self):
        self.url = "https://trends.google.com/trends/explore"
        self.listeners = []
        self.screenshot_calls = 0

    def on(self, event, callback):
        assert event == "response"
        self.listeners.append(callback)

    def remove_listener(self, event, callback):
        if callback in self.listeners:
            self.listeners.remove(callback)

    def goto(self, url, wait_until=None):
        self.url = url
        for callback in list(self.listeners):
            callback(TimelineResponse())

    def wait_for_timeout(self, milliseconds):
        return None

    def locator(self, selector):
        assert selector == "body"
        return TimelineBody()

    def screenshot(self, **kwargs):
        self.screenshot_calls += 1
        raise TimeoutError("Timeout 30000ms exceeded while taking screenshot")


class ScreenshotTimeoutContext:
    def __init__(self):
        self.page = ScreenshotTimeoutPage()

    def new_page(self):
        return self.page


class NoWriteWorksheet:
    def __init__(self):
        self.calls = []

    def get_all_values(self):
        self.calls.append("get")
        return []

    def update(self, *args, **kwargs):
        self.calls.append("update")

    def append_rows(self, *args, **kwargs):
        self.calls.append("append")


# 1. Raw timeline evidence must survive screenshot failure without being promoted.
def test_timeline_data_is_preserved_when_required_screenshot_times_out(tmp_path):
    google = load_module("google_radar_repair_screenshot", GOOGLE)
    context = ScreenshotTimeoutContext()

    result = google.trends_timeline(context, "perfume", "US", "today 12-m", tmp_path)

    assert result["acquisition_status"] == "data_acquired"
    assert result["screenshot_status"] == "failed"
    assert result["verification_status"] == "pending_evidence"
    assert result["delivery_eligible"] is False
    assert result["failure_type"] == "screenshot_timeout"
    assert Path(result["raw_evidence_ref"]).is_file()
    assert result["series"]
    # Bounded recovery: one initial attempt plus at most one retry.
    assert context.page.screenshot_calls == 2


# Response capture must be bound to the current request, not just any widgetdata payload.
def test_trends_response_binding_rejects_other_keyword_market_or_timeframe():
    google = load_module("google_radar_repair_binding", GOOGLE)
    good = TimelineResponse("perfume", "US", "today 12-m").url
    wrong_keyword = TimelineResponse("people finder", "US", "today 12-m").url
    wrong_market = TimelineResponse("perfume", "GB", "today 12-m").url
    wrong_timeframe = TimelineResponse("perfume", "US", "today 3-m").url

    assert google.trends_response_matches_request(good, "perfume", "US", "today 12-m") is True
    assert google.trends_response_matches_request(wrong_keyword, "perfume", "US", "today 12-m") is False
    assert google.trends_response_matches_request(wrong_market, "perfume", "US", "today 12-m") is False
    assert google.trends_response_matches_request(wrong_timeframe, "perfume", "US", "today 12-m") is False


# 2. A systemic failure must trip a bounded circuit breaker and ledger the skipped work.
def test_consecutive_systemic_timeline_failures_stop_the_batch_and_ledger_unattempted_items():
    runner = load_module("runner_radar_repair_breaker", RUNNER)
    calls = []

    def fail_timeline(keyword, timeframe):
        calls.append((keyword, timeframe))
        raise RuntimeError("screenshot_timeout: screenshot evidence unavailable")

    result = runner.run_pipeline(
        lambda _anchor: rising("perfume samples", "perfume for women", "perfume gift set"),
        domain="perfume",
        relation_gate=lambda *_: ("in_scope", "fixture is perfume demand"),
        max_depth=1,
        timeline_fetcher=fail_timeline,
        timeframe_specs=(("12m", "today 12-m"),),
        max_consecutive_collection_failures=2,
        max_collection_retries=0,
    )

    assert len(calls) == 2
    ledger = {row["keyword"]: row for row in result["candidate_ledger"]}
    assert ledger["perfume samples"]["acquisition_status"] == "failed"
    assert ledger["perfume for women"]["acquisition_status"] == "failed"
    assert ledger["perfume gift set"]["acquisition_status"] == "not_attempted"
    assert ledger["perfume gift set"]["acquisition_reason"] == "collection_circuit_open"
    assert result["status"] == "BLOCKED"


# 3. Generic lexical overlap and media homonyms are not sufficient domain admission.
def test_finder_ambiguity_and_perfume_media_homonyms_do_not_enter_formal_pool():
    radar = load_module("radar_repair_semantics", RADAR)

    people = radar.default_domain_relation("fragrance", "people finder", "perfume finder")
    stud = radar.default_domain_relation("fragrance", "how to use a stud finder", "perfume finder")
    movie = radar.default_domain_relation("fragrance", "Perfume: The Story of a Murderer movie", "perfume")
    relevant = radar.default_domain_relation("fragrance", "perfume samples", "perfume finder")
    uncertain = radar.default_domain_relation("fragrance", "best jasmine scent finder", "perfume finder")

    assert people[0] != "in_scope"
    assert stud[0] != "in_scope"
    assert movie[0] == "out_of_scope"
    assert relevant[0] == "in_scope"
    assert uncertain[0] == "unknown"


# 4. Every candidate, including those with no observations, must reconcile by identity.
def test_candidate_ledger_and_reconciliation_cover_candidates_without_observations():
    runner = load_module("runner_radar_repair_reconcile", RUNNER)

    def timeline(keyword, timeframe):
        if keyword == "perfume samples":
            return timeline_payload(keyword, timeframe=timeframe)
        raise RuntimeError("payload_not_observed")

    result = runner.run_pipeline(
        lambda _anchor: rising("perfume samples", "perfume for women"),
        domain="perfume",
        relation_gate=lambda *_: ("in_scope", "fixture is in scope"),
        max_depth=1,
        timeline_fetcher=timeline,
        timeframe_specs=(("12m", "today 12-m"),),
        max_consecutive_collection_failures=5,
        max_collection_retries=0,
    )

    ledger_ids = {row["candidate_id"] for row in result["candidate_ledger"]}
    reconciliation = result["reconciliation"]
    assert set(reconciliation["candidate_ids"]) == ledger_ids
    assert set(reconciliation["classified_ids"]) <= ledger_ids
    assert set(reconciliation["route_ids"]) == set(reconciliation["classified_ids"])
    assert set(reconciliation["delivery_ids"]) <= set(reconciliation["route_ids"])
    assert reconciliation["candidate_count"] == reconciliation["terminal_state_count"]
    failed = next(row for row in result["candidate_ledger"] if row["keyword"] == "perfume for women")
    assert failed["acquisition_status"] == "failed"
    assert failed["final_disposition"] == "pending_evidence"


# 5. A failed current acquisition must not overwrite a prior confirmed mature state.
def test_historical_mature_is_preserved_when_current_acquisition_fails():
    database = load_module("database_radar_repair_history", DATABASE)
    existing = {
        "schema_version": 1,
        "records": [
            {
                "domain": "perfume",
                "keyword": "perfume",
                "status": "mature",
                "source_evidence": ["confirmed-old.json"],
                "last_seen_at": "2026-08-01T00:00:00Z",
                "observation_state": "retired",
            }
        ],
    }

    merged = database.merge_database(
        existing,
        [
            {
                "domain": "perfume",
                "keyword": "perfume",
                "acquisition_status": "failed",
                "acquisition_reason": "screenshot_timeout",
                "current_classification_status": "unknown",
                "delivery_eligible": False,
            }
        ],
        [],
        "2026-09-12T00:00:00Z",
    )

    record = merged["records"][0]
    assert record["status"] == "mature"
    assert record["last_confirmed_status"] == "mature"
    assert record["last_confirmed_source_evidence"] == ["confirmed-old.json"]
    assert record["last_run_acquisition_status"] == "failed"
    assert record["current_classification_status"] == "unknown"


# 6. BLOCKED runs are a hard zero-write gate for production Sheet mutation.
def test_blocked_run_export_performs_zero_sheet_reads_or_writes():
    exporter = load_module("exporter_radar_repair_blocked", EXPORTER)
    sheet = NoWriteWorksheet()
    payload = {
        "schema_version": 1,
        "market": "US",
        "language": "en",
        "records": [{"domain": "perfume", "keyword": "perfume samples", "delivery_eligible": True}],
    }

    with pytest.raises(RuntimeError, match="BLOCKED|blocked"):
        exporter.export(sheet, payload, run_context={"status": "BLOCKED"})

    assert sheet.calls == []


# 7. Delivery contains only eligible records; unknown review reasons remain auditable.
def test_delivery_filter_keeps_only_eligible_records_and_preserves_unknown_reason():
    exporter = load_module("exporter_radar_repair_filter", EXPORTER)
    payload = {
        "schema_version": 1,
        "market": "US",
        "language": "en",
        "records": [
            {
                "domain": "perfume",
                "keyword": "perfume samples",
                "delivery_eligible": True,
                "status": "emerging",
                "signal_type": "net_new",
            },
            {
                "domain": "perfume",
                "keyword": "jasmine scent finder",
                "delivery_eligible": False,
                "domain_relation": "unknown",
                "domain_relation_reason": "semantic relation requires review",
            },
            {
                "domain": "perfume",
                "keyword": "people finder",
                "delivery_eligible": False,
                "domain_relation": "out_of_scope",
                "domain_relation_reason": "generic finder intent is unrelated to fragrance",
            },
        ],
    }

    selection = exporter.select_delivery_records(payload, run_context={"status": "PASS"})

    assert [row["keyword"] for row in selection["delivery_records"]] == ["perfume samples"]
    review = {row["keyword"]: row for row in selection["review_records"]}
    assert review["jasmine scent finder"]["domain_relation"] == "unknown"
    assert review["jasmine scent finder"]["domain_relation_reason"] == "semantic relation requires review"
    assert review["people finder"]["domain_relation"] == "out_of_scope"
