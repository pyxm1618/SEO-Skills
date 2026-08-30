import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GOOGLE = ROOT / "runtime" / "collectors" / "google_live_collector.py"
VALIDATOR = ROOT / "runtime" / "stage_validator.py"
CONTRACTS = ROOT / "runtime" / "stage_contracts.json"


def load_google(name="google_live_collector_safety_red"):
    spec = importlib.util.spec_from_file_location(name, GOOGLE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    status = 200
    url = "https://trends.google.com/trends/api/widgetdata/multiline?req=timeline"

    def text(self):
        payload = {
            "default": {
                "timelineData": [
                    {"time": "1767225600", "formattedTime": "Jan 1, 2026", "value": [20]},
                    {"time": "1767830400", "formattedTime": "Jan 8, 2026", "value": [35]},
                ]
            }
        }
        return ")]}'\n" + json.dumps(payload)


class FakeBody:
    def inner_text(self, timeout=5000):
        return "Interest over time Related queries"


class FakePage:
    def __init__(self):
        self.url = "https://trends.google.com/trends/explore"
        self._listeners = []

    def on(self, event, callback):
        assert event == "response"
        self._listeners.append(callback)

    def goto(self, url, wait_until=None):
        self.url = url
        for callback in self._listeners:
            callback(FakeResponse())

    def wait_for_timeout(self, milliseconds):
        assert milliseconds >= 0

    def locator(self, selector):
        assert selector == "body"
        return FakeBody()


class FakeContext:
    def new_page(self):
        return FakePage()


class FakeGoogleContext:
    def __init__(self, cookies):
        self.cookies_seen = cookies

    def cookies(self, *args):
        return list(self.cookies_seen)


class FakeBrowser:
    def __init__(self, clean_context):
        self.contexts = [FakeGoogleContext([{"domain": ".google.com", "name": "SID"}])]
        self.created_context = clean_context
        self.new_context_called = False

    def new_context(self):
        self.new_context_called = True
        return self.created_context


class FakePlaywright:
    def __init__(self, browser):
        self.browser = browser
        self.cdp_urls = []
        self.chromium = self

    def start(self):
        return self

    def connect_over_cdp(self, url):
        self.cdp_urls.append(url)
        return self.browser


def patch_playwright(monkeypatch, google, browser):
    fake_pw = FakePlaywright(browser)
    monkeypatch.setattr(google, "playwright", lambda: lambda: fake_pw)
    return fake_pw


def test_timeline_preserves_requested_timeframe_and_infers_actual_resolution(monkeypatch):
    google = load_google("google_live_collector_timeline_red")
    monkeypatch.setattr(google, "screenshot", lambda *args, **kwargs: "timeline.png")
    monkeypatch.setattr(google, "evidence_json", lambda *args, **kwargs: "timeline.json")
    monkeypatch.setattr(google, "now", lambda: "2026-08-30T00:00:00Z")

    result = google.trends_timeline(FakeContext(), "wedding", "US", "today 5-y", ".")

    assert result["requested_timeframe"] == "today 5-y"
    assert result["actual_resolution"] == "weekly"
    assert result["google_trends_series"] == result["series"]


def test_timeline_result_uses_the_canonical_contract_field_names(monkeypatch):
    google = load_google("google_live_collector_timeline_contract_red")
    monkeypatch.setattr(google, "screenshot", lambda *args, **kwargs: "timeline.png")
    monkeypatch.setattr(google, "evidence_json", lambda *args, **kwargs: "timeline.json")
    monkeypatch.setattr(google, "now", lambda: "2026-08-30T00:00:00Z")

    result = google.trends_timeline(FakeContext(), "wedding", "US", "today 5-y", ".")
    result["evidence_receipt_ref"] = "timeline.receipt.json"
    validator = load_module("stage_validator_timeline_contract_red", VALIDATOR)
    contracts = json.loads(CONTRACTS.read_text(encoding="utf-8"))

    assert validator.validate_stage("trends_timeline", result, contracts) == []


def test_google_connection_uses_new_clean_context_without_inheriting_default_cookies(monkeypatch):
    google = load_google("google_live_collector_isolation_red")
    clean = FakeGoogleContext([])
    browser = FakeBrowser(clean)
    fake_pw = patch_playwright(monkeypatch, google, browser)
    monkeypatch.setenv("SEO_BROWSER_CDP_URL", "http://127.0.0.1:9222")
    monkeypatch.delenv("SEO_GOOGLE_CDP_URL", raising=False)

    pw, connected_browser, context = google.connect()

    assert pw is fake_pw
    assert connected_browser is browser
    assert context is browser.created_context
    assert browser.new_context_called is True
    assert context.cookies() == []
    assert context is not browser.contexts[0]


def test_google_connection_blocks_when_clean_context_cannot_be_created(monkeypatch):
    google = load_google("google_live_collector_no_isolation_red")

    class NoNewContextBrowser(FakeBrowser):
        new_context = None

    browser = NoNewContextBrowser(FakeGoogleContext([]))
    patch_playwright(monkeypatch, google, browser)
    monkeypatch.setenv("SEO_BROWSER_CDP_URL", "http://127.0.0.1:9222")
    monkeypatch.delenv("SEO_GOOGLE_CDP_URL", raising=False)

    with pytest.raises(RuntimeError, match="isolated|profile"):
        google.connect()


def test_google_connection_rejects_google_auth_cookies_in_selected_context(monkeypatch):
    google = load_google("google_live_collector_auth_cookie_red")
    browser = FakeBrowser(FakeGoogleContext([{"domain": ".google.com", "name": "SID"}]))
    patch_playwright(monkeypatch, google, browser)
    monkeypatch.setenv("SEO_BROWSER_CDP_URL", "http://127.0.0.1:9222")
    monkeypatch.delenv("SEO_GOOGLE_CDP_URL", raising=False)

    with pytest.raises(RuntimeError, match="authenticated|logged out|cookie"):
        google.connect()


def test_throttle_is_serial_and_uses_configured_delay():
    google = load_google("google_live_collector_throttle_red")
    sleeps = []
    throttle = google.Throttle(1.0, 0.0, sleeps.append, lambda: 0.0)

    throttle.wait()
    throttle.wait()

    assert sleeps == [1.0]
