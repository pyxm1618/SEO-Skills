import json
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
AGGREGATE = BASE / "scripts" / "aggregate_signals.py"


def run(tmp_path, rows):
    path = tmp_path / "input.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(AGGREGATE), "--input", str(path), "--format", "json", "--as-of", "2026-08-23"],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)["candidates"][0]


def trend_row(time_window, lower_bound):
    return {
        "keyword": "blue jays vs yankees",
        "observed_at": "2026-08-23T06:18:00Z",
        "source": "google_trends",
        "source_type": "trending_now",
        "source_url": "https://trends.google.com/trending?geo=US&sort=search-volume",
        "root_id": None,
        "signal_value": lower_bound,
        "signal_unit": "searches_lower_bound",
        "country": "US",
        "time_window": time_window,
        "metric_source": "google_trends",
        "metric_database": "US",
        "trend_status": "active",
    }


def test_different_source_time_windows_do_not_inflate_persistence(tmp_path):
    # Real Google Trends snapshot on 2026-08-23: 100K+ in Past 24h and 200K+ in Past 48h.
    candidate = run(tmp_path, [
        trend_row("past_24h", 100000),
        trend_row("past_48h", 200000),
    ])

    assert len(candidate["source_evidence"]) == 2
    assert {e["time_window"] for e in candidate["source_evidence"]} == {"past_24h", "past_48h"}
    assert candidate["persistence_observations"] == 1
    assert candidate["primary_series"]["observation_count"] == 1
