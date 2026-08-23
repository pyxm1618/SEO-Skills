#!/usr/bin/env python3
"""Aggregate comparable emerging-demand signal series without cross-unit arithmetic."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from validate_observations import is_missing, load_rows, parse_iso, validate_rows

SERIES_FIELDS = ("source", "source_type", "country", "signal_unit", "metric_database", "time_window")
METRIC_FIELDS = ("volume", "kd", "cpc", "intitle_results")
CONTEXT_FIELDS = (
    "serp_dedicated_pages",
    "serp_ugc_pages",
    "serp_intent_mismatch",
    "emd_status",
    "durable_search_intent",
    "repeatable_page_or_product_fit",
    "trend_status",
)


def canonical_keyword(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def aggregation_observation_key(row: dict[str, Any]) -> str:
    """Identify one logical source snapshot without treating presentation URLs as new evidence."""
    fields = (
        "keyword",
        "observed_at",
        "source",
        "source_type",
        "root_id",
        "signal_value",
        "signal_unit",
        "country",
        "time_window",
        "metric_source",
        "metric_database",
    )
    values: list[Any] = []
    for field in fields:
        value = row.get(field)
        if field == "keyword":
            value = canonical_keyword(value)
        elif isinstance(value, str):
            value = value.strip().lower()
        values.append(value)
    return json.dumps(values, sort_keys=False, ensure_ascii=False, default=str)


def end_of_day(value: str | None) -> datetime:
    if value:
        parsed, error = parse_iso(value)
        if error or parsed is None:
            raise ValueError("--as-of must be a valid ISO date/datetime")
        if len(value.strip()) == 10:
            parsed = parsed.replace(hour=23, minute=59, second=59, microsecond=999999)
        return parsed
    return datetime.now(timezone.utc)


def row_dt(row: dict[str, Any]) -> datetime | None:
    parsed, error = parse_iso(row.get("observed_at"))
    return None if error else parsed


def mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def window_values(points: list[tuple[datetime, float]], as_of: datetime, min_days_ago: int, max_days_ago: int) -> list[float]:
    values: list[float] = []
    for observed, value in points:
        days_ago = (as_of.date() - observed.date()).days
        if min_days_ago <= days_ago <= max_days_ago:
            values.append(value)
    return values


def summarize_series(key: tuple[Any, ...], rows: list[dict[str, Any]], as_of: datetime) -> dict[str, Any]:
    points = sorted(
        (row_dt(row), float(row["signal_value"]))
        for row in rows
        if row_dt(row) is not None and row.get("signal_value") is not None
    )
    points = [(dt, value) for dt, value in points if dt is not None]
    recent_7 = window_values(points, as_of, 0, 6)
    previous_7 = window_values(points, as_of, 7, 13)
    prior_7 = window_values(points, as_of, 14, 20)
    recent_30 = window_values(points, as_of, 0, 29)
    previous_30 = window_values(points, as_of, 30, 59)
    baseline_90 = window_values(points, as_of, 7, 89)
    baseline_12m = window_values(points, as_of, 7, 364)

    recent_7_mean = mean(recent_7)
    previous_7_mean = mean(previous_7)
    prior_7_mean = mean(prior_7)
    baseline = mean(baseline_90)
    recent = recent_7_mean if recent_7_mean is not None else mean(recent_30)
    growth = None
    growth_status = "unknown"
    if recent is not None and baseline is not None:
        if baseline > 0:
            growth = (recent - baseline) / baseline
            growth_status = "calculated"
        elif baseline == 0 and recent > 0:
            growth_status = "from_observed_zero_baseline"
        elif baseline == 0 and recent == 0:
            growth = 0.0
            growth_status = "calculated"

    acceleration = None
    if recent_7_mean is not None and previous_7_mean is not None and prior_7_mean is not None:
        acceleration = (recent_7_mean - previous_7_mean) - (previous_7_mean - prior_7_mean)

    persistence_values = recent_7 if recent_7 else recent_30
    persistence_window = "recent_7d" if recent_7 else ("recent_30d" if recent_30 else None)
    persistence = None
    positive_count = 0
    if persistence_values:
        positive_count = sum(value > 0 for value in persistence_values)
        persistence = positive_count / len(persistence_values)

    provenance_status = "verified" if rows and all(r.get("provenance_status") == "verified" for r in rows) else "incomplete"
    first_dt = min((dt for dt, _ in points), default=None)
    last_dt = max((dt for dt, _ in points), default=None)
    return {
        "source": key[0],
        "source_type": key[1],
        "country": key[2],
        "signal_unit": key[3],
        "metric_database": key[4],
        "time_window": key[5],
        "observation_count": len(points),
        "first_observed_at": first_dt.date().isoformat() if first_dt else None,
        "last_observed_at": last_dt.date().isoformat() if last_dt else None,
        "recent_7d": recent_7_mean,
        "previous_7d": previous_7_mean,
        "recent_30d": mean(recent_30),
        "previous_30d": mean(previous_30),
        "baseline_90d": baseline,
        "baseline_12m": mean(baseline_12m),
        "baseline_signal": baseline,
        "baseline_observations": len(baseline_90),
        "recent_signal": recent,
        "recent_observations": len(recent_7) if recent_7 else len(recent_30),
        "growth_rate": growth,
        "growth_status": growth_status,
        "acceleration": acceleration,
        "persistence": persistence,
        "persistence_window": persistence_window,
        "persistence_observations": len(persistence_values),
        "positive_observations": positive_count,
        "peak_signal": max((value for _, value in points), default=None),
        "latest_signal": points[-1][1] if points else None,
        "provenance_status": provenance_status,
    }


def latest_non_missing(rows: list[dict[str, Any]], field: str) -> Any:
    ordered = sorted(rows, key=lambda row: row_dt(row) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    for row in ordered:
        value = row.get(field)
        if not is_missing(value):
            return value
    return None


def choose_primary(series: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not series:
        return None

    def sort_key(item: dict[str, Any]):
        last, _ = parse_iso(item.get("last_observed_at"))
        timestamp = last.timestamp() if last else 0.0
        identity = tuple(str(item.get(field) or "") for field in SERIES_FIELDS)
        return (-int(item.get("observation_count") or 0), -timestamp, identity)

    return sorted(series, key=sort_key)[0]


def aggregate(rows: list[dict[str, Any]], as_of: datetime) -> dict[str, Any]:
    validated = validate_rows(rows, as_of)
    invalid_rows = [row for row in validated if row["validation_status"] == "invalid"]
    valid_rows = [row for row in validated if row["validation_status"] == "valid" and canonical_keyword(row.get("keyword"))]

    # Preserve audit rows but count one logical source snapshot only once. Presentation
    # URL variants (for example Google Trends language parameters) are not new evidence.
    seen: set[str] = set()
    unique_rows: list[dict[str, Any]] = []
    duplicate_observation_count = 0
    for row in valid_rows:
        key = aggregation_observation_key(row)
        if key in seen:
            duplicate_observation_count += 1
            continue
        seen.add(key)
        unique_rows.append(row)

    by_keyword: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in unique_rows:
        by_keyword[canonical_keyword(row["keyword"])].append(row)

    candidates: list[dict[str, Any]] = []
    for normalized_keyword, keyword_rows in sorted(by_keyword.items()):
        keyword_all_valid = [row for row in valid_rows if canonical_keyword(row.get("keyword")) == normalized_keyword]
        series_rows: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
        for row in keyword_rows:
            dt = row_dt(row)
            if dt is None or row.get("signal_value") is None:
                continue
            series_key = tuple(row.get(field) for field in SERIES_FIELDS)
            series_rows[series_key].append(row)
        evidence = [summarize_series(key, srows, as_of) for key, srows in series_rows.items()]
        evidence.sort(key=lambda item: tuple(str(item.get(field) or "") for field in SERIES_FIELDS))
        primary = choose_primary(evidence)

        observed_dates = [row_dt(row) for row in keyword_rows if row_dt(row) is not None]
        first_dt = min(observed_dates, default=None)
        last_dt = max(observed_dates, default=None)
        root_ids = sorted({str(row.get("root_id")).strip() for row in keyword_rows if not is_missing(row.get("root_id"))})
        sources = {str(row.get("source")).strip() for row in keyword_rows if not is_missing(row.get("source"))}

        metrics = {field: latest_non_missing(keyword_all_valid, field) for field in METRIC_FIELDS}
        context = {field: latest_non_missing(keyword_all_valid, field) for field in CONTEXT_FIELDS}
        metric_status = "complete" if all(metrics[field] is not None for field in ("volume", "kd", "cpc")) else "incomplete"

        anchor_event = latest_non_missing(keyword_all_valid, "anchor_event")
        anchor_event_date = latest_non_missing(keyword_all_valid, "anchor_event_date")
        anchor_event_source = latest_non_missing(keyword_all_valid, "anchor_event_source")

        candidate = {
            "keyword": str(keyword_rows[0]["keyword"]).strip(),
            "root_id": root_ids[0] if len(root_ids) == 1 else None,
            "root_id_conflict": len(root_ids) > 1,
            "first_observed_at": first_dt.date().isoformat() if first_dt else None,
            "estimated_birth_window": None,
            "age_days": (as_of.date() - first_dt.date()).days if first_dt else None,
            "baseline_signal": primary.get("baseline_signal") if primary else None,
            "recent_signal": primary.get("recent_signal") if primary else None,
            "growth_rate": primary.get("growth_rate") if primary else None,
            "growth_status": primary.get("growth_status") if primary else "unknown",
            "acceleration": primary.get("acceleration") if primary else None,
            "persistence": primary.get("persistence") if primary else None,
            "persistence_observations": primary.get("persistence_observations", 0) if primary else 0,
            "source_count": len(sources),
            "source_evidence": evidence,
            "primary_series": primary,
            "anchor_event": anchor_event,
            "anchor_event_date": anchor_event_date,
            "anchor_event_source": anchor_event_source,
            "volume": metrics["volume"],
            "kd": metrics["kd"],
            "cpc": metrics["cpc"],
            "intitle_results": metrics["intitle_results"],
            "serp_dedicated_pages": context["serp_dedicated_pages"],
            "serp_ugc_pages": context["serp_ugc_pages"],
            "serp_intent_mismatch": context["serp_intent_mismatch"],
            "emd_status": context["emd_status"],
            "durable_search_intent": context["durable_search_intent"],
            "repeatable_page_or_product_fit": context["repeatable_page_or_product_fit"],
            "trend_status": context["trend_status"],
            "metric_status": metric_status,
            "observed_at": last_dt.date().isoformat() if last_dt else None,
            "unique_observation_count": len(keyword_rows),
            "duplicate_observation_count": len(keyword_all_valid) - len(keyword_rows),
            "aggregation_policy": "no_cross_series_addition",
        }
        candidates.append(candidate)

    return {"candidates": candidates, "invalid_rows": invalid_rows, "invalid_observation_count": len(invalid_rows), "duplicate_observation_count": duplicate_observation_count}


def emit(result: dict[str, Any], fmt: str) -> None:
    if fmt == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return
    rows = result["candidates"]
    if not rows:
        return
    fields = sorted({key for row in rows for key in row})
    writer = csv.DictWriter(__import__("sys").stdout, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        serial = dict(row)
        for key, value in serial.items():
            if isinstance(value, (list, dict)):
                serial[key] = json.dumps(value, ensure_ascii=False)
            elif value is None:
                serial[key] = ""
        writer.writerow(serial)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--format", choices=("json", "csv"), default="json")
    parser.add_argument("--as-of")
    args = parser.parse_args()
    as_of = end_of_day(args.as_of)
    result = aggregate(load_rows(Path(args.input)), as_of)
    emit(result, args.format)


if __name__ == "__main__":
    main()
