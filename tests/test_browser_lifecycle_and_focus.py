"""Tests for browser background lifecycle, worker page reuse, listener cleanup, and NEEDS_HUMAN control signal."""

import importlib.util
import json
import pytest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COLLECTOR = ROOT / "runtime" / "collectors" / "google_live_collector.py"
LAUNCHER = ROOT / "runtime" / "start_live_browser.py"
RADAR_DISCOVERY = ROOT / "skills" / "emerging-keyword-monitor" / "scripts" / "radar_discovery.py"
RADAR = ROOT / "skills" / "emerging-keyword-monitor" / "scripts" / "run_emerging_radar.py"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakePage:
    def __init__(self, url="https://www.google.com/"):
        self.url = url
        self.closed = False
        self.listeners = {}

    def close(self):
        self.closed = True

    def locator(self, selector):
        return self

    def inner_text(self, timeout=5000):
        return "Normal search result text"

    def on(self, event, handler):
        self.listeners.setdefault(event, []).append(handler)

    def remove_listener(self, event, handler):
        if event in self.listeners and handler in self.listeners[event]:
            self.listeners[event].remove(handler)


class FakeCaptchaPage(FakePage):
    def __init__(self, url="https://www.google.com/sorry/index?continue=..."):
        super().__init__(url)

    def inner_text(self, timeout=5000):
        return "Our systems have detected unusual traffic from your computer network. Please solve this captcha."


class FakeContext:
    def __init__(self, pages=None):
        self.pages = list(pages or [])
        self.created_pages = []

    def new_page(self):
        page = FakePage()
        self.created_pages.append(page)
        self.pages.append(page)
        return page


def test_shared_human_intervention_required_class():
    if str(RADAR_DISCOVERY.parent) not in sys.path:
        sys.path.insert(0, str(RADAR_DISCOVERY.parent))
    import radar_discovery
    import run_emerging_radar
    assert run_emerging_radar.HumanInterventionRequired is radar_discovery.HumanInterventionRequired


def test_worker_page_reuses_existing_normal_page():
    google = load_module("google_test_reuse", COLLECTOR)
    existing_page = FakePage("https://www.google.com/ncr")
    context = FakeContext(pages=[existing_page])

    with google.worker_page_context(context) as page:
        assert page is existing_page
        assert len(context.pages) == 1
        assert len(context.created_pages) == 0

    assert not existing_page.closed
    assert len(context.pages) == 1


def test_worker_page_creates_new_when_no_page():
    google = load_module("google_test_create", COLLECTOR)
    context = FakeContext(pages=[])

    with google.worker_page_context(context) as page:
        assert page in context.created_pages
        assert len(context.pages) == 1

    assert not page.closed


def test_worker_page_raises_when_existing_blocker_page_present():
    google = load_module("google_test_blocker_strict", COLLECTOR)
    captcha_page = FakeCaptchaPage()
    context = FakeContext(pages=[captcha_page])

    with pytest.raises(google.HumanInterventionRequired) as exc_info:
        google.get_worker_page(context)

    assert exc_info.value.blocker_type == "existing_unresolved_blocker"
    assert len(context.created_pages) == 0
    assert len(context.pages) == 1


def test_assert_google_raises_human_intervention_on_captcha():
    google = load_module("google_test_captcha", COLLECTOR)
    captcha_page = FakeCaptchaPage()

    with pytest.raises(google.HumanInterventionRequired) as exc_info:
        google.assert_google(captcha_page)

    assert "CAPTCHA" in str(exc_info.value)
    assert exc_info.value.blocker_type == "unusual_traffic_captcha"
    assert "sorry" in exc_info.value.url


def test_assert_google_fail_closed_on_inspection_error():
    google = load_module("google_test_fail_closed", COLLECTOR)

    class FailingPage(FakePage):
        def inner_text(self, timeout=5000):
            raise TimeoutError("Playwright timed out waiting for body text")

    failing_page = FailingPage()
    with pytest.raises(RuntimeError) as exc_info:
        google.assert_google(failing_page)

    assert "Failed to inspect Google page content" in str(exc_info.value)


def test_human_intervention_preserves_page_without_closing():
    google = load_module("google_test_preserve", COLLECTOR)
    context = FakeContext(pages=[])

    with pytest.raises(google.HumanInterventionRequired):
        with google.worker_page_context(context) as page:
            page.url = "https://www.google.com/sorry/index"
            google.assert_google(page)

    # MUST NOT BE CLOSED (现场保留)
    assert not page.closed


