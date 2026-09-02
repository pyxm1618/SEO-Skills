#!/usr/bin/env python3
"""Live Google collectors using an existing browser session over CDP.

Requires SEO_GOOGLE_CDP_URL for a dedicated Google browser/profile, or
SEO_BROWSER_CDP_URL when a clean isolated context can be created safely.
Playwright is required in the live Codex environment.
No HTTP/search API fallback is implemented by design.
"""

import argparse
import hashlib
import importlib.util
import json
import math
import os
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus, urljoin, urlparse

BINDING_PATH = Path(__file__).resolve().parents[1] / "evidence_binding.py"
GOOGLE_AUTH_COOKIE_NAMES = {
    "account_chooser",
    "apisid",
    "hsid",
    "lsid",
    "osid",
    "sapISID".casefold(),
    "sid",
    "ssid",
    "__host-gaps",
    "__secure-1psid",
    "__secure-3psid",
    "__secure-osid",
}


def _binding():
    spec = importlib.util.spec_from_file_location("seo_evidence_binding_for_google", BINDING_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def now():
    return datetime.now(timezone.utc).isoformat()


def _evidence_slug(*values):
    parts = [str(value or "").strip() for value in values]
    identity = "\x1f".join(parts)
    readable = re.sub(r"[^a-zA-Z0-9]+", "-", "-".join(parts)).strip("-").lower()
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
    return f"{readable}-{digest}" if readable else f"item-{digest}"


def playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is required for live collectors; no fallback is allowed") from exc
    return sync_playwright


def connect():
    cdp = os.environ.get("SEO_GOOGLE_CDP_URL") or os.environ.get("SEO_BROWSER_CDP_URL")
    if not cdp:
        raise RuntimeError("SEO_GOOGLE_CDP_URL or SEO_BROWSER_CDP_URL is required; no hosted WebSearch fallback is allowed")
    pw = playwright()().start()
    browser = pw.chromium.connect_over_cdp(cdp)
    if not browser.contexts:
        raise RuntimeError("No browser context available")

    general_cdp = os.environ.get("SEO_BROWSER_CDP_URL")
    dedicated_cdp = os.environ.get("SEO_GOOGLE_CDP_URL")
    if dedicated_cdp and dedicated_cdp != general_cdp:
        context = browser.contexts[0]
    else:
        new_context = getattr(browser, "new_context", None)
        if not callable(new_context):
            raise RuntimeError("Google collector requires an isolated browser context or separate profile")
        context = new_context()

    cookies = context.cookies()
    for cookie in cookies:
        domain = str(cookie.get("domain") or "").casefold()
        name = str(cookie.get("name") or "").casefold()
        if name in GOOGLE_AUTH_COOKIE_NAMES and "google." in domain:
            raise RuntimeError("Google collector context contains authenticated Google cookies; logged-out isolation required")
    return pw, browser, context


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


def goto_google(page, url):
    """Open a google.com URL, defeating the country redirect once if it fires.

    Google redirects google.com to a ccTLD (google.com.hk, google.co.jp, ...)
    based on egress IP. That ccTLD is a different market and a different origin,
    so `assert_google` rejects it and every collection from an affected network
    fails. Visiting `/ncr` (No Country Redirect) records the preference on the
    context; retry the original URL once afterwards. A second redirect is still
    a real BLOCKED condition.
    """
    page.goto(url, wait_until="domcontentloaded")
    if _google_url(page.url):
        assert_google(page)
        return
    page.goto("https://www.google.com/ncr", wait_until="domcontentloaded")
    page.wait_for_timeout(1200)
    page.goto(url, wait_until="domcontentloaded")
    assert_google(page)


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
    goto_google(page, f"https://www.google.com/search?hl={quote_plus(language)}&gl={quote_plus(country)}")
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
    goto_google(page, f"https://www.google.com/search?q={quote_plus(query)}&gl={quote_plus(market)}")
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
    goto_google(page, f"https://www.google.com/search?q={quote_plus(keyword)}&gl={quote_plus(market)}&num=10")
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
        goto_google(page, next_url)
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


def infer_timeline_resolution(series):
    timestamps = []
    for point in series:
        try:
            timestamp = int(str(point["time"]))
        except (KeyError, TypeError, ValueError):
            continue
        timestamps.append(timestamp)
    differences = [right - left for left, right in zip(timestamps, timestamps[1:]) if right > left]
    if not differences:
        return "unknown"
    seconds = sorted(differences)[len(differences) // 2]
    if seconds >= 300 * 24 * 60 * 60:
        return "yearly"
    if seconds >= 25 * 24 * 60 * 60:
        return "monthly"
    if seconds >= 5 * 24 * 60 * 60:
        return "weekly"
    if seconds >= 20 * 60 * 60:
        return "daily"
    return "subdaily"


def _related_group_type(group, index):
    for field in ("relation_type", "title", "name", "type"):
        value = str(group.get(field) or "").strip().lower()
        if "rising" in value:
            return "rising"
        if "top" in value:
            return "top"
    return ("top", "rising")[index] if index < 2 else None


def _related_value(value):
    if isinstance(value, bool) or value is None:
        return None, None
    if isinstance(value, (int, float)):
        number = float(value)
        if math.isfinite(number) and number >= 0:
            return (int(number) if number.is_integer() else number), None
        return None, None
    text = str(value).strip()
    if not text:
        return None, None
    try:
        number = float(text.replace(",", ""))
    except ValueError:
        return None, text
    if not math.isfinite(number) or number < 0:
        return None, text
    return (int(number) if number.is_integer() else number), None


def parse_trends_related(payload):
    default = payload.get("default") if isinstance(payload, dict) else None
    ranked_list = default.get("rankedList") if isinstance(default, dict) else None
    if not isinstance(ranked_list, list):
        raise RuntimeError("Google Trends related response missing rankedList")

    rows = []
    for group_index, group in enumerate(ranked_list):
        if not isinstance(group, dict):
            continue
        relation_type = _related_group_type(group, group_index)
        if relation_type not in {"top", "rising"}:
            continue
        ranked_keywords = group.get("rankedKeyword")
        if not isinstance(ranked_keywords, list):
            continue
        for item in ranked_keywords:
            if not isinstance(item, dict):
                continue
            query = " ".join(str(item.get("query") or "").split()).strip()
            if not query:
                continue
            value, label = _related_value(item.get("value"))
            if value is None and label is None:
                formatted = item.get("formattedValue")
                value, label = _related_value(formatted)
            rows.append(
                {
                    "query": query,
                    "relation_type": relation_type,
                    "rank": len([row for row in rows if row["relation_type"] == relation_type]) + 1,
                    "rising_value": value,
                    "google_rising_label": label,
                    "is_google_breakout": isinstance(label, str) and label.casefold() == "breakout",
                }
            )
    return rows


def _wait_for_related_payload(page, observed_payloads, timeout_seconds=15.0):
    deadline = time.monotonic() + timeout_seconds
    while not observed_payloads and time.monotonic() < deadline:
        page.wait_for_timeout(500)


def trends_related(context, anchor, country, timeframe, evidence_dir):
    page = context.new_page()
    observed_payloads = []

    def capture_related_response(response):
        try:
            parsed = urlparse(response.url)
            if parsed.hostname != "trends.google.com" or "/trends/api/widgetdata/relatedsearches" not in parsed.path:
                return
            if response.status != 200:
                return
            payload = _decode_trends_payload(response.text())
            related_queries = parse_trends_related(payload)
            observed_payloads.append(
                {"url": response.url, "payload": payload, "related_queries": related_queries}
            )
        except Exception:
            return

    page.on("response", capture_related_response)
    page.goto(
        "https://trends.google.com/trends/explore?"
        f"geo={quote_plus(country)}&date={quote_plus(timeframe)}&q={quote_plus(anchor)}",
        wait_until="domcontentloaded",
    )
    _wait_for_related_payload(page, observed_payloads)
    host = page.url.split("/", 3)[2].lower() if page.url.startswith("http") else ""
    if host != "trends.google.com":
        raise RuntimeError(f"wrong Google Trends origin: {host}")
    body = page.locator("body").inner_text(timeout=5000).lower()
    evidence_key = _evidence_slug(anchor, country, timeframe)
    if "related" not in body and "关联" not in body and not observed_payloads:
        blocker_observed_at = now()
        blocker_evidence = evidence_json(
            evidence_dir,
            f"trends-related-{evidence_key}-blocked.json",
            {
                "anchor": anchor,
                "country": country,
                "timeframe": timeframe,
                "observed_at": blocker_observed_at,
                "page_url": page.url,
                "body_excerpt": body[:2000],
                "observed_related_payload_count": 0,
                "blocker": "related_result_not_confirmed",
            },
        )
        blocker_screenshot = screenshot(page, evidence_dir, f"trends-related-{evidence_key}-blocked.png")
        raise RuntimeError(
            "Google Trends related result could not be confirmed; "
            f"blocker_evidence_ref={blocker_evidence}; blocker_screenshot_ref={blocker_screenshot}"
        )
    if not observed_payloads:
        blocker_observed_at = now()
        blocker_evidence = evidence_json(
            evidence_dir,
            f"trends-related-{evidence_key}-payload-blocked.json",
            {
                "anchor": anchor,
                "country": country,
                "timeframe": timeframe,
                "observed_at": blocker_observed_at,
                "page_url": page.url,
                "body_excerpt": body[:2000],
                "observed_related_payload_count": 0,
                "blocker": "related_payload_not_observed",
            },
        )
        blocker_screenshot = screenshot(page, evidence_dir, f"trends-related-{evidence_key}-payload-blocked.png")
        raise RuntimeError(
            "Google Trends related payload was not observed; screenshot-only evidence is insufficient; "
            f"blocker_evidence_ref={blocker_evidence}; blocker_screenshot_ref={blocker_screenshot}"
        )

    captured = observed_payloads[-1]
    observed_at = now()
    raw_evidence = evidence_json(
        evidence_dir,
        f"trends-related-{evidence_key}.json",
        {
            "anchor": anchor,
            "country": country,
            "timeframe": timeframe,
            "observed_at": observed_at,
            "source_url": captured["url"],
            "payload": captured["payload"],
            "related_queries": captured["related_queries"],
        },
    )
    screenshot_ref = screenshot(page, evidence_dir, f"trends-related-{evidence_key}.png")
    return {
        "anchor": anchor,
        "related_queries": captured["related_queries"],
        "country": country,
        "timeframe": timeframe,
        "observed_at": observed_at,
        "source": "Google Trends",
        "source_type": "google_trends_related",
        "source_url": captured["url"],
        "raw_evidence_ref": raw_evidence,
        "screenshot_ref": screenshot_ref,
    }


def trends_timeline(context, keyword, market, timeframe, evidence_dir):
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
    page.goto(
        "https://trends.google.com/trends/explore?"
        f"geo={quote_plus(market)}&date={quote_plus(timeframe)}&q={quote_plus(keyword)}",
        wait_until="domcontentloaded",
    )
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
    evidence_key = _evidence_slug(keyword, market, timeframe)
    observed_at = now()
    raw_evidence = evidence_json(
        evidence_dir,
        f"trends-{evidence_key}.json",
        {
            "keyword": keyword,
            "market": market,
            "requested_timeframe": timeframe,
            "observed_at": observed_at,
            "source_url": captured["url"],
            "payload": captured["payload"],
            "series": captured["series"],
            "actual_resolution": infer_timeline_resolution(captured["series"]),
        },
    )
    screenshot_ref = screenshot(page, evidence_dir, f"trends-{evidence_key}.png")
    return {
        "keyword": keyword,
        "is_finalist": True,
        "source": "Google Trends",
        "source_type": "google_trends_timeline",
        "source_url": captured["url"],
        "market": market,
        "requested_timeframe": timeframe,
        "actual_resolution": infer_timeline_resolution(captured["series"]),
        "series": captured["series"],
        "observed_at": observed_at,
        "raw_evidence_ref": raw_evidence,
        "screenshot_ref": screenshot_ref,
        "google_trends_source": "Google Trends",
        "google_trends_market": market,
        "google_trends_observed_at": observed_at,
        "google_trends_evidence_ref": raw_evidence,
        "google_trends_screenshot_ref": screenshot_ref,
        "google_trends_series": captured["series"],
    }


def trends(context, keyword, market, evidence_dir):
    return trends_timeline(context, keyword, market, "today 12-m", evidence_dir)


class Throttle:
    def __init__(self, min_delay_seconds=1.0, jitter_seconds=0.25, sleeper=time.sleep, random_source=random.random):
        if min_delay_seconds < 0 or jitter_seconds < 0:
            raise ValueError("throttle delays must be non-negative")
        self.min_delay_seconds = float(min_delay_seconds)
        self.jitter_seconds = float(jitter_seconds)
        self.sleeper = sleeper
        self.random_source = random_source
        self._has_waited = False

    def wait(self):
        if not self._has_waited:
            self._has_waited = True
            return
        delay = self.min_delay_seconds + self.jitter_seconds * float(self.random_source())
        self.sleeper(delay)


def _clean_text(node):
    try:
        if not node.is_visible():
            return ""
        return " ".join(node.inner_text().split()).strip()
    except Exception:
        return ""


def _collect_paa(page):
    """Visible 'People also ask' questions on the current SERP.

    Google also renders a wrapper element holding every question concatenated.
    It is rejected by the single-'?' and length rules rather than by a selector,
    because the wrapper's markup changes more often than its shape does.
    """
    out = []
    for selector in ('[jsname="yEVEwb"]', "div[data-initq]", '[role="heading"][aria-level="3"]'):
        for node in page.locator(selector).all():
            text = _clean_text(node)
            if not text or not text.endswith("?") or text.count("?") > 1:
                continue
            if len(text) > 120 or text.lower().startswith("people also ask"):
                continue
            if text not in out:
                out.append(text)
    return out


RELATED_NOISE = {"next", "more results", "previous", "images", "videos", "news", "shopping"}


def _collect_related(page, seed):
    """Visible 'Related searches' terms on the current SERP."""
    out = []
    seed_norm = " ".join(str(seed or "").lower().split())
    for selector in ('a[href*="/search?"] div[role="link"]', "div[data-abe] a", "#botstuff a"):
        for node in page.locator(selector).all():
            text = _clean_text(node)
            if not text or not 2 < len(text) < 80:
                continue
            low = text.lower()
            if low in RELATED_NOISE or low == seed_norm or text in out:
                continue
            out.append(text)
    return out


def expansions(context, seed, market, language, evidence_dir):
    """People Also Ask + Related Searches from one SERP page load.

    Both blocks render on the same result page the SERP collector already
    opens, so they cost no extra page load and carry the same observed
    provenance as the organic results. They expose tool and format demand that
    autocomplete does not return for the same seed.
    """
    page = context.new_page()
    goto_google(page, f"https://www.google.com/search?q={quote_plus(seed)}&gl={quote_plus(market)}&hl={quote_plus(language)}")
    _wait_for_serp_headings(page)
    page.wait_for_timeout(2500)
    paa = _collect_paa(page)
    related = _collect_related(page, seed)
    if not paa and not related:
        raise RuntimeError("Google SERP exposed neither People-Also-Ask nor Related-Searches blocks")
    observed_at = now()
    slug = _evidence_slug("expansions", seed, market, language)
    evidence = screenshot(page, evidence_dir, f"{slug}.png")
    observation = evidence_json(
        evidence_dir,
        f"{slug}.json",
        {
            "page_url": page.url,
            "seed": seed,
            "people_also_ask": paa,
            "related_searches": related,
            "market": market,
            "language": language,
            "observed_at": observed_at,
        },
    )
    return {
        "seed": seed,
        "people_also_ask": paa,
        "related_searches": related,
        "expansion_count": len(paa) + len(related),
        "market": market,
        "language": language,
        "observed_at": observed_at,
        "source": "google_serp_expansions",
        "evidence_ref": evidence,
        "observation_ref": observation,
    }


def _artifacts_for(mode, result):
    if mode == "trends_related":
        return [
            {"path": result["raw_evidence_ref"], "role": "related_payload"},
            {"path": result["screenshot_ref"], "role": "screenshot"},
        ]
    if mode in {"trends", "trends_timeline"}:
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
    parser.add_argument("mode", choices=["autocomplete", "expansions", "intitle", "serp", "trends", "trends_timeline", "trends_related"])
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
        pw, browser, context = connect()
        if args.mode == "autocomplete":
            if not args.seed:
                raise RuntimeError("--seed is required")
            result = autocomplete(context, args.seed, args.country, args.language, args.evidence_dir)
        elif args.mode == "expansions":
            if not args.seed:
                raise RuntimeError("--seed is required")
            result = expansions(context, args.seed, args.market, args.language, args.evidence_dir)
        else:
            if not args.keyword:
                raise RuntimeError("--keyword is required")
            if args.mode == "intitle":
                result = intitle(context, args.keyword, args.market, args.evidence_dir)
            elif args.mode == "serp":
                result = serp(context, args.keyword, args.market, args.evidence_dir)
            elif args.mode == "trends_related":
                result = trends_related(context, args.keyword, args.market, args.timeframe, args.evidence_dir)
            elif args.mode == "trends_timeline":
                result = trends_timeline(context, args.keyword, args.market, args.timeframe, args.evidence_dir)
            else:
                result = trends(context, args.keyword, args.market, args.evidence_dir)
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
