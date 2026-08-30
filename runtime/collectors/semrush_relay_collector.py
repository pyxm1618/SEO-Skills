#!/usr/bin/env python3
"""Live Semrush acquisition through the current authenticated sem.3ue.com session.

The collector intentionally has no hard-coded Semrush endpoint and no provider
fallback. A request descriptor must come from a current live same-origin
network capture. The raw response is preserved as evidence and deterministic
normalizers turn only the observed schema into contract rows.
"""

import argparse
import importlib.util
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ALLOWED_HOST = "sem.3ue.com"
MODES = {"ideas", "exact", "competitor_organic"}
DEFAULT_CAPTURE_MAX_AGE_SECONDS = 900
MAX_FUTURE_SKEW_SECONDS = 60
BINDING_PATH = Path(__file__).resolve().parents[1] / "evidence_binding.py"


def _binding():
    spec = importlib.util.spec_from_file_location("seo_evidence_binding_for_semrush", BINDING_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def now():
    return datetime.now(timezone.utc).isoformat()


def playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is required for live relay collection; no provider fallback is allowed") from exc
    return sync_playwright


def _present(value):
    return value is not None and value != ""


def _number(value, field, minimum=None, maximum=None):
    if isinstance(value, bool) or value is None:
        raise RuntimeError(f"relay response schema missing or invalid {field}")
    try:
        number = float(str(value).replace(",", ""))
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"relay response schema invalid numeric {field}") from exc
    if not math.isfinite(number):
        raise RuntimeError(f"relay response schema invalid numeric {field}")
    if minimum is not None and number < minimum:
        raise RuntimeError(f"relay response schema invalid {field}: below {minimum}")
    if maximum is not None and number > maximum:
        raise RuntimeError(f"relay response schema invalid {field}: above {maximum}")
    return int(number) if number.is_integer() else number


def _keyword(value):
    return " ".join(str(value or "").split()).casefold()


def _identity_field(mode):
    if mode == "ideas":
        return "seed"
    if mode == "exact":
        return "keyword"
    if mode == "competitor_organic":
        return "competitor_domain"
    raise RuntimeError(f"unsupported relay normalization mode: {mode}")