def test_page_leak_guard_triggers_above_threshold():
    google = load_module("google_test_guard", COLLECTOR)
    overflow_pages = [FakePage(f"https://www.google.com/{i}") for i in range(7)]
    context = FakeContext(pages=overflow_pages)

    with pytest.raises(RuntimeError) as exc_info:
        google.check_page_leak_guard(context, max_pages=5)

    msg = str(exc_info.value)
    assert "BLOCKED: browser_page_leak" in msg
    assert "page count 7 exceeds limit 5" in msg


class FakeTrendsResponse:
    def __init__(self, url, text_content, status=200):
        self.url = url
        self._text = text_content
        self.status = status

    def text(self):
        return self._text


class FakeTrendsPage(FakePage):
    def __init__(self, mode="related"):
        super().__init__("https://trends.google.com/trends/explore")
        self.mode = mode
        self.handlers_seen = []

    def goto(self, url, wait_until="domcontentloaded"):
        self.url = url
        if self.mode == "related":
            payload_data = {"default": {"rankedList": [{"rankedKeyword": [{"query": "subquery", "value": 100}]}]}}
            resp = FakeTrendsResponse(
                "https://trends.google.com/trends/api/widgetdata/relatedsearches?req=1",
                ")]}'\n" + json.dumps(payload_data),
            )
        else:
            payload_data = {"default": {"timelineData": [{"time": "1700000000", "value": [50]}, {"time": "1700086400", "value": [60]}]}}
            resp = FakeTrendsResponse(
                "https://trends.google.com/trends/api/widgetdata/timeline?req=1",
                ")]}'\n" + json.dumps(payload_data),
            )
        # Emit to currently registered listeners
        active_handlers = list(self.listeners.get("response", []))
        for handler in active_handlers:
            if handler not in self.handlers_seen:
                self.handlers_seen.append(handler)
            handler(resp)

    def wait_for_timeout(self, ms):
        pass

    def inner_text(self, timeout=5000):
        return "related Interest over time 关联 热度随时间变化"


def test_trends_related_removes_listener_and_isolates_callbacks(monkeypatch, tmp_path):
    google = load_module("google_test_listener_related", COLLECTOR)
    monkeypatch.setattr(google, "screenshot", lambda page, evidence_dir, name: str(tmp_path / name))

    fake_page = FakeTrendsPage(mode="related")
    context = FakeContext(pages=[fake_page])

    # Run 50 iterations on the same persistent page
    for i in range(50):
        res = google.trends_related(context, f"keyword-{i}", "US", "today 12-m", str(tmp_path))
        assert res["anchor"] == f"keyword-{i}"
        # Assert listeners on the page are strictly 0 after each call
        assert len(fake_page.listeners.get("response", [])) == 0

    # Total registered handlers across 50 calls should be 50 distinct handlers
    assert len(fake_page.handlers_seen) == 50

    # Ensure no leftover callback fires when another response arrives afterwards
    unrelated_resp = FakeTrendsResponse(
        "https://trends.google.com/trends/api/widgetdata/relatedsearches?req=unrelated",
        ")]}'\n" + json.dumps({"default": {"rankedList": []}}),
    )
    # Active listeners count must remain 0
    assert len(fake_page.listeners.get("response", [])) == 0
    for handler in list(fake_page.listeners.get("response", [])):
        handler(unrelated_resp)


def test_trends_timeline_removes_listener_and_isolates_callbacks(monkeypatch, tmp_path):
    google = load_module("google_test_listener_timeline", COLLECTOR)
    monkeypatch.setattr(google, "screenshot", lambda page, evidence_dir, name: str(tmp_path / name))

    fake_page = FakeTrendsPage(mode="timeline")
    context = FakeContext(pages=[fake_page])

    # Run 50 iterations on the same persistent page
    for i in range(50):
        res = google.trends_timeline(context, f"keyword-{i}", "US", "today 12-m", str(tmp_path))
        assert res["keyword"] == f"keyword-{i}"
        # Assert listeners on the page are strictly 0 after each call
        assert len(fake_page.listeners.get("response", [])) == 0

    assert len(fake_page.handlers_seen) == 50
    assert len(fake_page.listeners.get("response", [])) == 0


