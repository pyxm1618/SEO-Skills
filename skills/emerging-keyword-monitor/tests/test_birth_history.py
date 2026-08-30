import importlib.util
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

SKILL_ROOT = Path(__file__).resolve().parents[1]
BIRTH = SKILL_ROOT / "scripts" / "birth_history.py"
AGGREGATE = SKILL_ROOT / "scripts" / "aggregate_signals.py"
CLASSIFY = SKILL_ROOT / "scripts" / "classify_emergence.py"


def load_module(name, path):
    scripts_dir = str(path.parent)
    sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.path.remove(scripts_dir)
    return module


@pytest.fixture
def thresholds():
    return {
        "birth": {
            "min_history_observations": 6,
            "min_baseline_observations": 3,
            "min_formation_observations": 3,
            "min_follow_up_observations": 2,
            "min_follow_up_persistence": 0.66,
            "baseline_max_signal": 5,
            "min_signal": 5,
            "min_lift_ratio": 1.5,
            "quiet_max_signal": 5,
            "min_historical_positive_observations": 3,
            "min_quiet_observations": 3,
        }
    }


def weekly_points(values, start=date(2025, 5, 1)):
    return [
        {"time": (start + timedelta(days=index * 7)).isoformat(), "value": value}
        for index, value in enumerate(values)
    ]


def test_low_baseline_followed_by_persistent_rise_is_newly_observed(thresholds):
    birth = load_module("birth_history_new_red", BIRTH)

    result = birth.infer_demand_history(
        weekly_points([0, 0, 1, 0, 2, 12, 20, 24, 22, 18]), thresholds, "weekly"
    )

    assert result["demand_history_type"] == "newly_observed"
    assert result["estimated_birth_window"] == "2025-06 ~ 2025-07"
    assert result["birth_window_start"] == "2025-06"
    assert result["birth_window_end"] == "2025-07"
    assert result["birth_confidence"] in {"medium", "high"}
    assert result["birth_evidence_series"]


def test_longstanding_positive_series_is_preexisting_without_fake_birth_date(thresholds):
    birth = load_module("birth_history_preexisting_red", BIRTH)

    result = birth.infer_demand_history(weekly_points([25, 30, 28, 32, 31, 35]), thresholds, "weekly")

    assert result["demand_history_type"] == "preexisting"
    assert result["estimated_birth_window"] is None
    assert result["birth_window_start"] is None
    assert result["birth_reason"] == "before_available_history"


def test_quiet_period_after_old_demand_is_resurgent(thresholds):
    birth = load_module("birth_history_resurgent_red", BIRTH)

    result = birth.infer_demand_history(
        weekly_points([20, 22, 24, 0, 0, 0, 0, 15, 20, 25]), thresholds, "weekly"
    )

    assert result["demand_history_type"] == "resurgent"
    assert result["resurgence_window"] == "2025-06 ~ 2025-07"
    assert result["estimated_birth_window"] is None
    assert result["birth_reason"] == "before_available_history"


def test_single_spike_does_not_get_high_confidence_birth(thresholds):
    birth = load_module("birth_history_spike_red", BIRTH)

    result = birth.infer_demand_history(weekly_points([0, 0, 40, 0, 0]), thresholds, "weekly")

    assert result["demand_history_type"] == "unknown"
    assert result["birth_confidence"] != "high"
    assert result["estimated_birth_window"] is None


def test_series_starting_with_demand_is_before_available_history(thresholds):
    birth = load_module("birth_history_window_start_red", BIRTH)

    result = birth.infer_demand_history(weekly_points([20, 22, 24, 25, 28, 30]), thresholds, "weekly")

    assert result["demand_history_type"] == "preexisting"
    assert result["birth_reason"] == "before_available_history"
    assert result["estimated_birth_window"] is None


def test_timeframes_are_not_combined_for_growth():
    aggregate = load_module("aggregate_timeframe_isolation_red", AGGREGATE)
    rows = []
    for time_window, values, start in (
        ("5y", [10, 20], date(2025, 1, 1)),
        ("90d", [80, 90], date(2026, 8, 29)),
    ):
        for index, value in enumerate(values):
            rows.append(
                {
                    "keyword": "wedding",
                    "observed_at": (start + timedelta(days=index)).isoformat(),
                    "source": "google_trends",
                    "source_type": "interest_over_time",
                    "source_url": "https://trends.google.com/timeline",
                    "signal_value": value,
                    "signal_unit": "normalized_interest_index",
                    "country": "US",
                    "time_window": time_window,
                    "metric_source": "google_trends",
                    "metric_database": "US",
                }
            )

    result = aggregate.aggregate(rows, datetime(2026, 8, 30, tzinfo=timezone.utc))
    candidate = result["candidates"][0]

    assert len(candidate["source_evidence"]) == 2
    assert {series["time_window"] for series in candidate["source_evidence"]} == {"5y", "90d"}
    assert candidate["aggregation_policy"] == "no_cross_series_addition"


def test_google_breakout_label_does_not_create_canonical_breakout():
    classify = load_module("classify_google_breakout_separation_red", CLASSIFY)
    candidate = {
        "keyword": "micro wedding",
        "google_rising_label": "Breakout",
        "demand_history_type": "newly_observed",
        "root_id": None,
        "source_count": 1,
        "source_evidence": [{"source": "google_trends", "provenance_status": "verified"}],
        "primary_series": {
            "source": "google_trends",
            "provenance_status": "verified",
            "recent_7d": 40,
            "baseline_90d_7d": 0,
            "growth_rate_7d": None,
            "growth_status_7d": "from_observed_zero_baseline",
            "recent_7d_observations": 4,
            "persistence_7d": 1.0,
            "recent_observations": 4,
            "baseline_7d_observations": 4,
            "novelty_baseline_7d": 0,
            "novelty_baseline_7d_observations": 4,
            "historical_positive_7d_seen": False,
            "historical_positive_7d_observations": 0,
            "historical_positive_7d_windows": [],
            "latest_observation_age_days": 0,
            "peak_signal": 40,
            "latest_signal": 40,
        },
    }

    result = classify.classify_candidate(candidate, classify.load_thresholds())

    assert result["signal_type"] != "breakout"
    assert result["status"] != "breakout"


def test_resurgent_history_blocks_net_new_even_when_near_term_baseline_is_zero():
    classify = load_module("classify_resurgent_guard_red", CLASSIFY)
    candidate = {
        "keyword": "resurgent wedding term",
        "demand_history_type": "resurgent",
        "source_count": 1,
        "source_evidence": [{"source": "google_trends", "provenance_status": "verified"}],
        "primary_series": {
            "source": "google_trends",
            "provenance_status": "verified",
            "recent_7d": 40,
            "baseline_90d_7d": 0,
            "growth_rate_7d": None,
            "growth_status_7d": "from_observed_zero_baseline",
            "recent_7d_observations": 4,
            "persistence_7d": 1.0,
            "recent_observations": 4,
            "baseline_7d_observations": 4,
            "novelty_baseline_7d": 0,
            "novelty_baseline_7d_observations": 4,
            "historical_positive_7d_seen": False,
            "historical_positive_7d_observations": 0,
            "historical_positive_7d_windows": [],
            "latest_observation_age_days": 0,
            "peak_signal": 40,
            "latest_signal": 40,
        },
    }

    result = classify.classify_candidate(candidate, classify.load_thresholds())

    assert result["signal_type"] != "net_new"
