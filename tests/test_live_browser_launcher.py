import importlib.util

import pytest

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "runtime" / "start_live_browser.py"


def load_launcher(name="live_browser_launcher"):
    spec = importlib.util.spec_from_file_location(name, LAUNCHER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_chrome_command_uses_visible_loopback_persistent_profile(tmp_path):
    launcher = load_launcher("launcher_command")
    profile = tmp_path / ".seo-run" / "browser-profile"

    command = launcher.chrome_command(9223, profile, "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")

    assert command == [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "--remote-debugging-address=127.0.0.1",
        "--remote-debugging-port=9223",
        f"--user-data-dir={profile}",
        "--no-first-run",
        "--no-default-browser-check",
        "https://sem.3ue.com/",
    ]
    assert not any(argument == "--headless" or argument.startswith("--headless=") for argument in command)


def test_launcher_reuses_only_a_matching_dedicated_chrome(monkeypatch, tmp_path):
    launcher = load_launcher("launcher_reuse")
    profile = tmp_path / "browser-profile"
    monkeypatch.setattr(launcher, "read_cdp_version", lambda port: {"Browser": "Chrome/151"})
    monkeypatch.setattr(launcher, "dedicated_process_matches", lambda port, expected_profile: True)

    result = launcher.ensure_browser(9223, profile, "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")

    assert result == "reused"


def test_launcher_refuses_an_unknown_process_on_the_cdp_port(monkeypatch, tmp_path):
    launcher = load_launcher("launcher_unknown_process")
    profile = tmp_path / "browser-profile"
    monkeypatch.setattr(launcher, "read_cdp_version", lambda port: {"Browser": "unknown"})
    monkeypatch.setattr(launcher, "dedicated_process_matches", lambda port, expected_profile: False)

    with pytest.raises(RuntimeError, match="unknown process"):
        launcher.ensure_browser(9223, profile, "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


def test_launcher_starts_then_waits_for_cdp(monkeypatch, tmp_path):
    launcher = load_launcher("launcher_start")
    profile = tmp_path / "browser-profile"
    process = object()
    monkeypatch.setattr(launcher, "read_cdp_version", lambda port: None)
    monkeypatch.setattr(launcher, "port_is_free", lambda port: True)
    monkeypatch.setattr(launcher, "start_chrome", lambda port, expected_profile, binary: process)
    monkeypatch.setattr(launcher, "wait_for_cdp", lambda port, timeout: {"Browser": "Chrome/151"})

    result = launcher.ensure_browser(9223, profile, "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")

    assert result == "started"
