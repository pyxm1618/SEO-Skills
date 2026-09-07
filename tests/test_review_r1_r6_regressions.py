import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DISCOVERY_COVERAGE = ROOT / "runtime" / "discovery_coverage.py"
EMERGING_PIPELINE = ROOT / "runtime" / "emerging_pipeline.py"
RADAR = ROOT / "skills" / "emerging-keyword-monitor" / "scripts" / "run_emerging_radar.py"
RADAR_DISCOVERY = ROOT / "skills" / "emerging-keyword-monitor" / "scripts" / "radar_discovery.py"
GOOGLE = ROOT / "runtime" / "collectors" / "google_live_collector.py"
SERP_CLUSTER = ROOT / "skills" / "seo-keyword-selection" / "scripts" / "cluster_by_serp.py"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_r1_expansions_are_registered_and_extracted_as_observed_keywords():
    coverage = load_module("review_r1_coverage", DISCOVERY_COVERAGE)

    assert coverage.SOURCE_EVIDENCE_TYPES["google_serp_expansions"] == "google_serp_expansions"
    normalized = {
        "people_also_ask": ["How does an I Ching reading work?"],
        "related_searches": ["i ching reading online"],
    }
    assert coverage._observed_keywords(normalized, "google_serp_expansions") == [
        "how does an i ching reading work?",
        "i ching reading online",
    ]


def _emerging_observation(observed_at, signal_value, **context):
    row = {
        "keyword": "new helper expression",
        "observed_at": observed_at,
        "source": "google_trends",
        "source_type": "interest_over_time",
        "source_url": "https://trends.google.com/trends/explore?q=new+helper+expression",
        "signal_value": signal_value,
        "signal_unit": "normalized_interest_index",
        "country": "US",
        "time_window": "90d",
        "metric_source": "google_trends",
        "metric_database": "US",
        "root_id": "root-helper",
    }
    row.update(context)
    return row


def test_r2_canonical_pipeline_preserves_business_context_through_aggregation(tmp_path):
    pipeline = load_module("review_r2_pipeline", EMERGING_PIPELINE)
    as_of = datetime(2026, 9, 7, 23, 59, tzinfo=timezone.utc)
    context = {
        "domain": "example.com",
        "variant_subtype": "new_expression",
        "variant_evidence": "semantic relationship reviewed",
        "root_relation": "root_candidate",
        "root_candidate_hypothesis": "new stable helper family",
        "previous_status": "watch",
    }
    rows = [
        _emerging_observation((as_of - timedelta(days=offset)).isoformat(), 50, **context)
        for offset in (2, 1, 0)
    ]
    input_path = tmp_path / "observations.json"
    input_path.write_text(json.dumps(rows), encoding="utf-8")

    result = pipeline.replay_pipeline(input_path, as_of)
    candidate = result["classified"]["candidates"][0]

    assert candidate["domain"] == "example.com"
    assert candidate["variant_subtype"] == "new_expression"
    assert candidate["variant_evidence"] == "semantic relationship reviewed"
    assert candidate["root_relation"] == "root_candidate"
    assert candidate["root_candidate_hypothesis"] == "new stable helper family"
    assert candidate["previous_status"] == "watch"


def test_r3_radar_carries_watching_database_records_into_next_timeline_run():
    radar = load_module("review_r3_radar", RADAR)
    calls = []

    def related_fetcher(_anchor):
        return {"related_queries": []}

    def timeline_fetcher(keyword, timeframe):
        calls.append((keyword, timeframe))
        return {
            "series": [
                {"time": "2026-09-06T00:00:00+00:00", "value": 20},
                {"time": "2026-09-07T00:00:00+00:00", "value": 25},
            ],
            "observed_at": "2026-09-07T00:00:00+00:00",
            "source_url": "https://trends.google.com/trends/explore?q=legacy+topic",
            "market": "US",
            "actual_resolution": "daily",
            "raw_evidence_ref": "evidence/legacy-topic.json",
        }

    existing_database = {
        "schema_version": 1,
        "records": [
            {
                "domain": "example.com",
                "keyword": "legacy topic",
                "root_id": "root-legacy",
                "status": "watch",
                "observation_state": "watching",
                "first_observed_at": "2026-09-01",
                "last_seen_at": "2026-09-01T00:00:00+00:00",
            }
        ],
    }

    result = radar.run_pipeline(
        related_fetcher,
        domain="example.com",
        max_depth=1,
        timeline_fetcher=timeline_fetcher,
        timeframe_specs=(("90d", "today 3-m"),),
        as_of=datetime(2026, 9, 7, 23, 59, tzinfo=timezone.utc),
        discovered_at="2026-09-07T12:00:00+00:00",
        existing_database=existing_database,
    )

    assert calls == [("legacy topic", "today 3-m")]
    assert result["candidate_counts"]["classified"] == 1
    assert result["candidates"][0]["previous_status"] == "watch"


