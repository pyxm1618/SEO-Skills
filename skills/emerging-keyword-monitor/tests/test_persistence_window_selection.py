import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
AGGREGATE = BASE / "scripts" / "aggregate_signals.py"
CLASSIFY = BASE / "scripts" / "classify_emergence.py"


def run(script, tmp_path, payload, as_of):
    path = tmp_path / (script.stem + ".json")
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(script), "--input", str(path), "--format", "json", "--as-of", as_of],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def weekly_rows(values):
    start = date(2025, 1, 5)
    rows = []
    for index, value in enumerate(values):
        observed = start + timedelta(days=7 * index)
        rows.append({
            "keyword": "weekly replay",
            "observed_at": observed.isoformat(),
            "source": "google_trends",
            "source_type": "interest_over_time",
            "source_url": "https://example.com/weekly-source",
            "root_id": None,
            "signal_value": value,
            "signal_unit": "normalized_interest_index",
            "country": "US",
            "time_window": "weekly",
            "metric_source": "google_trends",
            "metric_database": "weekly-regression",
        })
    return rows


def classify_rows(tmp_path, values):
    as_of = "2025-04-06"
    aggregated = run(AGGREGATE, tmp_path, weekly_rows(values), as_of)
    candidate = aggregated["candidates"][0]
    return run(CLASSIFY, tmp_path, {"candidates": [candidate]}, as_of)["candidates"][0]


def test_weekly_stable_series_can_be_mature(tmp_path):
    row = classify_rows(tmp_path, [10] * 14)
    assert row["status"] == "mature"
    assert row["persistence_observations"] >= 3
    assert row["persistence_window"] == "recent_30d"


def test_weekly_persistent_rise_can_be_breakout(tmp_path):
    row = classify_rows(tmp_path, [1] * 10 + [1, 2, 4, 20])
    assert row["status"] == "breakout"
    assert row["signal_type"] == "breakout"
    assert row["persistence_observations"] >= 3
    assert row["persistence_window"] == "recent_30d"


def test_weekly_new_demand_uses_pre_recent_baseline_for_net_new(tmp_path):
    # Five recent weekly points contain four positives (0.80 persistence), so this
    # fixture satisfies the production confirmation threshold instead of relying on
    # a below-threshold 3/5 sample.
    row = classify_rows(tmp_path, [0] * 9 + [0, 1, 2, 4, 8])
    assert row["persistence_window"] == "recent_30d"
    assert row["persistence_observations"] >= 3
    assert row["persistence"] >= 0.66
    assert row["novelty_baseline_signal"] == 0
    assert row["status"] == "emerging"
    assert row["signal_type"] == "net_new"
