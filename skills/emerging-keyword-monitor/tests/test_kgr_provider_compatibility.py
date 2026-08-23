import json
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
AGGREGATE = BASE / "scripts" / "aggregate_signals.py"
CLASSIFY = BASE / "scripts" / "classify_emergence.py"


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


def test_semrush_core_metrics_and_google_intitle_are_compatible_end_to_end(tmp_path):
    rows = [
        {
            "keyword": "provider compatibility query",
            "observed_at": "2026-08-22",
            "source": "semrush",
            "source_type": "keyword_metrics",
            "source_url": "https://example.com/semrush-us",
            "signal_value": 10,
            "signal_unit": "index",
            "country": "US",
            "time_window": "daily",
            "metric_source": "semrush",
            "metric_database": "US",
            "volume": 1000,
            "kd": 20,
            "cpc": 0.30,
        },
        {
            "keyword": "provider compatibility query",
            "observed_at": "2026-08-23",
            "source": "google_search",
            "source_type": "serp_observation",
            "source_url": "https://www.google.com/search?q=intitle%3A%22provider+compatibility+query%22",
            "signal_value": 1,
            "signal_unit": "serp_observation",
            "country": "US",
            "time_window": "point_in_time",
            "metric_source": "google_search",
            "metric_database": "US",
            "intitle_results": 100,
        },
    ]

    aggregated = run(
        AGGREGATE,
        tmp_path,
        rows,
        "--as-of",
        "2026-08-23",
    )["candidates"][0]

    assert aggregated["metric_status"] == "complete"
    assert aggregated["metric_compatibility_status"] == "compatible"

    classified = run(
        CLASSIFY,
        tmp_path,
        {"candidates": [aggregated]},
        "--as-of",
        "2026-08-23",
    )["candidates"][0]

    assert classified["metric_status"] == "complete"
    assert classified["kgr"] == 0.1
