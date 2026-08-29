#!/usr/bin/env python3
"""Live Google collectors using an existing browser session over CDP.

Requires SEO_BROWSER_CDP_URL and Playwright in the live Codex environment.
No HTTP/search API fallback is implemented by design.
"""

import argparse
import importlib.util
import json
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus, urljoin, urlparse

BINDING_PATH = Path(__file__).resolve().parents[1] / "evidence_binding.py"


def _binding():
    spec = importlib.util.spec_from_file_location("seo_evidence_binding_for_google", BINDING_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def now():
    return datetime.now(timezone.utc).isoformat()


def playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is required for live collectors; no fallback is allowed") from exc
    return sync_playwright


def connect():
    cdp = os.environ.get("SEO_BROWSER_CDP_URL")
    if not cdp:
        raise RuntimeError("SEO_BROWSER_CDP_URL is required; no hosted WebSearch fallback is allowed")
    pw = playwright()().start()
    browser = pw.chromium.connect_over_cdp(cdp)
    if not browser.contexts:
        raise RuntimeError("No browser context available")
    return pw, browser, browser.contexts[0]


def _google_url(value):
    parsed = urlparse(str(value or ""))
    return parsed.scheme in {"http", "https"} and parsed.hostname in {"google.com", "www.google.com"}


def assert_google(page):
    parsed = urlparse(page.url)
    host = (parsed.hostname or "").lower()
    if not _google_url(page.url):
        raise RuntimeError(f"wrong Google origin: {host}")
    text = page.locator("body").inner_text(timeout=5000).lower()
    if "unusual traffic" in text or "captcha" in text:
        raise RuntimeError("Google CAPTCHA/unusual-traffic page detected")


def screenshot(page, evidence_dir, name):
    evidence_dir = Path(evidence_dir)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    path = evidence_dir / name
    page.screenshot(path=str(path), full_page=False)
    return str(path)


def evidence_json(evidence_dir, name, payload):
    evidence_dir = Path(evidence_dir)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    path = evidence_dir / name
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return str(path)


def autocomplete(context, seed, country, language, evidence_dir):
    page = context.new_page()
    page.goto(f"https://www.google.com/search?hl={quote_plus(language)}&gl={quote_plus(country)}", wait_until="domcontentloaded")
    assert_google(page)
    box = page.locator('textarea[name="q"], input[name="q"]').first
    if not box.is_visible():
        raise RuntimeError("Google search input unavailable")
    box.fill(seed)
    page.wait_for_timeout(1200)
    selectors = ['[role="option"]', 'ul[role="listbox"] li']
    values = []
    for selector in selectors:
        for node in page.locator(selector).all():
            try:
                if node.is_visible():
                    text = " ".join(node.inner_text().split()).strip()
                    if text and text not in values:
                        values.append(text)
            except Exception:
                continue
        if values:
            break
    if not values:
        raise RuntimeError("Google visible autocomplete dropdown unavailable or returned 0 suggestions")
    observed_at = now()
    evidence = screenshot(page, evidence_dir, f"autocomplete-{re.sub(r'[^a-zA-Z0-9]+','-',seed).strip('-')}.png")
    observation = evidence_json(
        evidence_dir,
        f"autocomplete-{re.sub(r'[^a-zA-Z0-9]+','-',seed).strip('-')}.json",
        {"page_url": page.url, "seed": seed, "suggestions": values, "country": country, "language": language, "observed_at": observed_at},
    )
    return {
        "seed": seed,
        "suggestions": values,
        "country": country,
        "language": language,
        "observed_at": observed_at,
        "source": "google_autocomplete",
        "evidence_ref": evidence,
        "observation_ref": observation,
    }


def intitle(context, keyword, market, evidence_dir):
    page = context.new_page()
    query = f'intitle:"{keyword}"'
    page.goto(f"https://www.google.com/search?q={quote_plus(query)}&gl={quote_plus(market)}", wait_until="domcontentloaded")
    assert_google(page)
    stats = page.locator("#result-stats")
    # Google can keep #result-stats in the DOM while Playwright reports the node
    # as not visible. The text is still part of the current loaded result page and
    # is recorded together with screenshot + structured observation evidence.
    if not stats.count():
        page.wait_for_selector("#result-stats", state="attached", timeout=10000)
    text = stats.first.inner_text().strip() if stats.count() else ""
    numbers = re.findall(r"\d[\d,\.\s]*", text)
    if not numbers:
        raise RuntimeError("Google intitle result count unavailable")
    digits = re.sub(r"\D", "", numbers[0])
    if not digits:
        raise RuntimeError("Google intitle result count could not be parsed")
    observed_at = now()
    evidence = screenshot(page, evidence_dir, f"intitle-{re.sub(r'[^a-zA-Z0-9]+','-',keyword).strip('-')}.png")
    observation = evidence_json(
        evidence_dir,
        f"intitle-{re.sub(r'[^a-zA-Z0-9]+','-',keyword).strip('-')}.json",
        {"page_url": page.url, "query": query, "result_stats_text": text, "intitle_results": int(digits), "market": market, "observed_at": observed_at},
    )
    return {
        "keyword": keyword,
        "intitle_results": int(digits),
        "source": "Google",
        "market": market,
        "observed_at": observed_at,
        "evidence_ref": evidence,
        "observation_ref": observation,
    }


def _organic_rows(page, seen):
    rows = []
    try:
        headings = page.locator("#search h3").all()
    except Exception:
        return rows
    # Walk result headings first. Google has used both <a><h3> and <h3><a>
    # shapes, so resolve either an ancestor link or a child link from each h3.
    for h3 in headings:
        try:
            if not h3.is_visible():
                continue
            anchor = h3.locator("xpath=ancestor::a[1]")
            if not anchor.count():
                anchor = h3.locator("a")
            if not anchor.count():
                continue
            anchor = anchor.first
            url = _resolve_result_url(page, anchor.get_attribute("href") or "")
            if not url or url in seen:
                continue
            title = h3.inner_text().strip()
            if not title:
                continue
            seen.add(url)
            rows.append({"url": url, "title": title})
        except Exception:
            continue
    return rows


def _google_or_http_url(value):
    parsed = urlparse(str(value or ""))
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _resolve_result_url(page, href):
    if _google_or_http_url(href):
        return href
    resolved = urljoin(page.url, href)
    if not _google_url(resolved):
        return ""
    request_context = getattr(getattr(page, "context", None), "request", None)
    if request_context is None:
        return ""
    try:
        response = request_context.get(resolved, timeout=10000, fail_on_status_code=False)
        try:
            final_url = response.url
        finally:
            response.dispose()
    except Exception:
        return ""
    if not _google_or_http_url(final_url) or _google_url(final_url):
        return ""
    return final_url


def _wait_for_serp_headings(page):
    headings = page.locator("#search h3")
    if not headings.all():
        page.wait_for_selector("#search h3", state="attached", timeout=10000)


def _next_page_url(page):
    selectors = ("a#pnnext", "a[aria-label='Next']", "a[aria-label*='Next']", "#search a", "a")
    for selector in selectors:
        try:
            anchors = page.locator(selector).all()
        except Exception:
            continue
        for anchor in anchors:
            try:
                if not anchor.is_visible():
                    continue
                href = anchor.get_attribute("href") or ""
                if not href:
                    continue
                label = " ".join(
                    filter(
                        None,
                        [
                            str(anchor.get_attribute("aria-label") or "").strip(),
                            str(anchor.inner_text() or "").strip(),
                        ],
                    )
                ).casefold()
                if selector not in {"a#pnnext", "a[aria-label='Next']", "a[aria-label*='Next']"} and "next" not in label and "下一页" not in label:
                    continue
                next_url = urljoin(page.url, href)
                if not _google_url(next_url):
                    raise RuntimeError(f"Google next page link leaves google.com: {next_url}")
                return next_url
            except RuntimeError:
                raise
            except Exception:
                continue
    return None


def serp(context, keyword, market, evidence_dir):
    page = context.new_page()
    page.goto(f"https://www.google.com/search?q={quote_plus(keyword)}&gl={quote_plus(market)}&num=10", wait_until="domcontentloaded")
    assert_google(page)
    _wait_for_serp_headings(page)
    rows = []
    seen = set()
    page_urls = [page.url]
    first_page_screenshot = screenshot(
        page, evidence_dir, f"serp-{re.sub(r'[^a-zA-Z0-9]+','-',keyword).strip('-')}.png"
    )
    max_pages = 5
    while len(rows) < 10 and len(page_urls) <= max_pages:
        for item in _organic_rows(page, seen):
            rows.append({"rank": len(rows) + 1, **item})
            if len(rows) == 10:
                break
        if len(rows) == 10:
            break
        next_url = _next_page_url(page)
        if not next_url or next_url in page_urls:
            break
        page.goto(next_url, wait_until="domcontentloaded")
        assert_google(page)
        _wait_for_serp_headings(page)
        page_urls.append(page.url)
    if len(rows) < 10:
        raise RuntimeError(f"Google real SERP collector found only {len(rows)} organic results; top 10 contract not met")
    observed_at = now()
    observation = evidence_json(
        evidence_dir,
        f"serp-{re.sub(r'[^a-zA-Z0-9]+','-',keyword).strip('-')}.json",
        {
            "page_url": page_urls[-1],
            "page_urls": page_urls,
            "keyword": keyword,
            "market": market,
            "observed_at": observed_at,
            "results": rows,
        },
    )
    return {
        "keyword": keyword,
        "source": "Google",
        "market": market,
        "observed_at": observed_at,
        "evidence_ref": first_page_screenshot,
        "observation_ref": observation,
        "page_urls": page_urls,
        "results": rows,
    }


def _decode_trends_payload(text):
    text = str(text or "").lstrip()
    if text.startswith(")]}'"):
        newline = text.find("\n")
        text = text[newline + 1:] if newline >= 0 else text[4:]
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Google Trends temporal response is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Google Trends temporal response is not a JSON object")
    return payload


def _trend_value(value, index):
    if isinstance(value, list):
        if not value:
            raise RuntimeError(f"Google Trends timeline row {index} has empty value")
        value = value[0]
    if isinstance(value, bool):
        raise RuntimeError(f"Google Trends timeline row {index} has invalid value")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"Google Trends timeline row {index} has invalid value") from exc
    if not math.isfinite(number) or number < 0:
        raise RuntimeError(f"Google Trends timeline row {index} has invalid value")
    return int(number) if number.is_integer() else number


