import json
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
AGGREGATE = BASE / "scripts" / "aggregate_signals.py"
CLASSIFY = BASE / "scripts" / "classify_emergence.py"

SOURCE_URL = "https://trends.google.com/trending?geo=US&sort=search-volume"
OBSERVED_AT = "2026-08-23T06:16:00Z"

LIVE_TRENDS = [
    ("blue jays vs yankees", 100000),
    ("michael wright", 100000),
    ("hull vs man united", 200000),
    ("brentford vs spurs", 50000),
    ("nick chubb", 100000),
    ("john sarcone disqualified u.s. attorney", 100000),
    ("ed oliver son", 20000),
    ("klay thompson", 100000),
    ("pirates vs dodgers", 100000),
    ("dollar tree halloween icon glasses", 20000),
    ("cubs vs mariners", 100000),
    ("commanders vs lions", 50000),
    ("giants vs red sox", 50000),
    ("boston", 20000),
    ("cardinals vs phillies", 100000),
    ("james o keefe", 20000),
    ("braves vs brewers", 100000),
    ("la liga", 20000),
    ("athletic - sevilla", 10000),
    ("police", 20000),
    ("mount fuji", 20000),
    ("canada tariffs trump", 20000),
    ("musk", 20000),
    ("horror", 20000),
    ("inter vs monza", 10000),
]


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


def observation(keyword, lower_bound):
    return {
        "keyword": keyword,
        "observed_at": OBSERVED_AT,
        "source": "google_trends",
        "source_type": "trending_now",
        "source_url": SOURCE_URL,
        "root_id": None,
        "signal_value": lower_bound,
        "signal_unit": "searches_lower_bound",
        "country": "US",
        "time_window": "past_24h",
        "metric_source": "google_trends",
        "metric_database": "US",
        "trend_status": "active",
    }


def test_live_google_trends_snapshot_is_conservative(tmp_path):
    observations = [observation(keyword, lower_bound) for keyword, lower_bound in LIVE_TRENDS]
    aggregated = run(AGGREGATE, tmp_path, observations, "--as-of", "2026-08-23")
    assert aggregated["invalid_observation_count"] == 0
    assert len(aggregated["candidates"]) == 25

    classified = run(CLASSIFY, tmp_path, aggregated, "--as-of", "2026-08-23")["candidates"]
    assert len(classified) == 25

    summary = {}
    for candidate in classified:
        summary[candidate["keyword"]] = candidate["status"]
        assert candidate["trend_status"] == "active"
        assert candidate["source_count"] == 1
        assert candidate["unique_observation_count"] == 1
        assert candidate["persistence_observations"] == 1
        assert candidate["status"] == "new_signal"
        assert candidate["signal_type"] is None
        assert candidate["metric_status"] == "incomplete"
        assert candidate["volume"] is None
        assert candidate["kd"] is None
        assert candidate["cpc"] is None

    print("LIVE_SNAPSHOT_SUMMARY=" + json.dumps(summary, sort_keys=True))
