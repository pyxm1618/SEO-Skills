#!/usr/bin/env python3
"""Live Semrush acquisition through the current authenticated sem.3ue.com session.

The collector intentionally has no hard-coded Semrush endpoint and no official
API fallback. A request descriptor must come from a current live same-origin
network capture and is revalidated before use.
"""

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


ALLOWED_HOST = "sem.3ue.com"


def now():
    return datetime.now(timezone.utc).isoformat()


def playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is required for live relay collection; no provider fallback is allowed") from exc
    return sync_playwright


def load_request(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    required = ["path", "method", "body", "capture_observed_at", "capture_evidence_ref"]
    missing = [field for field in required if field not in data or data[field] in (None, "")]
    if missing:
        raise RuntimeError(f"live relay request descriptor incomplete: {', '.join(missing)}")
    parsed = urlparse(data["path"] if "://" in data["path"] else f"https://{ALLOWED_HOST}{data['path']}")
    if parsed.hostname != ALLOWED_HOST:
        raise RuntimeError(f"relay request host must be {ALLOWED_HOST}")
    return data


def connect_same_origin():
    cdp = os.environ.get("SEO_BROWSER_CDP_URL")
    if not cdp:
        raise RuntimeError("SEO_BROWSER_CDP_URL is required")
    pw = playwright()().start()
    browser = pw.chromium.connect_over_cdp(cdp)
    if not browser.contexts:
        raise RuntimeError("No browser context available")
    context = browser.contexts[0]
    page = next((p for p in context.pages if urlparse(p.url).hostname == ALLOWED_HOST), None)
    if page is None:
        page = context.new_page()
        page.goto(f"https://{ALLOWED_HOST}/", wait_until="domcontentloaded")
    if urlparse(page.url).hostname != ALLOWED_HOST:
        raise RuntimeError("authenticated same-origin relay page unavailable")
    return pw, browser, page


def collect(page, descriptor):
    path = descriptor["path"]
    if path.startswith("http"):
        parsed = urlparse(path)
        if parsed.hostname != ALLOWED_HOST:
            raise RuntimeError("cross-origin relay request prohibited")
        request_url = path
    else:
        request_url = path if path.startswith("/") else f"/{path}"

    result = page.evaluate(
        """async ({url, method, body}) => {
          if (location.hostname !== 'sem.3ue.com') throw new Error('wrong origin');
          const res = await fetch(url, {
            method,
            credentials: 'include',
            headers: {'content-type': 'application/json'},
            body: method.toUpperCase() === 'GET' ? undefined : JSON.stringify(body)
          });
          const text = await res.text();
          let data;
          try { data = JSON.parse(text); } catch { throw new Error('relay response is not JSON'); }
          return {ok: res.ok, status: res.status, data};
        }""",
        {"url": request_url, "method": descriptor["method"], "body": descriptor["body"]},
    )
    if not result.get("ok"):
        raise RuntimeError(f"relay HTTP/RPC failed with status {result.get('status')}")
    data = result.get("data")
    if not isinstance(data, (dict, list)):
        raise RuntimeError("relay response schema is not a JSON object/array")
    for key in descriptor.get("required_top_level_keys", []):
        if not isinstance(data, dict) or key not in data:
            raise RuntimeError(f"relay response schema missing required key: {key}")
    return {
        "metric_source": "Semrush",
        "relay_origin": f"https://{ALLOWED_HOST}/",
        "observed_at": now(),
        "capture_observed_at": descriptor["capture_observed_at"],
        "capture_evidence_ref": descriptor["capture_evidence_ref"],
        "request_method": descriptor["method"],
        "request_path": request_url,
        "response": data,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True, help="descriptor from current live same-origin network capture")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    pw = browser = None
    try:
        descriptor = load_request(args.request)
        pw, browser, page = connect_same_origin()
        result = collect(page, descriptor)
        Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(f"BLOCKED: {exc}", file=os.sys.stderr)
        return 2
    finally:
        if browser is not None:
            browser.close()
        if pw is not None:
            pw.stop()


if __name__ == "__main__":
    raise SystemExit(main())
