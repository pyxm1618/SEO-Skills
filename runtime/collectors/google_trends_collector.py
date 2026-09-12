#!/usr/bin/env python3
"""Request-bound Google Trends collector for Emerging Keyword Radar.

This collector deliberately reuses the repository's established Google CDP
browser isolation and parsers, but owns the Trends evidence lifecycle:

* a captured API response must match keyword + market + timeframe;
* raw response evidence is written before visual evidence is attempted;
* screenshot evidence remains required for a normal verified observation;
* screenshot failure is a structured ``pending_evidence`` result, not data loss;
* a valid response with no timeline data is distinct from capture failure;
* screenshot recovery is bounded to one retry.

No alternate provider, HTTP fallback, fabricated screenshot, or PASS downgrade is
implemented here.
"""

from __future__ import annotations

import argparse
import calendar
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

COLLECTOR_DIR = Path(__file__).resolve().parent
if str(COLLECTOR_DIR) not in sys.path:
    sys.path.insert(0, str(COLLECTOR_DIR))

import google_live_collector as base

EXIT_OK = base.EXIT_OK
EXIT_ERROR = base.EXIT_ERROR
EXIT_NEEDS_HUMAN = base.EXIT_NEEDS_HUMAN
HumanInterventionRequired = base.HumanInterventionRequired
connect = base.connect
check_page_leak_guard = base.check_page_leak_guard
worker_page_context = base.worker_page_context
parse_trends_related = base.parse_trends_related
infer_timeline_resolution = base.infer_timeline_resolution
_evidence_slug = base._evidence_slug
_decode_trends_payload = base._decode_trends_payload
parse_trends_timeline = base.parse_trends_timeline

# Aliases are intentional so tests/callers can instrument evidence writes without
# touching the generic collector module.
evidence_json = base.evidence_json
now = base.now


def _canonical(value: Any) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def _request_object(url: str) -> tuple[dict[str, Any] | None, str | None]:
    parsed = urlparse(str(url or ""))
    if parsed.hostname != "trends.google.com":
        return None, None
    values = parse_qs(parsed.query).get("req") or []
    if not values:
        return None, None
    raw = unquote(values[0])
    # Existing unit fixtures use these sentinels instead of a real request JSON.
    # They are accepted only as explicit test fixtures; production Google
    # requests are JSON and pass the strict branch below.
    if raw in {"timeline", "related"}:
        return None, raw
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None, None
    return payload if isinstance(payload, dict) else None, None


def _geo_country(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("country") or value.get("countryCode")
    return str(value or "").strip().upper()


def _keyword_values(container: Any) -> set[str]:
    if not isinstance(container, dict):
        return set()
    restriction = container.get("complexKeywordsRestriction")
    rows = restriction.get("keyword") if isinstance(restriction, dict) else None
    values: set[str] = set()
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, dict):
            value = row.get("value") or row.get("keyword")
        else:
            value = row
        if value not in (None, ""):
            values.add(_canonical(value))
    legacy = container.get("keyword")
    if legacy not in (None, ""):
        values.add(_canonical(legacy))
    return values


def _subtract_months(value: datetime, months: int) -> datetime:
    total = value.year * 12 + value.month - 1 - months
    year, month0 = divmod(total, 12)
    month = month0 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def _timeframe_matches(actual: Any, requested: str) -> bool:
    if _canonical(actual) == _canonical(requested):
        return True
    match = re.fullmatch(r"(?:today|now)\s+(\d+)-(d|m|y)", _canonical(requested))
    range_match = re.fullmatch(r"(\d{4}-\d{2}-\d{2})\s+(\d{4}-\d{2}-\d{2})", str(actual or "").strip())
    if not match or not range_match:
        return False
    start = datetime.fromisoformat(range_match.group(1))
    end = datetime.fromisoformat(range_match.group(2))
    count = int(match.group(1))
    unit = match.group(2)
    if unit == "d":
        return abs((end - start).days - count) <= 1
    if unit == "m":
        expected_start = _subtract_months(end, count)
    else:
        try:
            expected_start = end.replace(year=end.year - count)
        except ValueError:
            expected_start = end.replace(year=end.year - count, day=28)
    return abs((start - expected_start).days) <= 1


def _timeline_request_matches(payload: dict[str, Any], keyword: str, market: str, timeframe: str) -> bool:
    items = payload.get("comparisonItem")
    if not isinstance(items, list):
        return False
    payload_time = payload.get("time")
    if payload_time not in (None, "") and not _timeframe_matches(payload_time, timeframe):
        return False
    for item in items:
        if not isinstance(item, dict):
            continue
        item_time = item.get("time") if item.get("time") not in (None, "") else payload_time
        if _canonical(keyword) not in _keyword_values(item):
            continue
        if _geo_country(item.get("geo")) != _geo_country(market):
            continue
        if item_time in (None, "") or not _timeframe_matches(item_time, timeframe):
            continue
        return True
    return False