def parse_trends_timeline(payload):
    default = payload.get("default") if isinstance(payload, dict) else None
    timeline = default.get("timelineData") if isinstance(default, dict) else None
    if not isinstance(timeline, list) or len(timeline) < 2:
        raise RuntimeError("Google Trends temporal payload missing timelineData")
    series = []
    for index, row in enumerate(timeline):
        if not isinstance(row, dict) or row.get("time") in (None, "") or "value" not in row:
            raise RuntimeError(f"Google Trends timeline row {index} is incomplete")
        point = {"time": str(row["time"]), "value": _trend_value(row["value"], index)}
        if row.get("formattedTime") not in (None, ""):
            point["formatted_time"] = str(row["formattedTime"])
        series.append(point)
    return series


def trends(context, keyword, market, evidence_dir):
    page = context.new_page()
    observed_payloads = []

    def capture_temporal_response(response):
        try:
            parsed = urlparse(response.url)
            if parsed.hostname != "trends.google.com" or "/trends/api/widgetdata" not in parsed.path:
                return
            if response.status != 200:
                return
            payload = _decode_trends_payload(response.text())
            series = parse_trends_timeline(payload)
            observed_payloads.append({"url": response.url, "payload": payload, "series": series})
        except Exception:
            return

    page.on("response", capture_temporal_response)
    page.goto(f"https://trends.google.com/trends/explore?geo={quote_plus(market)}&q={quote_plus(keyword)}", wait_until="domcontentloaded")
    page.wait_for_timeout(5000)
    host = page.url.split("/", 3)[2].lower() if page.url.startswith("http") else ""
    if host != "trends.google.com":
        raise RuntimeError(f"wrong Google Trends origin: {host}")
    body = page.locator("body").inner_text(timeout=5000)
    if "Interest over time" not in body and "热度随时间变化" not in body:
        raise RuntimeError("Google Trends current result could not be confirmed")
    if not observed_payloads:
        raise RuntimeError("Google Trends real temporal payload was not observed; screenshot-only evidence is insufficient")

    captured = observed_payloads[-1]
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", keyword).strip("-")
    observed_at = now()
    raw_evidence = evidence_json(
        evidence_dir,
        f"trends-{slug}.json",
        {
            "keyword": keyword,
            "market": market,
            "observed_at": observed_at,
            "source_url": captured["url"],
            "payload": captured["payload"],
            "series": captured["series"],
        },
    )
    screenshot_ref = screenshot(page, evidence_dir, f"trends-{slug}.png")
    return {
        "keyword": keyword,
        "is_finalist": True,
        "google_trends_source": "Google Trends",
        "google_trends_market": market,
        "google_trends_observed_at": observed_at,
        "google_trends_evidence_ref": raw_evidence,
        "google_trends_screenshot_ref": screenshot_ref,
        "google_trends_series": captured["series"],
    }


