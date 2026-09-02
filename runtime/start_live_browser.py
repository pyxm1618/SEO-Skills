#!/usr/bin/env python3
"""Start or safely reuse the project's visible, persistent Chrome CDP session."""

import argparse
import json
import socket
import subprocess
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = ROOT / ".seo-run" / "browser-profile"
GOOGLE_PROFILE = ROOT / ".seo-run" / "google-profile"
DEFAULT_PORT = 9223
DEFAULT_GOOGLE_PORT = 9224
DEFAULT_WAIT_SECONDS = 20.0
CHROME_CANDIDATES = (
    Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    Path("/Applications/Google Chrome Beta.app/Contents/MacOS/Google Chrome Beta"),
)
LOGIN_URL = "https://sem.3ue.com/"
GOOGLE_START_URL = "https://www.google.com/ncr"


def chrome_command(port, profile, binary, start_url=LOGIN_URL):
    return [
        str(binary),
        "--remote-debugging-address=127.0.0.1",
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile}",
        "--no-first-run",
        "--no-default-browser-check",
        start_url,
    ]


def _validate_port(port):
    if not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError(f"CDP port must be between 1 and 65535: {port}")


def _cdp_version_url(port):
    return f"http://127.0.0.1:{port}/json/version"


def read_cdp_version(port):
    _validate_port(port)
    try:
        with urlopen(_cdp_version_url(port), timeout=0.5) as response:
            payload = json.load(response)
    except (OSError, URLError, ValueError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) and payload.get("Browser") else None


def port_is_free(port):
    _validate_port(port)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def dedicated_process_matches(port, expected_profile):
    profile_flag = f"--user-data-dir={Path(expected_profile).expanduser().resolve()}"
    port_flag = f"--remote-debugging-port={port}"
    result = subprocess.run(
        ["ps", "-axo", "command="],
        capture_output=True,
        text=True,
        check=False,
    )
    for command_line in result.stdout.splitlines():
        if (
            port_flag in command_line
            and profile_flag in command_line
            and "Chrome" in command_line
        ):
            return True
    return False


def start_chrome(port, profile, binary, start_url=LOGIN_URL):
    Path(profile).mkdir(parents=True, exist_ok=True)
    return subprocess.Popen(
        chrome_command(port, profile, binary, start_url),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def wait_for_cdp(port, timeout):
    deadline = time.monotonic() + timeout
    while True:
        version = read_cdp_version(port)
        if version is not None:
            return version
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError(f"Chrome CDP endpoint did not become available on 127.0.0.1:{port}")
        time.sleep(min(0.2, remaining))


def ensure_browser(port, profile, binary, wait_seconds=DEFAULT_WAIT_SECONDS, start_url=LOGIN_URL):
    _validate_port(port)
    existing = read_cdp_version(port)
    if existing is not None:
        if dedicated_process_matches(port, profile):
            return "reused"
        raise RuntimeError(
            f"CDP port {port} is already served by an unknown process; refusing to reuse or replace it"
        )
    if not port_is_free(port):
        raise RuntimeError(f"CDP port {port} is occupied; refusing to kill an unknown process")

    process = start_chrome(port, profile, binary, start_url)
    try:
        wait_for_cdp(port, wait_seconds)
    except Exception:
        process.terminate()
        raise
    return "started"


def find_chrome():
    for candidate in CHROME_CANDIDATES:
        if candidate.is_file():
            return str(candidate)
    raise RuntimeError("macOS Google Chrome executable was not found")


def main():
    parser = argparse.ArgumentParser(
        description="Start or safely reuse a project Chrome CDP session."
    )
    parser.add_argument("--port", type=int)
    parser.add_argument("--wait-seconds", type=float, default=DEFAULT_WAIT_SECONDS)
    parser.add_argument(
        "--google",
        action="store_true",
        help=(
            "Start the dedicated Google browser instead of the relay browser: a separate "
            "port and profile, exported as SEO_GOOGLE_CDP_URL. The Google collector then "
            "reuses that persistent logged-out profile rather than building a cookieless "
            "context per run, which Google's bot detection flags immediately."
        ),
    )
    args = parser.parse_args()

    if args.google:
        port = args.port if args.port is not None else DEFAULT_GOOGLE_PORT
        profile, start_url, variable = GOOGLE_PROFILE, GOOGLE_START_URL, "SEO_GOOGLE_CDP_URL"
    else:
        port = args.port if args.port is not None else DEFAULT_PORT
        profile, start_url, variable = DEFAULT_PROFILE, LOGIN_URL, "SEO_BROWSER_CDP_URL"

    try:
        status = ensure_browser(port, profile, find_chrome(), args.wait_seconds, start_url)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"BLOCKED: {exc}")
        return 2
    print(f"export {variable}=http://127.0.0.1:{port}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