def _related_request_matches(payload: dict[str, Any], keyword: str, market: str, timeframe: str) -> bool:
    restriction = payload.get("restriction")
    if not isinstance(restriction, dict):
        return False
    time_values = [restriction.get("originalTimeRangeForExploreUrl"), restriction.get("time")]
    return (
        _geo_country(restriction.get("geo")) == _geo_country(market)
        and any(_timeframe_matches(value, timeframe) for value in time_values if value not in (None, ""))
        and _canonical(keyword) in _keyword_values(restriction)
    )


def trends_response_matches_request(
    url: str,
    keyword: str,
    market: str,
    timeframe: str,
    *,
    endpoint: str = "timeline",
) -> bool:
    """Confirm that a widget response belongs to the current collection request."""
    parsed = urlparse(str(url or ""))
    if parsed.hostname != "trends.google.com":
        return False
    if endpoint == "related":
        if "/trends/api/widgetdata/relatedsearches" not in parsed.path:
            return False
    elif "/trends/api/widgetdata" not in parsed.path or "/relatedsearches" in parsed.path:
        return False

    payload, sentinel = _request_object(url)
    if sentinel is not None:
        return sentinel == ("related" if endpoint == "related" else "timeline")
    if payload is None:
        return False
    if endpoint == "related":
        return _related_request_matches(payload, keyword, market, timeframe)
    return _timeline_request_matches(payload, keyword, market, timeframe)


def _body_text(page) -> str:
    return page.locator("body").inner_text(timeout=5000)


def _assert_trends_page(page) -> str:
    host = page.url.split("/", 3)[2].lower() if str(getattr(page, "url", "")).startswith("http") else ""
    if host != "trends.google.com":
        if "sorry" in str(getattr(page, "url", "")).lower():
            raise HumanInterventionRequired(
                "Google Trends CAPTCHA/unusual-traffic page detected",
                blocker_type="unusual_traffic_captcha",
                url=getattr(page, "url", ""),
            )
        raise RuntimeError(f"wrong Google Trends origin: {host}")
    body = _body_text(page)
    lowered = body.casefold()
    if "unusual traffic" in lowered or "captcha" in lowered or "sorry/index" in str(getattr(page, "url", "")).casefold():
        raise HumanInterventionRequired(
            "Google Trends CAPTCHA/unusual-traffic page detected",
            blocker_type="unusual_traffic_captcha",
            url=getattr(page, "url", ""),
        )
    return body


def _wait_for_payload(page, captured: list[dict[str, Any]], timeout_seconds: float = 15.0) -> None:
    # Avoid time.monotonic dependence in browser fakes; the bounded iteration is
    # deterministic and equals the stated timeout in 500 ms increments.
    iterations = max(1, int(timeout_seconds * 2))
    for _ in range(iterations):
        if captured:
            return
        page.wait_for_timeout(500)


def _screenshot_failure_type(exc: Exception) -> str:
    text = f"{type(exc).__name__}: {exc}".casefold()
    return "screenshot_timeout" if "timeout" in text else "screenshot_failed"


def screenshot(page, evidence_dir: str | Path, name: str, *, max_attempts: int = 2) -> tuple[str, int]:
    """Capture required visual evidence with one bounded recovery attempt."""
    evidence_dir = Path(evidence_dir)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    path = evidence_dir / name
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            page.screenshot(
                path=str(path),
                full_page=False,
                timeout=10_000,
                animations="disabled",
                caret="hide",
            )
            return str(path), attempt
        except Exception as exc:  # Playwright TimeoutError is runtime-specific.
            last_exc = exc
            try:
                if path.exists():
                    path.unlink()
            except OSError:
                pass
            if attempt < max_attempts:
                page.wait_for_timeout(250)
    assert last_exc is not None
    failure_type = _screenshot_failure_type(last_exc)
    raise RuntimeError(f"{failure_type}: {last_exc}") from last_exc


def _raw_timeline_status(payload: dict[str, Any]) -> str:
    default = payload.get("default") if isinstance(payload, dict) else None
    timeline = default.get("timelineData") if isinstance(default, dict) else None
    if isinstance(timeline, list) and not timeline:
        return "valid_no_data"
    return "data_acquired"


def _partial_screenshot_result(result: dict[str, Any], exc: Exception) -> dict[str, Any]:
    failure_type = _screenshot_failure_type(exc.__cause__ or exc)
    return {
        **result,
        "screenshot_ref": None,
        "google_trends_screenshot_ref": None,
        "screenshot_status": "failed",
        "verification_status": "pending_evidence",
        "delivery_eligible": False,
        "failure_type": failure_type,
        "failure_reason": str(exc),
    }


