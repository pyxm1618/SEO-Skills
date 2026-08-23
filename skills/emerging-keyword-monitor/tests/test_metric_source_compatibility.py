import json
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
AGGREGATE = BASE / "scripts" / "aggregate_signals.py"


def test_same_market_cross_source_core_metrics_are_not_compatible(tmp_path):
    rows = [
        {
            "keyword": "cross source metrics",
            "observed_at": "2026-08-20",
            "source": "semrush",
            "source_type": "keyword_metric",
            "source_url": "https://example.com/semrush",
            "signal_value": 10,
            "signal_unit": "index",
            "country": "US",
            "time_window": "daily",
            "metric_source": "semrush",
            "metric_database": "US",
            "volume": 1200,
            "kd": 30,
        },
        {
            "keyword": "cross source metrics",
            "observed_at": "2026-08-21",
            "source": "google_ads",
            "source_type": "keyword_metric",
            "source_url": "https://example.com/google-ads",
            "signal_value": 12,
            "signal_unit": "index",
            "country": "US",
            "time_window": "daily",
            "metric_source": "google_ads",
            "metric_database": "US",
            "cpc": 1.25,
        },
    ]
    path = tmp_path / "rows.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(AGGREGATE), "--input", str(path), "--format", "json", "--as-of", "2026-08-23"],
        capture_output=True,
        text=True,
        check=True,
    )
    candidate = json.loads(result.stdout)["candidates"][0]
    assert candidate["metric_status"] == "incompatible"
    assert candidate["metric_compatibility_status"] == "mixed_context"
