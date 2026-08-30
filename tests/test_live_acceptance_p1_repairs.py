import importlib.util
import json
from pathlib import Path

import pytest

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


class _DelayedStatsLocator:
    def __init__(self, page):
        self.page = page

    @property
    def first(self):
        return self

    def count(self):
        return 1 if self.page.stats_ready else 0

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


class _DelayedStatsPage(_FakePage):
    def __init__(self):
        super().__init__()
        self.stats_ready = False

    def wait_for_selector(self, selector, state=None, timeout=None):
        assert selector == "#result-stats"
        assert state == "attached"
        self.stats_ready = True

    def locator(self, selector):
        if selector == "#result-stats":
            return _DelayedStatsLocator(self)
        return super().locator(selector)


class _DelayedStatsContext:
    def new_page(self):
        return _DelayedStatsPage()


class _NextAnchor:
    def __init__(self, href, label="Next"):
        self.href = href
        self.label = label

    def is_visible(self):
        return True

    def get_attribute(self, name):
        if name == "href":
            return self.href
        if name == "aria-label":
            return self.label
        raise AssertionError(f"unexpected attribute: {name}")

    def inner_text(self):
        return self.label


class _ResultH3:
    def __init__(self, title, href):
        self.title = title
        self.anchor = _Anchor(href)

    def is_visible(self):
        return True

    def inner_text(self):
        return self.title

    def locator(self, selector):
        if selector == "xpath=ancestor::a[1]":
            return self.anchor
        if selector == "a":
            return _Collection([])
        raise AssertionError(f"unexpected H3 selector: {selector}")


class _UnlinkedH3:
    def __init__(self, title):
        self.title = title

    def is_visible(self):
        return True

    def inner_text(self):
        return self.title

    def locator(self, selector):
        if selector in {"xpath=ancestor::a[1]", "a"}:
            return _Collection([])
        raise AssertionError(f"unexpected H3 selector: {selector}")


class _PagedPage:
    def __init__(self, page_states):
        self.page_states = page_states
        self.page_index = 0
        self.url = "https://www.google.com/search"
        self.goto_urls = []

    @property
    def state(self):
        return self.page_states[self.page_index]

    def goto(self, url, wait_until=None):
        self.goto_urls.append(url)
        if len(self.goto_urls) == 1:
            self.page_index = 0
        else:
            matches = [
                index for index, state in enumerate(self.page_states) if state.get("url") == url
            ]
            if not matches:
                self.url = url
                return
            self.page_index = matches[0]
        self.url = url

    def locator(self, selector):
        if selector == "#search h3":
            return _Collection(self.state["h3s"])
        if selector == "a#pnnext":
            next_url = self.state.get("next_url")
            return _Collection([_NextAnchor(next_url)] if next_url else [])
        if selector == "body":
            return _Body()
        raise AssertionError(f"unexpected paged selector: {selector}")


class _PagedContext:
    def __init__(self, page):
        self.page = page

    def new_page(self):
        return self.page


class _RedirectResponse:
    def __init__(self, url):
        self.url = url

    def dispose(self):
        return None


class _RedirectRequest:
    def __init__(self, urls):
        self.urls = urls

    def get(self, url, **kwargs):
        return _RedirectResponse(self.urls[url])


class _RedirectContext:
    def __init__(self, urls):
        self.request = _RedirectRequest(urls)


class _RedirectSerpPage(_PagedPage):
    def __init__(self, page_states, urls):
        super().__init__(page_states)
        self.context = _RedirectContext(urls)


class _DelayedSerpPage(_PagedPage):
    def __init__(self, page_states):
        super().__init__(page_states)
        self.headings_ready = False

    def wait_for_selector(self, selector, state=None, timeout=None):
        assert selector == "#search h3"
        assert state == "attached"
        self.headings_ready = True

    def locator(self, selector):
        if selector == "#search h3" and not self.headings_ready:
            return _Collection([])
        return super().locator(selector)


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


def test_intitle_waits_for_result_stats_to_mount_after_domcontentloaded(monkeypatch):
    google = load_module("live_p1_google_intitle_delayed_stats", GOOGLE)
    _patch_artifact_writes(monkeypatch, google)

    result = google.intitle(_DelayedStatsContext(), "wedding cost calculator", "US", ".")

    assert result["intitle_results"] == 540


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


def _serp_page_states(first_h3s, second_h3s=None, second_url=None, next_url=None):
    states = [{"h3s": first_h3s, "next_url": next_url}]
    if second_h3s is not None:
        states.append({"h3s": second_h3s, "url": second_url})
    return states


def _patch_serp_artifacts(monkeypatch, google):
    observations = []
    monkeypatch.setattr(google, "screenshot", lambda *args, **kwargs: "serp.png")
    monkeypatch.setattr(
        google,
        "evidence_json",
        lambda _directory, _name, payload: observations.append(payload) or "serp.json",
    )
    monkeypatch.setattr(google, "now", lambda: "2026-08-28T00:00:00Z")
    return observations


def test_serp_does_not_paginate_when_first_page_has_ten_results(monkeypatch):
    google = load_module("live_p1_google_no_pagination", GOOGLE)
    observations = _patch_serp_artifacts(monkeypatch, google)
    page = _PagedPage(_serp_page_states([_ResultH3(f"Result {i}", f"https://one{i}.example/") for i in range(1, 11)]))

    result = google.serp(_PagedContext(page), "wedding cost calculator", "US", ".")

    assert len(result["results"]) == 10
    assert len(page.goto_urls) == 1
    assert len(result["page_urls"]) == 1
    assert observations[0]["page_urls"] == result["page_urls"]