def _artifacts_for(mode, result):
    if mode == "trends":
        return [
            {"path": result["google_trends_evidence_ref"], "role": "temporal_payload"},
            {"path": result["google_trends_screenshot_ref"], "role": "screenshot"},
        ]
    artifacts = [{"path": result["evidence_ref"], "role": "screenshot"}]
    if result.get("observation_ref"):
        artifacts.append({"path": result["observation_ref"], "role": "structured_observation"})
    return artifacts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["autocomplete", "intitle", "serp", "trends"])
    parser.add_argument("--keyword")
    parser.add_argument("--seed")
    parser.add_argument("--country", default="US")
    parser.add_argument("--language", default="en")
    parser.add_argument("--market", default="US")
    parser.add_argument("--evidence-dir", default=".seo-run/evidence")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    pw = browser = None
    try:
        pw, browser, context = connect()
        if args.mode == "autocomplete":
            if not args.seed:
                raise RuntimeError("--seed is required")
            result = autocomplete(context, args.seed, args.country, args.language, args.evidence_dir)
        else:
            if not args.keyword:
                raise RuntimeError("--keyword is required")
            if args.mode == "intitle":
                result = intitle(context, args.keyword, args.market, args.evidence_dir)
            elif args.mode == "serp":
                result = serp(context, args.keyword, args.market, args.evidence_dir)
            else:
                result = trends(context, args.keyword, args.market, args.evidence_dir)
        output = Path(args.output)
        evidence_type = {
            "autocomplete": "google_autocomplete",
            "intitle": "google_intitle",
            "serp": "google_serp",
            "trends": "google_trends",
        }[args.mode]
        result = _binding().write_observed_output(
            output,
            result,
            "google_live_collector",
            evidence_type,
            _artifacts_for(args.mode, result),
        )
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
