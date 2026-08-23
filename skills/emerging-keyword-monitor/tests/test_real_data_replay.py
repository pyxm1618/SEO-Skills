import json
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
AGGREGATE = BASE / "scripts" / "aggregate_signals.py"
CLASSIFY = BASE / "scripts" / "classify_emergence.py"


def run(script, tmp_path, payload, *args):
    path = tmp_path / "input.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(script), "--input", str(path), "--format", "json", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def trend_obs(**overrides):
    row = {
        "keyword": "pirates vs dodgers",
        "observed_at": "2026-08-23T05:00:00Z",
        "source": "google_trends",
        "source_type": "trending_now",
        "source_url": "https://trends.google.com/trending?geo=US",
        "root_id": None,
        "signal_value": 5000,
        "signal_unit": "searches_approx",
        "country": "US",
        "time_window": "past_4h",
        "metric_source": "google_trends",
        "metric_database": "US",
    }
    row.update(overrides)
    return row


def test_lasted_google_trends_snapshot_is_not_new_signal(tmp_path):
    rows = [trend_obs(keyword="daylight saving time", trend_status="lasted")]
    candidate = run(AGGREGATE, tmp_path, rows, "--as-of", "2026-08-23")["candidates"][0]
    assert candidate["trend_status"] == "lasted"

    classified = run(CLASSIFY, tmp_path, {"candidates": [candidate]}, "--as-of", "2026-08-23")["candidates"][0]
    assert classified["status"] == "watch"
    assert classified["signal_type"] is None
    assert "ended" in classified["status_reason"].lower()


def test_localized_google_trends_urls_do_not_inflate_persistence(tmp_path):
    rows = [
        trend_obs(source_url="https://trends.google.com/trending?geo=US&hl=en"),
        trend_obs(source_url="https://trends.google.com/trending?geo=US&hl=es"),
        trend_obs(source_url="https://trends.google.com/trending?geo=US&hl=fr"),
        trend_obs(source_url="https://trends.google.com/trending?geo=US&hl=zh-CN"),
    ]
    candidate = run(AGGREGATE, tmp_path, rows, "--as-of", "2026-08-23")["candidates"][0]
    assert candidate["duplicate_observation_count"] == 3
    assert candidate["unique_observation_count"] == 1
    assert candidate["primary_series"]["observation_count"] == 1
    assert candidate["persistence_observations"] == 1
