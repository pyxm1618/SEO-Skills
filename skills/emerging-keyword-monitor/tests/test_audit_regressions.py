import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
AGGREGATE = BASE / "scripts" / "aggregate_signals.py"
CLASSIFY = BASE / "scripts" / "classify_emergence.py"
ROUTE = BASE / "scripts" / "route_candidates.py"
AS_OF = date(2026, 8, 23)


def run(script, tmp_path, payload, *args):
    path = tmp_path / f"{script.stem}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(script), "--input", str(path), "--format", "json", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def observed(days_ago, value, **overrides):
    row = {
        "keyword": "audit query",
        "observed_at": (AS_OF - timedelta(days=days_ago)).isoformat(),
        "source": "google_trends",
        "source_type": "trend_index",
        "source_url": "https://example.com/google-trends",
        "root_id": "audit-root",
        "signal_value": value,
        "signal_unit": "index_0_100",
        "country": "US",
        "time_window": "daily",
        "metric_source": "google_trends",
        "metric_database": "US",
    }
    row.update(overrides)
    return row


def aggregate(tmp_path, rows):
    return run(AGGREGATE, tmp_path, rows, "--as-of", AS_OF.isoformat())["candidates"][0]


def classify(tmp_path, candidate):
    return run(CLASSIFY, tmp_path, {"candidates": [candidate]}, "--as-of", AS_OF.isoformat())["candidates"][0]


def route(tmp_path, candidate):
    return run(ROUTE, tmp_path, {"candidates": [candidate]})["routes"][0]


def test_cross_market_metric_provenance_is_not_complete_compatible_set(tmp_path):
    rows = [
        observed(3, 10, source="semrush", source_url="https://example.com/semrush-us", metric_source="semrush", metric_database="US", country="US", volume=1200),
        observed(2, 20, source="semrush", source_url="https://example.com/semrush-uk", metric_source="semrush", metric_database="UK", country="UK", kd=31),
        observed(1, 30, source="google_ads", source_url="https://example.com/google-ads-us", metric_source="google_ads", metric_database="US", country="US", cpc=1.25),
    ]
    candidate = aggregate(tmp_path, rows)
    assert candidate["metric_provenance"]["volume"]["country"] == "US"
    assert candidate["metric_provenance"]["kd"]["country"] == "UK"
    assert candidate["metric_provenance"]["cpc"]["metric_source"] == "google_ads"
    assert candidate["metric_compatibility_status"] == "incompatible"
    assert candidate["metric_status"] != "complete"


def test_incompatible_kgr_markets_remain_unknown(tmp_path):
    rows = [
        observed(2, 10, source="semrush", source_url="https://example.com/semrush-us", metric_source="semrush", metric_database="US", country="US", volume=1000),
        observed(1, 20, source="google_search", source_url="https://example.com/google-uk", metric_source="google_search", metric_database="UK", country="UK", intitle_results=100),
    ]
    result = classify(tmp_path, aggregate(tmp_path, rows))
    assert result["kgr"] is None
    assert result["metric_provenance"]["volume"]["country"] == "US"
    assert result["metric_provenance"]["intitle_results"]["country"] == "UK"


def test_bare_kgr_values_without_provenance_stay_unknown(tmp_path):
    candidate = {
        "keyword": "bare metric candidate",
        "root_id": "root",
        "first_observed_at": "2026-08-01",
        "age_days": 22,
        "baseline_signal": 10,
        "recent_signal": 30,
        "growth_rate": 2,
        "persistence": 1,
        "persistence_observations": 3,
        "source_count": 1,
        "source_evidence": [{"source": "semrush", "provenance_status": "verified"}],
        "primary_series": {
            "source": "semrush",
            "provenance_status": "verified",
            "baseline_observations": 3,
            "recent_observations": 3,
            "observation_count": 6,
            "peak_signal": 30,
            "latest_signal": 30,
            "latest_observation_age_days": 1,
        },
        "volume": 1000,
        "kd": 20,
        "cpc": 0.3,
        "intitle_results": 100,
    }
    result = classify(tmp_path, candidate)
    assert result["kgr"] is None


