"""Tests for browser background lifecycle, worker page reuse, and NEEDS_HUMAN control signal."""

import importlib.util
import json
import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COLLECTOR = ROOT / "runtime" / "collectors" / "google_live_collector.py"
LAUNCHER = ROOT / "runtime" / "start_live_browser.py"
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

    def close(self):
        self.closed = True

    def locator(self, selector):
        return self

    def inner_text(self, timeout=5000):
        return "Normal search result text"


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


def test_worker_page_bypasses_blocker_page_and_creates_worker():
    google = load_module("google_test_blocker_bypass", COLLECTOR)
    captcha_page = FakeCaptchaPage()
    context = FakeContext(pages=[captcha_page])

    with google.worker_page_context(context) as page:
        assert page is not captcha_page
        assert len(context.pages) == 2

    # Since it was a temporary new page and context had multiple pages, verify cleanup
    assert page.closed
    assert not captcha_page.closed


def test_assert_google_raises_human_intervention_on_captcha():
    google = load_module("google_test_captcha", COLLECTOR)
    captcha_page = FakeCaptchaPage()

    with pytest.raises(google.HumanInterventionRequired) as exc_info:
        google.assert_google(captcha_page)

    assert "CAPTCHA" in str(exc_info.value)
    assert exc_info.value.blocker_type == "unusual_traffic_captcha"
    assert "sorry" in exc_info.value.url


def test_human_intervention_preserves_page_without_closing():
    google = load_module("google_test_preserve", COLLECTOR)
    context = FakeContext(pages=[])

    with pytest.raises(google.HumanInterventionRequired):
        with google.worker_page_context(context) as page:
            page.url = "https://www.google.com/sorry/index"
            google.assert_google(page)

    # MUST NOT BE CLOSED (現場保留)
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


def test_radar_stops_immediately_on_needs_human_and_aborts_batch(monkeypatch, tmp_path):
    radar = load_module("radar_test_needs_human", RADAR)
    mock_collector = tmp_path / "mock_collector.py"
    mock_collector.write_text(
        """
import sys
import json
print("NEEDS_HUMAN: Please complete captcha", file=sys.stderr)
sys.exit(3)
"""
    )
    dummy_output = tmp_path / "output.json"

    with pytest.raises(radar.HumanInterventionRequired) as exc_info:
        radar._collector_payload(["python3", str(mock_collector)], dummy_output)

    assert "NEEDS_HUMAN" in str(exc_info.value)


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
