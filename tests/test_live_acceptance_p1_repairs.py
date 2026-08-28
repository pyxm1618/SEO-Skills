import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "runtime" / "stage_validator.py"
CONTRACTS = ROOT / "runtime" / "stage_contracts.json"
GOOGLE = ROOT / "runtime" / "collectors" / "google_live_collector.py"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_semrush_ideas_validates_the_top_level_envelope_not_each_row():
    validator = load_module("live_p1_validator", VALIDATOR)
    contracts = json.loads(CONTRACTS.read_text(encoding="utf-8"))
    payload = {
        "seed": "wedding calculator",
        "rows": [{"keyword": "wedding budget calculator", "volume": 2400, "kd": 12, "cpc": 1.2}],
        "observed_at": "2026-08-28T00:00:00Z",
        "metric_source": "Semrush",
        "relay_origin": "https://sem.3ue.com/",
        "provenance_ref": "relay-capture.json",
    }

    complete, blocked = validator.validate_payload(
        "discovery_semrush_ideas", payload, contracts, production=False
    )

    assert blocked == []
    assert complete == [payload]


class _StatsLocator:
    @property
    def first(self):
        return self

    def count(self):
        return 1

    def is_visible(self):
        return False

    def inner_text(self):
        return "About 540 results (0.48 seconds)"


class _Anchor:
    @property
    def first(self):
        return self

    def count(self):
        return 1

    def get_attribute(self, name):
        assert name == "href"
        return self.href

    def __init__(self, href):
        self.href = href


class _H3:
    def __init__(self, rank):
        self.rank = rank
        self.anchor = _Anchor(f"https://example{rank}.com/page")

    def is_visible(self):
        return True

    def inner_text(self):
        return f"Organic result {self.rank}"

    def locator(self, selector):
        assert selector == "xpath=ancestor::a[1]"
        return self.anchor


class _Collection:
    def __init__(self, items):
        self.items = items

    def all(self):
        return list(self.items)


class _Body:
    def inner_text(self, timeout=5000):
        return "normal google search results"


class _FakePage:
    def __init__(self):
        self.url = "https://www.google.com/search"
        self.h3s = [_H3(i) for i in range(1, 11)]

    def goto(self, url, wait_until=None):
        self.url = url

    def locator(self, selector):
        if selector == "#result-stats":
            return _StatsLocator()
        if selector == "#search h3":
            return _Collection(self.h3s)
        if selector == "#search a":
            # Mirrors the live DOM shape that broke the old implementation:
            # h3 contains a, so walking anchors and looking for child h3 finds none.
            return _Collection([])
        if selector == "body":
            return _Body()
        raise AssertionError(f"unexpected selector: {selector}")


class _Context:
    def new_page(self):
        return _FakePage()


def _patch_artifact_writes(monkeypatch, google):
    monkeypatch.setattr(google, "screenshot", lambda *args, **kwargs: "evidence.png")
    monkeypatch.setattr(google, "evidence_json", lambda *args, **kwargs: "observation.json")
    monkeypatch.setattr(google, "now", lambda: "2026-08-28T00:00:00Z")


def test_intitle_accepts_result_stats_text_even_when_google_marks_node_not_visible(monkeypatch):
    google = load_module("live_p1_google_intitle", GOOGLE)
    _patch_artifact_writes(monkeypatch, google)

    result = google.intitle(_Context(), "wedding cost calculator", "US", ".")

    assert result["intitle_results"] == 540
    assert result["source"] == "Google"


def test_serp_walks_visible_h3_titles_to_their_ancestor_links(monkeypatch):
    google = load_module("live_p1_google_serp", GOOGLE)
    _patch_artifact_writes(monkeypatch, google)

    result = google.serp(_Context(), "wedding cost calculator", "US", ".")

    assert len(result["results"]) == 10
    assert result["results"][0] == {
        "rank": 1,
        "url": "https://example1.com/page",
        "title": "Organic result 1",
    }
