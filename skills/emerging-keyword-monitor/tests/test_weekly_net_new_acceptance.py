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


def find_net_new_shapes(source):
    shapes = []
    used_terms = set()
    for term, payload in source["terms"].items():
        points = sorted(
            (date.fromisoformat(point["date"]), float(point["value"]))
            for point in payload.get("data", [])
        )
        for index in range(12, len(points)):
            history = points[: index + 1]
            as_of = history[-1][0]
            recent_30 = [(d, v) for d, v in history if 0 <= (as_of - d).days <= 29]
            prior_30_89 = [(d, v) for d, v in history if 30 <= (as_of - d).days <= 89]
            if len(recent_30) < 4 or len(prior_30_89) < 6:
                continue
            persistence = sum(v > 0 for _, v in recent_30) / len(recent_30)
            if persistence < 0.66 or history[-1][1] <= 0:
                continue
            if any(v != 0 for _, v in prior_30_89):
                continue
            if term in used_terms:
                continue
            used_terms.add(term)
            shapes.append({
                "term": term,
                "history": history,
                "as_of": as_of,
                "recent_30": recent_30,
                "prior_30_89": prior_30_89,
                "persistence": persistence,
            })
            if len(shapes) >= 10:
                return shapes
    return shapes


def observations(shape):
    return [
        {
            "keyword": shape["term"],
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
        }
        for observed, value in shape["history"]
    ]


def test_real_weekly_newly_observed_shapes_can_be_net_new(tmp_path):
    shapes = find_net_new_shapes(load_source())
    assert len(shapes) >= 3, f"expected at least 3 real net-new replay shapes, found {len(shapes)}"

    failures = []
    for shape in shapes:
        as_of = shape["as_of"].isoformat()
        aggregated = run(AGGREGATE, tmp_path, observations(shape), as_of)
        candidate = aggregated["candidates"][0]
        classified = run(CLASSIFY, tmp_path, {"candidates": [candidate]}, as_of)["candidates"][0]
        if classified["status"] != "emerging" or classified["signal_type"] != "net_new":
            failures.append({
                "term": shape["term"],
                "as_of": as_of,
                "actual_status": classified["status"],
                "actual_signal_type": classified["signal_type"],
                "baseline_signal": classified["baseline_signal"],
                "baseline_observations": classified["primary_series"]["baseline_observations"],
                "persistence_window": classified.get("persistence_window"),
                "persistence": classified.get("persistence"),
                "persistence_observations": classified.get("persistence_observations"),
                "prior_30_89_values": [v for _, v in shape["prior_30_89"]],
                "recent_30_values": [v for _, v in shape["recent_30"]],
            })

    assert not failures, json.dumps(failures, ensure_ascii=False, indent=2)