def test_radar_related_discovery_aborts_immediately_on_needs_human():
    radar_discovery = load_module("radar_discovery_e2e_test", RADAR_DISCOVERY)
    HumanInterventionRequired = radar_discovery.HumanInterventionRequired

    anchors = [
        {"keyword": "anchor1", "discovery_depth": 0},
        {"keyword": "anchor2", "discovery_depth": 0},
        {"keyword": "anchor3", "discovery_depth": 0},
    ]
    executed = []

    def mock_fetcher(keyword):
        executed.append(keyword)
        if keyword == "anchor1":
            raise HumanInterventionRequired("CAPTCHA on anchor1")
        return {"related_queries": []}

    with pytest.raises(HumanInterventionRequired) as exc_info:
        radar_discovery.discover_rising_bfs("example.com", anchors, mock_fetcher)

    assert "CAPTCHA on anchor1" in str(exc_info.value)
    # Critical assertion: anchor2 and anchor3 MUST NOT BE EXECUTED
    assert executed == ["anchor1"]


def test_radar_autocomplete_supplemental_aborts_immediately_on_needs_human():
    radar = load_module("radar_ac_e2e_test", RADAR)
    HumanInterventionRequired = radar.HumanInterventionRequired

    anchors = [
        {"keyword": "anchor1", "anchor_source": "explicit", "discovery_depth": 0, "parent_anchor": None, "root_id": None, "root_status": None, "root_verified": False},
        {"keyword": "anchor2", "anchor_source": "explicit", "discovery_depth": 0, "parent_anchor": None, "root_id": None, "root_status": None, "root_verified": False},
    ]

    def mock_related_fetcher(keyword):
        return {"related_queries": []}

    executed_ac = []

    def mock_ac_fetcher(keyword):
        executed_ac.append(keyword)
        if keyword == "example.com":
            raise HumanInterventionRequired("CAPTCHA on autocomplete anchor1")
        return {"suggestions": []}

    with pytest.raises(HumanInterventionRequired) as exc_info:
        radar.run_pipeline(
            mock_related_fetcher,
            autocomplete_fetcher=mock_ac_fetcher,
            domain="example.com",
            explicit_anchors=["anchor1", "anchor2"],
        )

    assert "CAPTCHA on autocomplete anchor1" in str(exc_info.value)
    # Critical assertion: subsequent anchors MUST NOT BE EXECUTED
    assert executed_ac == ["example.com"]


def test_radar_timeline_aborts_immediately_on_needs_human():
    radar = load_module("radar_tl_e2e_test", RADAR)
    HumanInterventionRequired = radar.HumanInterventionRequired

    candidates = [
        {"keyword": "kw1", "domain": "example.com"},
        {"keyword": "kw2", "domain": "example.com"},
    ]
    executed_tl = []

    def mock_timeline_fetcher(keyword, timeframe):
        executed_tl.append((keyword, timeframe))
        raise HumanInterventionRequired("CAPTCHA on timeline")

    blockers = []
    with pytest.raises(HumanInterventionRequired) as exc_info:
        radar._timeline_observations(
            candidates,
            mock_timeline_fetcher,
            timeframe_specs=(("5y", "today 5-y"), ("12m", "today 12-m")),
            throttle=None,
            blockers=blockers,
        )

    assert "CAPTCHA on timeline" in str(exc_info.value)
    # Critical assertion: only the first call was attempted, subsequent calls aborted
    assert len(executed_tl) == 1
    assert executed_tl[0] == ("kw1", "today 5-y")


def test_radar_main_returns_exit_3_on_needs_human(monkeypatch):
    radar = load_module("radar_main_e2e_test", RADAR)
    HumanInterventionRequired = radar.HumanInterventionRequired

    def fake_live_runner(args):
        raise HumanInterventionRequired("Google CAPTCHA requires human intervention")

    monkeypatch.setattr(radar, "_live_runner", fake_live_runner)
    monkeypatch.setattr(sys, "argv", ["run_emerging_radar.py", "--domain", "example.com"])

    exit_code = radar.main()
    assert exit_code == 3


def test_launcher_only_terminates_dedicated_process(monkeypatch):
    launcher = load_module("launcher_test_terminate", LAUNCHER)
    fake_ps = """
 1001 /Applications/Google Chrome.app/Contents/MacOS/Google Chrome
 1002 /Applications/Google Chrome.app/Contents/MacOS/Google Chrome --remote-debugging-port=9224 --user-data-dir=/Users/test/.seo-run/google-profile --no-first-run
 1003 /Applications/Google Chrome.app/Contents/MacOS/Google Chrome --remote-debugging-port=9999 --user-data-dir=/Users/test/other-profile
"""
    class FakeCompletedProcess:
        stdout = fake_ps
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: FakeCompletedProcess())

    pids = launcher.find_dedicated_pids(9224, "/Users/test/.seo-run/google-profile")
    assert pids == [1002]

