import json
import subprocess
import sys
import urllib.request
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
AGGREGATE = BASE / "scripts" / "aggregate_signals.py"
CLASSIFY = BASE / "scripts" / "classify_emergence.py"
SOURCE_URL = "https://raw.githubusercontent.com/lukeslp/us-attention-data/main/trends_data.json"


def load_source():
    request = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "SEO-Skills-real-replay/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


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


def select_real_shapes(source):
    all_dates = [
        date.fromisoformat(point["date"])
        for payload in source["terms"].values()
        for point in payload.get("data", [])
    ]
    as_of = max(all_dates)
    mature = []
    breakout = []

    for term, payload in source["terms"].items():
        points = sorted(
            (date.fromisoformat(point["date"]), float(point["value"]))
            for point in payload.get("data", [])
        )
        if len(points) < 14 or points[-1][0] != as_of:
            continue
        if (as_of - points[0][0]).days < 90:
            continue

        recent_30 = [(d, v) for d, v in points if 0 <= (as_of - d).days <= 29]
        baseline_90 = [v for d, v in points if 7 <= (as_of - d).days <= 89]
        if len(recent_30) < 4 or sum(v > 0 for _, v in recent_30) < 3 or not baseline_90:
            continue

        baseline = sum(baseline_90) / len(baseline_90)
        latest = points[-1][1]
        if baseline <= 0 or latest <= 0:
            continue
        growth = (latest - baseline) / baseline

        item = (term, points, baseline, latest, growth)
        if abs(growth) < 0.5:
            mature.append(item)
        elif growth >= 1.0:
            breakout.append(item)

    mature.sort(key=lambda x: abs(x[4]))
    breakout.sort(key=lambda x: x[4], reverse=True)
    selected = [("mature", item) for item in mature[:15]] + [("breakout", item) for item in breakout[:10]]
    if len(selected) < 20:
        remaining = [("mature", item) for item in mature[15:]] + [("breakout", item) for item in breakout[10:]]
        selected.extend(remaining[: 20 - len(selected)])
    return as_of, selected, len(mature), len(breakout)


def to_observations(selected):
    rows = []
    for expected, (term, points, baseline, latest, growth) in selected:
        for observed, value in points:
            rows.append({
                "keyword": term,
                "observed_at": observed.isoformat(),
                "source": "google_trends",
                "source_type": "interest_over_time",
                "source_url": SOURCE_URL,
                "root_id": None,
                "signal_value": value,
                "signal_unit": "normalized_interest_index",
                "country": "US",
                "time_window": "weekly",
                "metric_source": "google_trends",
                "metric_database": "us-attention-data",
            })
    return rows


def test_real_weekly_history_can_reach_mature_and_breakout_states(tmp_path):
    source = load_source()
    as_of, selected, mature_count, breakout_count = select_real_shapes(source)
    assert len(selected) >= 20, (
        f"source did not yield 20 replay shapes: mature={mature_count}, breakout={breakout_count}, as_of={as_of}"
    )

    observations = to_observations(selected)
    aggregated = run(AGGREGATE, tmp_path, observations, as_of.isoformat())
    assert aggregated["invalid_observation_count"] == 0

    classified = run(CLASSIFY, tmp_path, aggregated, as_of.isoformat())["candidates"]
    actual = {row["keyword"]: row for row in classified}

    failures = []
    for expected, (term, points, baseline, latest, growth) in selected:
        row = actual[term]
        if row["status"] != expected:
            failures.append({
                "term": term,
                "expected": expected,
                "actual": row["status"],
                "recent_observations": row["primary_series"]["recent_observations"],
                "persistence_observations": row["persistence_observations"],
                "baseline": baseline,
                "latest": latest,
                "growth": growth,
            })

    assert not failures, json.dumps(failures, ensure_ascii=False, indent=2)