def _capture_time(value):
    text = str(value or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        captured = datetime.fromisoformat(text)
    except ValueError as exc:
        raise RuntimeError("live relay request capture_observed_at is invalid") from exc
    if captured.tzinfo is None:
        captured = captured.replace(tzinfo=timezone.utc)
    return captured.astimezone(timezone.utc)


def _validate_capture_freshness(data):
    try:
        max_age = int(os.environ.get("SEO_RELAY_CAPTURE_MAX_AGE_SECONDS", DEFAULT_CAPTURE_MAX_AGE_SECONDS))
    except ValueError as exc:
        raise RuntimeError("SEO_RELAY_CAPTURE_MAX_AGE_SECONDS must be an integer") from exc
    if max_age <= 0:
        raise RuntimeError("SEO_RELAY_CAPTURE_MAX_AGE_SECONDS must be positive")
    age_seconds = (datetime.now(timezone.utc) - _capture_time(data["capture_observed_at"])).total_seconds()
    if age_seconds < -MAX_FUTURE_SKEW_SECONDS:
        raise RuntimeError("live relay request capture timestamp is implausibly in the future")
    if age_seconds > max_age:
        raise RuntimeError(
            f"live relay request capture is stale ({int(age_seconds)}s old; max {max_age}s); recapture from current session"
        )


def load_request(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    required = [
        "path", "method", "body", "capture_observed_at", "capture_evidence_ref",
        "mode", "metric_database",
    ]
    missing = [field for field in required if not _present(data.get(field))]
    if missing:
        raise RuntimeError(f"live relay request descriptor incomplete: {', '.join(missing)}")
    if data["mode"] not in MODES:
        raise RuntimeError(f"unsupported relay normalization mode: {data['mode']}")
    identity_field = _identity_field(data["mode"])
    if not _present(data.get(identity_field)):
        raise RuntimeError(f"live relay request descriptor incomplete: {identity_field}")
    if str(data["metric_database"]).lower() != "us":
        raise RuntimeError("production relay metric_database must be us")
    parsed = urlparse(data["path"] if "://" in data["path"] else f"https://{ALLOWED_HOST}{data['path']}")
    if parsed.hostname != ALLOWED_HOST:
        raise RuntimeError(f"relay request host must be {ALLOWED_HOST}")
    capture_ref = Path(str(data["capture_evidence_ref"]))
    if not capture_ref.is_file():
        raise RuntimeError("live relay request capture evidence file is missing")
    _validate_capture_freshness(data)
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


def _provenance(descriptor, raw_evidence_ref):
    return str(raw_evidence_ref or descriptor.get("capture_evidence_ref") or "").strip()


def normalize_ideas(data, descriptor, observed_at, raw_evidence_ref=None):
    if not isinstance(data, dict) or "error" in data or not isinstance(data.get("result"), list):
        raise RuntimeError("relay Ideas response schema mismatch")
    rows = []
    for index, item in enumerate(data["result"]):
        if not isinstance(item, dict) or not _present(item.get("phrase")):
            raise RuntimeError(f"relay Ideas response schema invalid row {index}")
        row = {"keyword": str(item["phrase"]).strip()}
        if item.get("volume") is not None:
            row["volume"] = _number(item["volume"], f"rows[{index}].volume", minimum=0)
        if item.get("difficulty") is not None:
            row["kd"] = _number(item["difficulty"], f"rows[{index}].difficulty", minimum=0, maximum=100)
        rows.append(row)
    if not rows:
        raise RuntimeError("relay Ideas response contains no rows")
    provenance_ref = _provenance(descriptor, raw_evidence_ref)
    if not provenance_ref:
        raise RuntimeError("relay Ideas evidence provenance is missing")
    return {
        "seed": str(descriptor["seed"]).strip(),
        "rows": rows,
        "observed_at": observed_at,
        "metric_source": "Semrush",
        "metric_database": "us",
        "metric_stage": "ideas",
        "relay_origin": f"https://{ALLOWED_HOST}/",
        "provenance_ref": provenance_ref,
    }


def _select_exact_row(data, descriptor):
    if not isinstance(data, dict) or "error" in data:
        raise RuntimeError("relay Exact response schema mismatch")
    result = data.get("result")
    if not isinstance(result, dict) or not isinstance(result.get("keywords"), list):
        raise RuntimeError("relay Exact response schema mismatch: result.keywords missing")
    target = _keyword(descriptor["keyword"])
    database = str(descriptor["metric_database"]).lower()
    matches = [
        row for row in result["keywords"]
        if isinstance(row, dict)
        and str(row.get("database") or "").lower() == database
        and _keyword(row.get("phrase")) == target
    ]
    if len(matches) != 1:
        raise RuntimeError(f"relay Exact response schema/identity mismatch: expected 1 US exact row, got {len(matches)}")
    return matches[0]


def normalize_exact(data, descriptor, observed_at, raw_evidence_ref=None):
    row = _select_exact_row(data, descriptor)
    required = ["phrase", "volume", "difficulty", "cpc", "intents", "competition_level", "trend"]
    missing = [field for field in required if field not in row or row[field] is None]
    if missing:
        raise RuntimeError(f"relay Exact response schema missing required fields: {', '.join(missing)}")
    if not isinstance(row["intents"], list) or not row["intents"]:
        raise RuntimeError("relay Exact response schema missing required intents")
    if not isinstance(row["trend"], list) or len(row["trend"]) != 12:
        raise RuntimeError("relay Exact response schema requires 12-month trend")
    trend = [_number(value, f"trend[{index}]", minimum=0) for index, value in enumerate(row["trend"])]
    provenance_ref = _provenance(descriptor, raw_evidence_ref)
    if not provenance_ref:
        raise RuntimeError("relay Exact evidence provenance is missing")
    return {
        "keyword": str(row["phrase"]).strip(),
        "volume": _number(row["volume"], "volume", minimum=0),
        "kd": _number(row["difficulty"], "difficulty", minimum=0, maximum=100),
        "cpc": _number(row["cpc"], "cpc", minimum=0),
        "intent": row["intents"],
        "competition_level": row["competition_level"],
        "trend": trend,
        "metric_source": "Semrush",
        "metric_database": "us",
        "metric_stage": "exact",
        "observed_at": observed_at,
        "relay_origin": f"https://{ALLOWED_HOST}/",
        "provenance_ref": provenance_ref,
    }


def normalize_competitor_organic(data, descriptor, observed_at, raw_evidence_ref=None):
    if not isinstance(data, dict) or "error" in data:
        raise RuntimeError("relay competitor response schema mismatch")
    result = data.get("result")
    if isinstance(result, dict):
        rows_data = result.get("keywords")
    else:
        rows_data = result
    if not isinstance(rows_data, list):
        raise RuntimeError("relay competitor response schema mismatch: result.keywords missing")

    rows = []
    for index, item in enumerate(rows_data):
        if not isinstance(item, dict) or not _present(item.get("phrase")):
            raise RuntimeError(f"relay competitor response schema invalid row {index}")
        row = {"keyword": str(item["phrase"]).strip()}
        if item.get("volume") is not None:
            row["volume"] = _number(item["volume"], f"rows[{index}].volume", minimum=0)
        if item.get("difficulty") is not None:
            row["kd"] = _number(item["difficulty"], f"rows[{index}].difficulty", minimum=0, maximum=100)
        if item.get("cpc") is not None:
            row["cpc"] = _number(item["cpc"], f"rows[{index}].cpc", minimum=0)
        if item.get("position") is not None:
            row["position"] = _number(item["position"], f"rows[{index}].position", minimum=1)
        if item.get("traffic") is not None:
            row["traffic"] = _number(item["traffic"], f"rows[{index}].traffic", minimum=0)
        if item.get("traffic_percent") is not None:
            row["traffic_percent"] = _number(
                item["traffic_percent"], f"rows[{index}].traffic_percent", minimum=0, maximum=100
            )
        if item.get("intents") is not None:
            if not isinstance(item["intents"], list):
                raise RuntimeError(f"relay competitor response schema invalid rows[{index}].intents")
            row["intent"] = item["intents"]
        if item.get("competition_level") is not None:
            row["competition_level"] = item["competition_level"]
        rows.append(row)
    if not rows:
        raise RuntimeError("relay competitor response contains no rows")
    provenance_ref = _provenance(descriptor, raw_evidence_ref)
    if not provenance_ref:
        raise RuntimeError("relay competitor evidence provenance is missing")
    competitor_domain = str(descriptor.get("competitor_domain") or "").strip()
    if not competitor_domain:
        raise RuntimeError("relay competitor descriptor missing competitor_domain")
    return {
        "competitor_domain": competitor_domain,
        "rows": rows,
        "observed_at": observed_at,
        "metric_source": "Semrush",
        "metric_database": "us",
        "metric_stage": "competitor_organic",
        "relay_origin": f"https://{ALLOWED_HOST}/",
        "provenance_ref": provenance_ref,
    }


def _normalize(data, descriptor, observed_at, raw_evidence_ref=None):
    mode = descriptor.get("mode")
    if mode == "ideas":
        return normalize_ideas(data, descriptor, observed_at, raw_evidence_ref)
    if mode == "exact":
        return normalize_exact(data, descriptor, observed_at, raw_evidence_ref)
    if mode == "competitor_organic":
        return normalize_competitor_organic(data, descriptor, observed_at, raw_evidence_ref)
    raise RuntimeError(f"unsupported relay normalization mode: {mode}")


def collect(page, descriptor, raw_evidence_ref=None, raw_output_path=None):
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
    if not isinstance(data, dict):
        raise RuntimeError("relay response schema is not a JSON object")
    if "error" in data:
        raise RuntimeError("relay HTTP succeeded but RPC response contains error")
    for key in descriptor.get("required_top_level_keys", []):
        if key not in data:
            raise RuntimeError(f"relay response schema missing required key: {key}")

    observed_at = now()
    if raw_output_path:
        raw_path = Path(raw_output_path)
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_record = {
            "observed_at": observed_at,
            "relay_origin": f"https://{ALLOWED_HOST}/",
            "request_method": descriptor["method"],
            "request_path": request_url,
            "capture_observed_at": descriptor["capture_observed_at"],
            "capture_evidence_ref": descriptor["capture_evidence_ref"],
            "mode": descriptor["mode"],
            "metric_database": descriptor["metric_database"],
            "seed": descriptor.get("seed"),
            "keyword": descriptor.get("keyword"),
            "competitor_domain": descriptor.get("competitor_domain"),
            "response": data,
        }
        raw_path.write_text(json.dumps(raw_record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raw_evidence_ref = str(raw_path)
    return _normalize(data, descriptor, observed_at, raw_evidence_ref)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True, help="descriptor from current live same-origin network capture")
    parser.add_argument("--output", required=True)
    parser.add_argument("--raw-output", help="raw current relay response evidence; defaults beside --output")
    args = parser.parse_args()
    pw = browser = None
    try:
        descriptor = load_request(args.request)
        output = Path(args.output)
        raw_output = Path(args.raw_output) if args.raw_output else output.with_suffix(".raw.json")
        pw, browser, page = connect_same_origin()
        result = collect(page, descriptor, raw_output_path=raw_output)
        evidence_type = {
            "ideas": "semrush_ideas",
            "exact": "semrush_exact",
            "competitor_organic": "semrush_competitor_organic",
        }[descriptor["mode"]]
        result = _binding().write_observed_output(
            output,
            result,
            "semrush_relay_collector",
            evidence_type,
            [
                {"path": raw_output, "role": "relay_raw_response"},
                {"path": descriptor["capture_evidence_ref"], "role": "current_network_capture"},
            ],
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
