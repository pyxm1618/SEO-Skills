#!/usr/bin/env python3
"""Live Google collectors using an existing browser session over CDP.

Requires SEO_BROWSER_CDP_URL and Playwright in the live Codex environment.
No HTTP/search API fallback is implemented by design.
"""

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus


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


def assert_google(page):
    host = page.url.split("/", 3)[2].lower() if page.url.startswith("http") else ""
    if not host.endswith("google.com"):
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
    evidence = screenshot(page, evidence_dir, f"autocomplete-{re.sub(r'[^a-zA-Z0-9]+','-',seed).strip('-')}.png")
    return {
        "seed": seed,
        "suggestions": values,
        "country": country,
        "language": language,
        "observed_at": now(),
        "source": "google_autocomplete",
        "evidence_ref": evidence,
    }


def intitle(context, keyword, market, evidence_dir):
    page = context.new_page()
    query = f'intitle:"{keyword}"'
    page.goto(f"https://www.google.com/search?q={quote_plus(query)}&gl={quote_plus(market)}", wait_until="domcontentloaded")
    assert_google(page)
    stats = page.locator("#result-stats")
    text = stats.inner_text().strip() if stats.count() and stats.first.is_visible() else ""
    numbers = re.findall(r"\d[\d,\.\s]*", text)
    if not numbers:
        raise RuntimeError("Google visible intitle result count unavailable")
    digits = re.sub(r"\D", "", numbers[0])
    if not digits:
        raise RuntimeError("Google intitle result count could not be parsed")
    evidence = screenshot(page, evidence_dir, f"intitle-{re.sub(r'[^a-zA-Z0-9]+','-',keyword).strip('-')}.png")
    return {
        "keyword": keyword,
        "volume": None,
        "intitle_results": int(digits),
        "source": "Google",
        "market": market,
        "observed_at": now(),
        "evidence_ref": evidence,
    }


def serp(context, keyword, market, evidence_dir):
    page = context.new_page()
    page.goto(f"https://www.google.com/search?q={quote_plus(keyword)}&gl={quote_plus(market)}&num=10", wait_until="domcontentloaded")
    assert_google(page)
    rows = []
    seen = set()
    for anchor in page.locator("#search a").all():
        try:
            h3 = anchor.locator("h3")
            if not h3.count() or not h3.first.is_visible():
                continue
            url = anchor.get_attribute("href") or ""
            if not url.startswith("http") or url in seen:
                continue
            seen.add(url)
            rows.append({"rank": len(rows) + 1, "url": url, "title": h3.first.inner_text().strip()})
            if len(rows) == 10:
                break
        except Exception:
            continue
    if len(rows) < 10:
        raise RuntimeError(f"Google real SERP collector found only {len(rows)} organic results; top 10 contract not met")
    evidence = screenshot(page, evidence_dir, f"serp-{re.sub(r'[^a-zA-Z0-9]+','-',keyword).strip('-')}.png")
    return {
        "keyword": keyword,
        "source": "Google",
        "market": market,
        "observed_at": now(),
        "evidence_ref": evidence,
        "results": rows,
    }


def trends(context, keyword, market, evidence_dir):
    page = context.new_page()
    page.goto(f"https://trends.google.com/trends/explore?geo={quote_plus(market)}&q={quote_plus(keyword)}", wait_until="domcontentloaded")
    page.wait_for_timeout(4000)
    host = page.url.split("/", 3)[2].lower() if page.url.startswith("http") else ""
    if host != "trends.google.com":
        raise RuntimeError(f"wrong Google Trends origin: {host}")
    body = page.locator("body").inner_text(timeout=5000)
    if "Interest over time" not in body and "热度随时间变化" not in body:
        raise RuntimeError("Google Trends current result could not be confirmed")
    evidence = screenshot(page, evidence_dir, f"trends-{re.sub(r'[^a-zA-Z0-9]+','-',keyword).strip('-')}.png")
    return {
        "keyword": keyword,
        "is_finalist": True,
        "google_trends_source": "Google Trends",
        "google_trends_observed_at": now(),
        "google_trends_evidence_ref": evidence,
    }


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