def test_recent_30d_fallback_uses_non_overlapping_growth_baseline(tmp_path):
    rows = [
        observed(50, 10),
        observed(40, 10),
        observed(25, 100),
        observed(20, 100),
        observed(15, 100),
        observed(10, 100),
        observed(2, 100),
    ]
    result = classify(tmp_path, aggregate(tmp_path, rows))
    assert result["persistence_window"] == "recent_30d"
    assert result["recent_signal"] == 100
    assert result["baseline_signal"] == 10
    assert result["growth_rate"] == 9


def test_stale_recent_observations_cannot_confirm_emerging(tmp_path):
    rows = [
        observed(60, 0),
        observed(45, 0),
        observed(20, 40),
        observed(15, 50),
        observed(10, 60),
    ]
    candidate = aggregate(tmp_path, rows)
    assert candidate["latest_observation_age_days"] == 10
    assert candidate["distinct_observation_days"] >= 5
    assert "coverage_ratio" in candidate
    assert "max_observation_gap_days" in candidate
    result = classify(tmp_path, candidate)
    assert result["status"] == "watch"
    assert result["signal_type"] is None


def test_earlier_12m_positive_demand_blocks_net_new(tmp_path):
    rows = [
        observed(220, 40),
        observed(180, 30),
        observed(60, 0),
        observed(45, 0),
        observed(20, 20),
        observed(15, 30),
        observed(10, 40),
    ]
    result = classify(tmp_path, aggregate(tmp_path, rows))
    assert result["historical_positive_seen"] is True
    assert result["historical_positive_observations"] >= 2
    assert result["signal_type"] != "net_new"


def test_incremental_input_preserves_supplied_first_observed_at(tmp_path):
    row = observed(0, 20, first_observed_at="2026-08-01")
    candidate = aggregate(tmp_path, [row])
    assert candidate["first_observed_at"] == "2026-08-01"
    assert candidate["age_days"] == 22


def test_lasted_source_does_not_veto_fresh_active_breakout_source(tmp_path):
    rows = [
        observed(50, 10, source="semrush", source_url="https://example.com/semrush", metric_source="semrush", metric_database="US"),
        observed(40, 10, source="semrush", source_url="https://example.com/semrush", metric_source="semrush", metric_database="US"),
        observed(3, 50, source="semrush", source_url="https://example.com/semrush", metric_source="semrush", metric_database="US", trend_status="active"),
        observed(2, 60, source="semrush", source_url="https://example.com/semrush", metric_source="semrush", metric_database="US", trend_status="active"),
        observed(1, 70, source="semrush", source_url="https://example.com/semrush", metric_source="semrush", metric_database="US", trend_status="active"),
        observed(0, 0, source="google_trends", source_url="https://example.com/google-trends", metric_source="google_trends", metric_database="US", trend_status="lasted"),
    ]
    result = classify(tmp_path, aggregate(tmp_path, rows))
    assert result["status"] == "breakout"
    assert result["signal_type"] == "breakout"


def test_watch_root_candidate_with_hypothesis_stays_on_watchlist(tmp_path):
    result = route(
        tmp_path,
        {
            "keyword": "candidate family phrase",
            "status": "watch",
            "signal_type": None,
            "root_id": None,
            "root_relation": "root_candidate",
            "root_candidate_hypothesis": "possible stable demand family",
            "source_evidence": [],
            "first_observed_at": "2026-08-01",
        },
    )
    assert result["route"] == "new_root_watchlist"
    assert result["mutates_root_library"] is False


def test_selection_handoff_includes_metric_provenance(tmp_path):
    provenance = {
        "volume": {"value": 1000, "source": "semrush", "metric_source": "semrush", "metric_database": "US", "country": "US", "observed_at": "2026-08-22"}
    }
    result = route(
        tmp_path,
        {
            "keyword": "handoff metric phrase",
            "root_id": "known-root",
            "root_relation": "existing_root",
            "status": "emerging",
            "signal_type": "net_new",
            "metric_status": "incomplete",
            "metric_compatibility_status": "incomplete",
            "metric_provenance": provenance,
            "volume": 1000,
        },
    )
    assert result["route"] == "selection_handoff"
    assert result["handoff"]["metric_provenance"] == provenance
    assert result["handoff"]["metric_compatibility_status"] == "incomplete"
