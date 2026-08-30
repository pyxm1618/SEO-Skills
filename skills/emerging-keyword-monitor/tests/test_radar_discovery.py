import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "radar_discovery.py"


def load_radar(name="radar_discovery_red"):
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rising(*queries):
    return [
        {
            "query": query,
            "relation_type": "rising",
            "rank": index + 1,
            "rising_value": 100 + index,
            "google_rising_label": None,
            "is_google_breakout": False,
            "source_url": "https://trends.google.com/related",
            "raw_evidence_ref": "related.json",
        }
        for index, query in enumerate(queries)
    ]


def test_rising_bfs_dedupes_and_obeys_parent_depth_and_cap():
    radar = load_radar("radar_discovery_bfs_red")
    graph = {
        "a": rising("b", "c"),
        "b": rising("d"),
        "c": rising("a", "e"),
        "d": [],
        "e": [],
    }

    result = radar.discover_rising_bfs(
        "domain",
        [{"keyword": "a", "discovery_depth": 0}],
        graph.__getitem__,
        relation_gate=lambda *_: ("in_scope", "fixture graph is in scope"),
        max_depth=2,
        max_candidates=4,
    )

    assert [row["keyword"] for row in result["candidates"]] == ["b", "c", "d", "e"]
    assert next(row for row in result["candidates"] if row["keyword"] == "d")["parent_anchor"] == "b"
    assert next(row for row in result["candidates"] if row["keyword"] == "d")["discovery_depth"] == 2
    assert "a" in result["visited"]
    assert len(result["candidates"]) == 4


def test_bfs_only_rising_rows_enqueue_and_top_rows_remain_context():
    radar = load_radar("radar_discovery_rising_only_red")

    def fetch(_):
        return [
            {"query": "top wedding", "relation_type": "top", "rank": 1},
            {"query": "rising wedding", "relation_type": "rising", "rank": 1},
        ]

    result = radar.discover_rising_bfs(
        "wedding",
        [{"keyword": "wedding", "discovery_depth": 0}],
        fetch,
        max_depth=1,
    )

    assert [row["keyword"] for row in result["candidates"]] == ["rising wedding"]
    assert result["anchor_evidence"]["wedding"][0]["relation_type"] == "top"
    assert result["visited"] == ["wedding"]


def test_out_of_domain_candidate_is_preserved_but_not_recursed():
    radar = load_radar("radar_discovery_drift_red")
    calls = []

    def fetch(keyword):
        calls.append(keyword)
        return rising("celebrity news")

    result = radar.discover_rising_bfs(
        "wedding",
        [{"keyword": "wedding", "discovery_depth": 0}],
        fetch,
        relation_gate=lambda *_: ("out_of_scope", "not a wedding search task"),
    )

    assert result["candidates"][0]["domain_relation"] == "out_of_scope"
    assert result["candidates"][0]["domain_relation_reason"] == "not a wedding search task"
    assert calls == ["wedding"]
    assert result["stops"][0]["reason"] == "domain_relation_out_of_scope"


def test_anchor_pool_marks_candidate_roots_without_limiting_discovery():
    radar = load_radar("radar_discovery_anchor_pool_red")
    anchors = radar.build_anchor_pool(
        "wedding",
        ["wedding budget"],
        [
            {
                "root_id": "root-wedding",
                "root": "wedding",
                "status": "active",
                "scope": "domain",
                "applicable_domains": "wedding",
            },
            {
                "root_id": "root-candidate",
                "root": "new ceremony format",
                "status": "candidate",
                "scope": "domain",
                "applicable_domains": "wedding",
            },
        ],
    )

    by_keyword = {row["keyword"]: row for row in anchors}
    assert set(by_keyword) == {"wedding", "wedding budget", "new ceremony format"}
    assert by_keyword["wedding"]["root_status"] == "active"
    assert by_keyword["new ceremony format"]["root_status"] == "candidate"
    assert by_keyword["new ceremony format"]["root_verified"] is False


def test_fetch_blocker_stops_only_the_current_branch_without_fallback():
    radar = load_radar("radar_discovery_blocker_red")

    def fetch(_):
        raise RuntimeError("Google CAPTCHA/unusual traffic page detected")

    result = radar.discover_rising_bfs(
        "wedding",
        [{"keyword": "wedding", "discovery_depth": 0}],
        fetch,
    )

    assert result["candidates"] == []
    assert result["blockers"][0]["status"] == "BLOCKED"
    assert "CAPTCHA" in result["blockers"][0]["reason"]
