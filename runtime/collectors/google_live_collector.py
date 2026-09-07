#!/usr/bin/env python3
"""Compatibility wrapper that gives legacy Google evidence files collision-safe names."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

LEGACY_PATH = Path(__file__).resolve().with_name("google_live_collector_legacy.py")


def _load_legacy():
    spec = importlib.util.spec_from_file_location("seo_google_live_collector_legacy", LEGACY_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load Google collector legacy module: {LEGACY_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_legacy = _load_legacy()

for _name in dir(_legacy):
    if not _name.startswith("__") and _name not in globals():
        globals()[_name] = getattr(_legacy, _name)


def autocomplete(context, seed, country, language, evidence_dir):
    page = context.new_page()
    _legacy.goto_google(
        page,
        f"https://www.google.com/search?hl={_legacy.quote_plus(language)}&gl={_legacy.quote_plus(country)}",
    )
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
    observed_at = _legacy.now()
    evidence_key = _legacy._evidence_slug("autocomplete", seed, country, language)
    evidence = _legacy.screenshot(page, evidence_dir, f"{evidence_key}.png")
    observation = _legacy.evidence_json(
        evidence_dir,
        f"{evidence_key}.json",
        {
            "page_url": page.url,
            "seed": seed,
            "suggestions": values,
            "country": country,
            "language": language,
            "observed_at": observed_at,
        },
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
    _legacy.goto_google(
        page,
        f"https://www.google.com/search?q={_legacy.quote_plus(query)}&gl={_legacy.quote_plus(market)}",
    )
    stats = page.locator("#result-stats")
    if not stats.count():
        page.wait_for_selector("#result-stats", state="attached", timeout=10000)
    text = stats.first.inner_text().strip() if stats.count() else ""
    numbers = _legacy.re.findall(r"\d[\d,\.\s]*", text)
    if not numbers:
        raise RuntimeError("Google intitle result count unavailable")
    digits = _legacy.re.sub(r"\D", "", numbers[0])
    if not digits:
        raise RuntimeError("Google intitle result count could not be parsed")
    observed_at = _legacy.now()
    evidence_key = _legacy._evidence_slug("intitle", keyword, market)
    evidence = _legacy.screenshot(page, evidence_dir, f"{evidence_key}.png")
    observation = _legacy.evidence_json(
        evidence_dir,
        f"{evidence_key}.json",
        {
            "page_url": page.url,
            "query": query,
            "result_stats_text": text,
            "intitle_results": int(digits),
            "market": market,
            "observed_at": observed_at,
        },
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


def serp(context, keyword, market, evidence_dir):
    page = context.new_page()
    _legacy.goto_google(
        page,
        f"https://www.google.com/search?q={_legacy.quote_plus(keyword)}&gl={_legacy.quote_plus(market)}&num=10",
    )
    _legacy._wait_for_serp_headings(page)
    rows = []
    seen = set()
    page_urls = [page.url]
    evidence_key = _legacy._evidence_slug("serp", keyword, market)
    first_page_screenshot = _legacy.screenshot(page, evidence_dir, f"{evidence_key}.png")
    max_pages = 5
    while len(rows) < 10 and len(page_urls) <= max_pages:
        for item in _legacy._organic_rows(page, seen):
            rows.append({"rank": len(rows) + 1, **item})
            if len(rows) == 10:
                break
        if len(rows) == 10:
            break
        next_url = _legacy._next_page_url(page)
        if not next_url or next_url in page_urls:
            break
        _legacy.goto_google(page, next_url)
        _legacy._wait_for_serp_headings(page)
        page_urls.append(page.url)
    if len(rows) < 10:
        raise RuntimeError(f"Google real SERP collector found only {len(rows)} organic results; top 10 contract not met")
    observed_at = _legacy.now()
    observation = _legacy.evidence_json(
        evidence_dir,
        f"{evidence_key}.json",
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


# Keep imported callers and direct CLI execution on the same functions.
_legacy.autocomplete = autocomplete
_legacy.intitle = intitle
_legacy.serp = serp


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mode",
        choices=["autocomplete", "expansions", "intitle", "serp", "trends", "trends_timeline", "trends_related"],
    )
    parser.add_argument("--keyword")
    parser.add_argument("--seed")
    parser.add_argument("--country", default="US")
    parser.add_argument("--language", default="en")
    parser.add_argument("--market", default="US")
    parser.add_argument("--timeframe", default="today 12-m")
    parser.add_argument("--evidence-dir", default=".seo-run/evidence")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    pw = browser = None
    try:
        pw, browser, context = _legacy.connect()
        if args.mode == "autocomplete":
            if not args.seed:
                raise RuntimeError("--seed is required")
            result = autocomplete(context, args.seed, args.country, args.language, args.evidence_dir)
        elif args.mode == "expansions":
            if not args.seed:
                raise RuntimeError("--seed is required")
            result = _legacy.expansions(context, args.seed, args.market, args.language, args.evidence_dir)
        else:
            if not args.keyword:
                raise RuntimeError("--keyword is required")
            if args.mode == "intitle":
                result = intitle(context, args.keyword, args.market, args.evidence_dir)
            elif args.mode == "serp":
                result = serp(context, args.keyword, args.market, args.evidence_dir)
            elif args.mode == "trends_related":
                result = _legacy.trends_related(context, args.keyword, args.market, args.timeframe, args.evidence_dir)
            elif args.mode == "trends_timeline":
                result = _legacy.trends_timeline(context, args.keyword, args.market, args.timeframe, args.evidence_dir)
            else:
                result = _legacy.trends(context, args.keyword, args.market, args.evidence_dir)
        output = Path(args.output)
        evidence_type = {
            "autocomplete": "google_autocomplete",
            "expansions": "google_serp_expansions",
            "intitle": "google_intitle",
            "serp": "google_serp",
            "trends": "google_trends",
            "trends_timeline": "google_trends",
            "trends_related": "google_trends_related",
        }[args.mode]
        result = _legacy._binding().write_observed_output(
            output,
            result,
            "google_live_collector",
            evidence_type,
            _legacy._artifacts_for(args.mode, result),
        )
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2
    finally:
        if browser is not None:
            browser.close()
        if pw is not None:
            pw.stop()


if __name__ == "__main__":
    raise SystemExit(main())