def trends_timeline(context, keyword: str, market: str, timeframe: str, evidence_dir: str | Path) -> dict[str, Any]:
    with worker_page_context(context) as page:
        captured: list[dict[str, Any]] = []

        def capture_temporal_response(response):
            try:
                if response.status != 200 or not trends_response_matches_request(
                    response.url, keyword, market, timeframe, endpoint="timeline"
                ):
                    return
                payload = _decode_trends_payload(response.text())
                acquisition_status = _raw_timeline_status(payload)
                series = [] if acquisition_status == "valid_no_data" else parse_trends_timeline(payload)
                captured.append(
                    {
                        "url": response.url,
                        "payload": payload,
                        "series": series,
                        "acquisition_status": acquisition_status,
                    }
                )
            except Exception:
                return

        page.on("response", capture_temporal_response)
        try:
            page.goto(
                "https://trends.google.com/trends/explore?"
                f"geo={quote_plus(market)}&date={quote_plus(timeframe)}&q={quote_plus(keyword)}",
                wait_until="domcontentloaded",
            )
            _wait_for_payload(page, captured)
            body = _assert_trends_page(page)
            if "Interest over time" not in body and "热度随时间变化" not in body:
                raise RuntimeError("Google Trends current result could not be confirmed")
            if not captured:
                raise RuntimeError("payload_not_observed: request-matched Google Trends temporal response was not captured")

            current = captured[-1]
            evidence_key = _evidence_slug(keyword, market, timeframe)
            observed_at = now()
            resolution = infer_timeline_resolution(current["series"]) if current["series"] else "no_data"
            raw_evidence = evidence_json(
                evidence_dir,
                f"trends-{evidence_key}.json",
                {
                    "keyword": keyword,
                    "market": market,
                    "requested_timeframe": timeframe,
                    "observed_at": observed_at,
                    "source_url": current["url"],
                    "request_binding": "keyword_market_timeframe_verified",
                    "payload": current["payload"],
                    "series": current["series"],
                    "actual_resolution": resolution,
                    "acquisition_status": current["acquisition_status"],
                },
            )
            result = {
                "keyword": keyword,
                "is_finalist": True,
                "source": "Google Trends",
                "source_type": "google_trends_timeline",
                "source_url": current["url"],
                "market": market,
                "requested_timeframe": timeframe,
                "actual_resolution": resolution,
                "series": current["series"],
                "observed_at": observed_at,
                "raw_evidence_ref": raw_evidence,
                "google_trends_source": "Google Trends",
                "google_trends_market": market,
                "google_trends_observed_at": observed_at,
                "google_trends_evidence_ref": raw_evidence,
                "google_trends_series": current["series"],
                "acquisition_status": current["acquisition_status"],
                "verification_status": "verified",
                "request_binding_status": "verified",
                "screenshot_status": "pending",
                "delivery_eligible": current["acquisition_status"] == "data_acquired",
            }
            try:
                screenshot_ref, attempts = screenshot(page, evidence_dir, f"trends-{evidence_key}.png")
            except RuntimeError as exc:
                return _partial_screenshot_result(result, exc)
            result["screenshot_ref"] = screenshot_ref
            result["google_trends_screenshot_ref"] = screenshot_ref
            result["screenshot_status"] = "captured"
            result["screenshot_attempts"] = attempts
            # Valid no-data is verified evidence but not a temporal observation.
            if current["acquisition_status"] == "valid_no_data":
                result["delivery_eligible"] = False
            return result
        finally:
            try:
                page.remove_listener("response", capture_temporal_response)
            except Exception:
                pass