def test_r4_recursive_rising_candidates_keep_verified_existing_root_relation():
    discovery = load_module("review_r4_discovery", RADAR_DISCOVERY)
    anchors = [
        {
            "keyword": "wedding",
            "anchor_source": "root_bootstrap",
            "discovery_depth": 0,
            "root_id": "root-wedding",
            "root_status": "active",
            "root_verified": True,
        }
    ]
    related = {
        "wedding": [{"query": "micro wedding", "relation_type": "rising"}],
        "micro wedding": [{"query": "micro wedding helper", "relation_type": "rising"}],
    }

    result = discovery.discover_rising_bfs(
        "wedding",
        anchors,
        lambda anchor: {"related_queries": related.get(anchor, [])},
        relation_gate=lambda *_args: ("in_scope", "test relation"),
        max_depth=2,
    )

    by_keyword = {row["keyword"]: row for row in result["candidates"]}
    assert by_keyword["micro wedding"]["root_relation"] == "existing_root"
    assert by_keyword["micro wedding helper"]["root_id"] == "root-wedding"
    assert by_keyword["micro wedding helper"]["root_relation"] == "existing_root"


class _FakeNode:
    def __init__(self, text=""):
        self.text = text

    def is_visible(self):
        return True

    def inner_text(self):
        return self.text


class _FakeLocator:
    def __init__(self, nodes=None):
        self.nodes = list(nodes or [])
        self.first = self

    def is_visible(self):
        return True

    def fill(self, _value):
        return None

    def all(self):
        return self.nodes


class _FakePage:
    def __init__(self):
        self.url = "https://www.google.com/search"

    def locator(self, selector):
        if "textarea" in selector or "input[name=\"q\"]" in selector:
            return _FakeLocator()
        if selector in ('[role="option"]', 'ul[role="listbox"] li'):
            return _FakeLocator([_FakeNode("相关建议")])
        return _FakeLocator()

    def wait_for_timeout(self, _ms):
        return None


class _FakeContext:
    def new_page(self):
        return _FakePage()


def test_r5_chinese_autocomplete_evidence_names_do_not_collide(tmp_path, monkeypatch):
    google = load_module("review_r5_google", GOOGLE)
    names = []
    monkeypatch.setattr(google, "goto_google", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        google,
        "screenshot",
        lambda _page, evidence_dir, name: names.append(name) or str(Path(evidence_dir) / name),
    )
    monkeypatch.setattr(
        google,
        "evidence_json",
        lambda evidence_dir, name, _payload: names.append(name) or str(Path(evidence_dir) / name),
    )

    google.autocomplete(_FakeContext(), "易经", "US", "zh-CN", tmp_path)
    google.autocomplete(_FakeContext(), "六爻", "US", "zh-CN", tmp_path)

    assert len(set(names)) == 4
    assert "autocomplete-.png" not in names
    assert "autocomplete-.json" not in names


def test_r5_chinese_domain_relation_does_not_treat_nonempty_keyword_as_empty():
    discovery = load_module("review_r5_relation", RADAR_DISCOVERY)
    relation, reason = discovery.default_domain_relation("易经", "易经六爻排盘", "易经")
    assert relation == "in_scope", reason


def test_r6_serp_canonicalization_keeps_document_identity_params_and_drops_tracking():
    cluster = load_module("review_r6_cluster", SERP_CLUSTER)

    left = cluster.canonical_url("https://example.com/article.php?id=101&utm_source=google")
    right = cluster.canonical_url("https://example.com/article.php?id=202&utm_source=google")
    left_without_tracking = cluster.canonical_url("https://example.com/article.php?id=101")

    assert left != right
    assert left == left_without_tracking
