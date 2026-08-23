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


def observed(days_ago=0, **overrides):
    observed_at = (AS_OF - timedelta(days=days_ago)).isoformat()
    row = {
        "keyword": "audit query",
        "observed_at": observed_at,
        "source": "google_trends",
        "source_type": "trend_index",
        "source_url": "https://example.com/google-trends",
        "root_id": "audit-root",
        "signal_value": 20,
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


def test_cross_market_metric_provenance_is_not_a_complete_compatible_set(tmp_path):
    rows = [
        observed(
            3,
            source="semrush",
            source_type="keyword_metrics",
            source_url="https://example.com/semrush-us",
            metric_source="semrush",
            metric_database="US",
            country="US",
            volume=1200,
        ),
        observed(
            2,
            source="semrush",
            source_type="keyword_metrics",
            source_url="https://example.com/semrush-uk",
            metric_source="semrush",
            metric_database="UK",
            country="UK",
            kd=28,
        ),
        observed(
            1,
            source="google_ads",
            source_type="keyword_metrics",
            source_url="https://example.com/google-ads-us",
            metric_source="google_ads",
            metric_database="US",
            country="US",
            cpc=1.25,
        ),
    ]
    candidate = aggregate(tmp_path, rows)

    assert candidate["volume"] == 1200
    assert candidate["kd"] == 28
    assert candidate["cpc"] == 1.25
    assert candidate["metric_status"] != "complete"
    assert candidate["metric_compatibility_status"] == "mixed_context"

    provenance = candidate["metric_provenance"]
    assert provenance["volume"] == {
        "value": 1200.0,
        "source": "semrush",
        "metric_source": "semrush",
        "metric_database": "US",
        "country": "US",
        "observed_at": "2026-08-20",
    }
    assert provenance["kd"]["country"] == "UK"
    assert provenance["cpc"]["country"] == "US"


def test_incompatible_kgr_inputs_remain_unknown(tmp_path):
    rows = [
        observed(
            2,
            source="semrush",
            source_url="https://example.com/semrush-us",
            metric_source="semrush",
            metric_database="US",
            country="US",
            volume=1000,
        ),
        observed(
            1,
            source="google_search",
            source_url="https://example.com/google-uk",
            metric_source="google_search",
            metric_database="UK",
            country="UK",
            intitle_results=100,
        ),
    ]
    candidate = aggregate(tmp_path, rows)
    classified = classify(tmp_path, candidate)

    assert candidate["metric_compatibility_status"] == "mixed_context"
    assert classified["kgr"] is None

    compatible = dict(candidate)
    compatible["volume"] = 1000
    compatible["intitle_results"] = 100
    compatible["metric_provenance"] = {
        "volume": {
            "value": 1000,
            "source": "semrush",
            "metric_source": "semrush",
            "metric_database": "US",
            "country": "US",
            "observed_at": "2026-08-22",
        },
        "kd": None,
        "cpc": None,
        "intitle_results": {
            "value": 100,
            "source": "google_search",
            "metric_source": "google_search",
            "metric_database": "US",
            "country": "US",
            "observed_at": "2026-08-22",
        },
    }
    compatible["metric_compatibility_status"] = "compatible"
    assert classify(tmp_path, compatible)["kgr"] == 0.1


def test_recent_30d_fallback_uses_non_overlapping_baseline(tmp_path):
    rows = [
        observed(60, signal_value=10),
        observed(40, signal_value=10),
        observed(20, signal_value=20),
        observed(10, signal_value=30),
        observed(2, signal_value=40),
    ]
    classified = classify(tmp_path, aggregate(tmp_path, rows))

    assert classified["persistence_window"] == "recent_30d"
    assert classified["baseline_signal"] == 10
    assert classified["recent_signal"] == 30
    assert classified["growth_rate"] == 2.0


def test_stale_observations_cannot_confirm_emerging(tmp_path):
    rows = [
        observed(50, signal_value=0),
        observed(40, signal_value=0),
        observed(20, signal_value=10),
        observed(15, signal_value=20),
        observed(10, signal_value=30),
    ]
    candidate = aggregate(tmp_path, rows)
    primary = candidate["primary_series"]

    assert primary["latest_observation_age_days"] == 10
    assert primary["distinct_observation_days"] == 5
    assert "coverage_ratio" in primary
    assert "max_observation_gap_days" in primary

    classified = classify(tmp_path, candidate)
    assert classified["status"] == "watch"
    assert classified["signal_type"] is None
    assert classified["freshness_status"] == "stale"


def test_reactivated_old_query_is_not_net_new(tmp_path):
    rows = [
        observed(170, signal_value=40),
        observed(160, signal_value=35),
        observed(60, signal_value=0),
        observed(40, signal_value=0),
        observed(5, signal_value=20),
        observed(3, signal_value=30),
        observed(1, signal_value=40),
    ]
    candidate = aggregate(tmp_path, rows)
    primary = candidate["primary_series"]
    classified = classify(tmp_path, candidate)

    assert primary["historical_positive_seen"] is True
    assert primary["historical_positive_observations"] >= 2
    assert primary["historical_positive_windows"]
    assert classified["signal_type"] != "net_new"
    assert classified["status"] in {"watch", "breakout"}


def test_incremental_replay_preserves_first_observed_at(tmp_path):
    day1 = aggregate(
        tmp_path,
        [observed(22, signal_value=10, first_observed_at="2026-08-01")],
    )
    assert day1["first_observed_at"] == "2026-08-01"

    day2 = aggregate(
        tmp_path,
        [
            observed(
                0,
                signal_value=30,
                first_observed_at=day1["first_observed_at"],
            )
        ],
    )
    assert day2["first_observed_at"] == "2026-08-01"
    assert day2["age_days"] == 22


def test_lasted_source_does_not_veto_fresh_breakout_source(tmp_path):
    source_a = {
        "source": "google_trends",
        "provenance_status": "verified",
        "observation_count": 5,
        "baseline_observations": 2,
        "baseline_90d_7d": 0,
        "baseline_90d_30d": 0,
        "baseline_7d_observations": 2,
        "baseline_30d_observations": 2,
        "recent_7d": 25,
        "recent_30d": 25,
        "recent_observations": 3,
        "recent_7d_observations": 3,
        "recent_30d_observations": 3,
        "persistence": 1.0,
        "persistence_7d": 1.0,
        "persistence_30d": 1.0,
        "peak_signal": 25,
        "latest_signal": 25,
        "trend_status": "lasted",
        "latest_observation_age_days": 0,
        "historical_positive_seen": False,
        "historical_positive_observations": 0,
        "historical_positive_windows": [],
        "novelty_baseline_7d": 0,
        "novelty_baseline_7d_observations": 2,
        "novelty_baseline_30d": 0,
        "novelty_baseline_30d_observations": 2,
    }
    source_b = {
        "source": "semrush",
        "provenance_status": "verified",
        "observation_count": 4,
        "baseline_observations": 3,
        "baseline_90d_7d": 10,
        "baseline_90d_30d": 10,
        "baseline_7d_observations": 3,
        "baseline_30d_observations": 3,
        "recent_7d": 30,
        "recent_30d": 30,
        "recent_observations": 3,
        "recent_7d_observations": 3,
        "recent_30d_observations": 3,
        "growth_rate_7d": 2.0,
        "growth_status_7d": "calculated",
        "growth_rate_30d": 2.0,
        "growth_status_30d": "calculated",
        "persistence": 1.0,
        "persistence_7d": 1.0,
        "persistence_30d": 1.0,
        "peak_signal": 30,
        "latest_signal": 30,
        "trend_status": "active",
        "latest_observation_age_days": 0,
        "historical_positive_seen": True,
        "historical_positive_observations": 3,
        "historical_positive_windows": ["days_7_89"],
        "novelty_baseline_7d": 10,
        "novelty_baseline_7d_observations": 3,
        "novelty_baseline_30d": 10,
        "novelty_baseline_30d_observations": 3,
    }
    candidate = {
        "keyword": "cross source conflict",
        "root_id": "audit-root",
        "first_observed_at": "2026-04-01",
        "age_days": 144,
        "baseline_signal": 0,
        "recent_signal": 25,
        "growth_rate": None,
        "growth_status": "from_observed_zero_baseline",
        "persistence": 1.0,
        "persistence_observations": 3,
        "source_count": 2,
        "source_evidence": [source_a, source_b],
        "primary_series": source_a,
        "trend_status": "lasted",
        "volume": None,
        "kd": None,
        "cpc": None,
        "intitle_results": None,
    }

    classified = classify(tmp_path, candidate)
    assert classified["status"] == "breakout"
    assert classified["signal_type"] == "breakout"
    assert classified["classification_primary_series"]["source"] == "semrush"


def test_watch_root_candidate_stays_on_watchlist(tmp_path):
    routed = route(
        tmp_path,
        {
            "keyword": "premature root",
            "status": "watch",
            "signal_type": None,
            "root_id": None,
            "root_relation": "root_candidate",
            "root_candidate_hypothesis": "possible stable demand family",
            "source_evidence": [],
        },
    )
    assert routed["route"] == "new_root_watchlist"
    assert routed["mutates_root_library"] is False


def test_selection_handoff_preserves_metric_provenance(tmp_path):
    provenance = {
        "volume": {
            "value": 1000,
            "source": "semrush",
            "metric_source": "semrush",
            "metric_database": "US",
            "country": "US",
            "observed_at": "2026-08-22",
        },
        "kd": None,
        "cpc": None,
        "intitle_results": None,
    }
    routed = route(
        tmp_path,
        {
            "keyword": "handoff provenance",
            "root_id": "audit-root",
            "root_relation": "existing_root",
            "status": "emerging",
            "signal_type": "net_new",
            "metric_status": "incomplete",
            "metric_compatibility_status": "compatible",
            "metric_provenance": provenance,
            "volume": 1000,
            "kd": None,
            "cpc": None,
            "intitle_results": None,
        },
    )
    assert routed["route"] == "selection_handoff"
    assert routed["handoff"]["metric_provenance"] == provenance
    assert routed["handoff"]["metric_compatibility_status"] == "compatible"