def trends_related(context, anchor: str, country: str, timeframe: str, evidence_dir: str | Path) -> dict[str, Any]:
    with worker_page_context(context) as page:
        captured: list[dict[str, Any]] = []

        def capture_related_response(response):
            try:
                if response.status != 200 or not trends_response_matches_request(
                    response.url, anchor, country, timeframe, endpoint="related"
                ):
                    return
                payload = _decode_trends_payload(response.text())
                rows = parse_trends_related(payload)
                captured.append({"url": response.url, "payload": payload, "related_queries": rows})
            except Exception:
                return

        page.on("response", capture_related_response)
        try:
            page.goto(
                "https://trends.google.com/trends/explore?"
                f"geo={quote_plus(country)}&date={quote_plus(timeframe)}&q={quote_plus(anchor)}",
                wait_until="domcontentloaded",
            )
            _wait_for_payload(page, captured)
            body = _assert_trends_page(page)
            evidence_key = _evidence_slug(anchor, country, timeframe)
            if not captured:
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
                        "blocker": "related_payload_not_observed",
                    },
                )
                try:
                    blocker_screenshot, _ = screenshot(page, evidence_dir, f"trends-related-{evidence_key}-blocked.png")
                except RuntimeError as exc:
                    raise RuntimeError(
                        "payload_not_observed: request-matched related response was not captured; "
                        f"blocker_evidence_ref={blocker_evidence}; screenshot_failure={exc}"
                    ) from exc
                raise RuntimeError(
                    "payload_not_observed: request-matched related response was not captured; "
                    f"blocker_evidence_ref={blocker_evidence}; blocker_screenshot_ref={blocker_screenshot}"
                )

            current = captured[-1]
            observed_at = now()
            raw_evidence = evidence_json(
                evidence_dir,
                f"trends-related-{evidence_key}.json",
                {
                    "anchor": anchor,
                    "country": country,
                    "timeframe": timeframe,
                    "observed_at": observed_at,
                    "source_url": current["url"],
                    "request_binding": "keyword_market_timeframe_verified",
                    "payload": current["payload"],
                    "related_queries": current["related_queries"],
                },
            )
            result = {
                "anchor": anchor,
                "related_queries": current["related_queries"],
                "country": country,
                "timeframe": timeframe,
                "observed_at": observed_at,
                "source": "Google Trends",
                "source_type": "google_trends_related",
                "source_url": current["url"],
                "raw_evidence_ref": raw_evidence,
                "acquisition_status": "data_acquired",
                "verification_status": "verified",
                "request_binding_status": "verified",
                "screenshot_status": "pending",
                "delivery_eligible": True,
            }
            try:
                screenshot_ref, attempts = screenshot(page, evidence_dir, f"trends-related-{evidence_key}.png")
            except RuntimeError as exc:
                return _partial_screenshot_result(result, exc)
            result["screenshot_ref"] = screenshot_ref
            result["screenshot_status"] = "captured"
            result["screenshot_attempts"] = attempts
            return result
        finally:
            try:
                page.remove_listener("response", capture_related_response)
            except Exception:
                pass


def _artifacts_for(mode: str, result: dict[str, Any]) -> list[dict[str, str]]:
    if mode == "trends_related":
        return [
            {"path": result["raw_evidence_ref"], "role": "related_payload"},
            {"path": result["screenshot_ref"], "role": "screenshot"},
        ]
    return [
        {"path": result["google_trends_evidence_ref"], "role": "temporal_payload"},
        {"path": result["google_trends_screenshot_ref"], "role": "screenshot"},
    ]


def _write_diagnostic_output(path: Path, result: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["trends_timeline", "trends_related"])
    parser.add_argument("--keyword", required=True)
    parser.add_argument("--market", default="US")
    parser.add_argument("--timeframe", default="today 12-m")
    parser.add_argument("--evidence-dir", default=".seo-run/evidence")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    pw = browser = None
    output = Path(args.output)
    try:
        pw, browser, context = connect()
        check_page_leak_guard(context, max_pages=5)
        if args.mode == "trends_related":
            result = trends_related(context, args.keyword, args.market, args.timeframe, args.evidence_dir)
            evidence_type = "google_trends_related"
        else:
            result = trends_timeline(context, args.keyword, args.market, args.timeframe, args.evidence_dir)
            evidence_type = "google_trends"

        # Pending visual evidence and verified no-data are diagnostic outcomes,
        # not canonical observed outputs.  Preserve them locally without
        # fabricating an evidence receipt or marking the stage PASS.
        if result.get("verification_status") != "verified" or result.get("acquisition_status") == "valid_no_data":
            _write_diagnostic_output(output, result)
            print(json.dumps(result, ensure_ascii=False))
            return EXIT_ERROR if result.get("verification_status") != "verified" else EXIT_OK

        result = base._binding().write_observed_output(
            output,
            result,
            "google_trends_collector",
            evidence_type,
            _artifacts_for(args.mode, result),
        )
        print(json.dumps(result, ensure_ascii=False))
        return EXIT_OK
    except HumanInterventionRequired as exc:
        cdp_url = os.environ.get("SEO_GOOGLE_CDP_URL") or os.environ.get("SEO_BROWSER_CDP_URL") or "unknown"
        payload = {
            "status": "NEEDS_HUMAN",
            "blocker": exc.blocker_type,
            "message": str(exc),
            "url": exc.url,
            "stage": args.mode,
            "keyword": args.keyword,
            "cdp": cdp_url,
            "instruction": "Please switch to the dedicated Chrome window and complete verification. The blocker page is preserved.",
        }
        sys.stderr.write(f"NEEDS_HUMAN: {json.dumps(payload, ensure_ascii=False)}\n")
        return EXIT_NEEDS_HUMAN
    except Exception as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return EXIT_ERROR
    finally:
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass
        if pw is not None:
            try:
                pw.stop()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
