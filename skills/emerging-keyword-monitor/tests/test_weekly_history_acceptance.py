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
    mature_by_term = {}
    breakout_by_term = {}

    for term, payload in source["terms"].items():
        points = sorted(
            (date.fromisoformat(point["date"]), float(point["value"]))
            for point in payload.get("data", [])
        )
        if len(points) < 14:
            continue

        for index in range(13, len(points)):
            history = points[: index + 1]
            as_of = history[-1][0]
            if (as_of - history[0][0]).days < 90:
                continue

            recent_30 = [(d, v) for d, v in history if 0 <= (as_of - d).days <= 29]
            baseline_90 = [v for d, v in history if 7 <= (as_of - d).days <= 89]
            if len(recent_30) < 4 or sum(v > 0 for _, v in recent_30) < 3 or not baseline_90:
                continue

            baseline = sum(baseline_90) / len(baseline_90)
            latest = history[-1][1]
            if baseline <= 0 or latest <= 0:
                continue
            growth = (latest - baseline) / baseline
            item = {
                "term": term,
                "history": history,
                "as_of": as_of,
                "baseline": baseline,
                "latest": latest,
                "growth": growth,
            }

            if abs(growth) < 0.5:
                current = mature_by_term.get(term)
                if current is None or abs(growth) < abs(current["growth"]):
                    mature_by_term[term] = item
            elif growth >= 1.0:
                current = breakout_by_term.get(term)
                if current is None or growth > current["growth"]:
                    breakout_by_term[term] = item

    breakout = sorted(breakout_by_term.values(), key=lambda item: item["growth"], reverse=True)
    breakout_terms = {item["term"] for item in breakout[:10]}
    mature = sorted(
        (item for term, item in mature_by_term.items() if term not in breakout_terms),
        key=lambda item: abs(item["growth"]),
    )

    selected = [("breakout", item) for item in breakout[:10]]
    selected += [("mature", item) for item in mature[:15]]
    return selected, len(mature_by_term), len(breakout_by_term)


def to_observations(item):
    rows = []
    for observed, value in item["history"]:
        rows.append({
            "keyword": item["term"],
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
    selected, mature_count, breakout_count = select_real_shapes(source)
    assert len(selected) >= 20, (
        f"source did not yield 20 distinct replay terms: mature={mature_count}, breakout={breakout_count}"
    )

    failures = []
    for expected, item in selected:
        as_of = item["as_of"].isoformat()
        aggregated = run(AGGREGATE, tmp_path, to_observations(item), as_of)
        assert aggregated["invalid_observation_count"] == 0
        candidate = aggregated["candidates"][0]
        classified = run(CLASSIFY, tmp_path, {"candidates": [candidate]}, as_of)["candidates"][0]

        if classified["status"] != expected:
            failures.append({
                "term": item["term"],
                "as_of": as_of,
                "expected": expected,
                "actual": classified["status"],
                "recent_observations": classified["primary_series"]["recent_observations"],
                "persistence_observations": classified["persistence_observations"],
                "baseline": item["baseline"],
                "latest": item["latest"],
                "growth": item["growth"],
            })

    assert not failures, json.dumps(failures, ensure_ascii=False, indent=2)