def test_serp_waits_for_result_headings_to_mount_after_domcontentloaded(monkeypatch):
    google = load_module("live_p1_google_delayed_serp", GOOGLE)
    _patch_serp_artifacts(monkeypatch, google)
    page = _DelayedSerpPage(_serp_page_states([_ResultH3(f"Result {i}", f"https://one{i}.example/") for i in range(1, 11)]))

    result = google.serp(_PagedContext(page), "wedding cost calculator", "US", ".")

    assert len(result["results"]) == 10
    assert page.headings_ready is True


def test_serp_resolves_current_google_redirect_links_to_final_urls(monkeypatch):
    google = load_module("live_p1_google_redirect_results", GOOGLE)
    _patch_serp_artifacts(monkeypatch, google)
    redirect_urls = {
        f"https://www.google.com/goto?url=encoded-{i}": f"https://one{i}.example/page"
        for i in range(1, 11)
    }
    first = [_ResultH3(f"Result {i}", f"/goto?url=encoded-{i}") for i in range(1, 11)]
    page = _RedirectSerpPage(_serp_page_states(first), redirect_urls)

    result = google.serp(_PagedContext(page), "wedding cost calculator", "US", ".")

    assert len(result["results"]) == 10
    assert result["results"][0]["url"] == "https://one1.example/page"


def test_serp_uses_next_google_page_to_complete_nine_results(monkeypatch):
    google = load_module("live_p1_google_pagination", GOOGLE)
    observations = _patch_serp_artifacts(monkeypatch, google)
    second_url = "https://www.google.com/search?q=wedding+cost+calculator&start=10"
    first = [_ResultH3(f"Result {i}", f"https://one{i}.example/") for i in range(1, 10)]
    second = [_ResultH3("Duplicate result", "https://one9.example/"), _ResultH3("Result 10", "https://ten.example/")]
    page = _PagedPage(_serp_page_states(first, second, second_url=second_url, next_url=second_url))

    result = google.serp(_PagedContext(page), "wedding cost calculator", "US", ".")

    assert len(result["results"]) == 10
    assert result["results"][-1] == {"rank": 10, "url": "https://ten.example/", "title": "Result 10"}
    assert [row["rank"] for row in result["results"]] == list(range(1, 11))
    assert result["page_urls"] == [page.goto_urls[0], second_url]
    assert observations[0]["page_urls"] == result["page_urls"]


def test_serp_blocks_without_next_page_when_fewer_than_ten_results(monkeypatch):
    google = load_module("live_p1_google_no_next", GOOGLE)
    _patch_serp_artifacts(monkeypatch, google)
    page = _PagedPage(_serp_page_states([_ResultH3(f"Result {i}", f"https://one{i}.example/") for i in range(1, 10)]))

    with pytest.raises(RuntimeError, match="only 9 organic results"):
        google.serp(_PagedContext(page), "wedding cost calculator", "US", ".")


def test_serp_blocks_when_next_page_link_leaves_google(monkeypatch):
    google = load_module("live_p1_google_wrong_next", GOOGLE)
    _patch_serp_artifacts(monkeypatch, google)
    first = [_ResultH3(f"Result {i}", f"https://one{i}.example/") for i in range(1, 10)]
    page = _PagedPage(_serp_page_states(first, next_url="https://not-google.example/next"))

    with pytest.raises(RuntimeError, match="google.com"):
        google.serp(_PagedContext(page), "wedding cost calculator", "US", ".")

    assert len(page.goto_urls) == 1


def test_serp_excludes_unlinked_ai_module_and_uses_real_next_result(monkeypatch):
    google = load_module("live_p1_google_ai_module", GOOGLE)
    observations = _patch_serp_artifacts(monkeypatch, google)
    second_url = "https://www.google.com/search?q=wedding+cost+calculator&start=10"
    first = [_ResultH3(f"Result {i}", f"https://one{i}.example/") for i in range(1, 10)]
    first.append(_UnlinkedH3("AI Overview"))
    second = [_ResultH3("Result 10", "https://ten.example/")]
    page = _PagedPage(_serp_page_states(first, second, second_url=second_url, next_url=second_url))

    result = google.serp(_PagedContext(page), "wedding cost calculator", "US", ".")

    assert len(result["results"]) == 10
    assert all("AI Overview" not in row["title"] for row in result["results"])
    assert observations[0]["results"] == result["results"]


def test_serp_blocks_when_limited_pages_still_have_fewer_than_ten_results(monkeypatch):
    google = load_module("live_p1_google_still_short", GOOGLE)
    _patch_serp_artifacts(monkeypatch, google)
    second_url = "https://www.google.com/search?q=wedding+cost+calculator&start=10"
    first = [_ResultH3(f"Result {i}", f"https://one{i}.example/") for i in range(1, 9)]
    second = [_ResultH3("Result 9", "https://nine.example/")]
    page = _PagedPage(_serp_page_states(first, second, second_url=second_url, next_url=second_url))

    with pytest.raises(RuntimeError, match="only 9 organic results"):
        google.serp(_PagedContext(page), "wedding cost calculator", "US", ".")
