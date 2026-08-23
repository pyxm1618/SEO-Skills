#!/usr/bin/env python3
"""Aggregate comparable emerging-demand signal series without cross-unit arithmetic."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
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


def historical_first_dt(row: dict[str, Any]) -> datetime | None:
    parsed, error = parse_iso(row.get("first_observed_at"))
    return None if error else parsed


def mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def persistence_stats(values: list[float]) -> tuple[float | None, int, int]:
    if not values:
        return None, 0, 0
    positive_count = sum(value > 0 for value in values)
    return positive_count / len(values), len(values), positive_count


def window_values(points: list[tuple[datetime, float]], as_of: datetime, min_days_ago: int, max_days_ago: int) -> list[float]:
    values: list[float] = []
    for observed, value in points:
        days_ago = (as_of.date() - observed.date()).days
        if min_days_ago <= days_ago <= max_days_ago:
            values.append(value)
    return values


def growth_stats(recent_values: list[float], baseline_values: list[float]) -> tuple[float | None, str]:
    recent = mean(recent_values)
    baseline = mean(baseline_values)
    if recent is None or baseline is None:
        return None, "unknown"
    if baseline > 0:
        return (recent - baseline) / baseline, "calculated"
    if baseline == 0 and recent > 0:
        return None, "from_observed_zero_baseline"
    if baseline == 0 and recent == 0:
        return 0.0, "calculated"
    return None, "unknown"


def positive_history(
    points: list[tuple[datetime, float]],
    as_of: datetime,
    min_days_ago: int,
) -> tuple[bool, int, list[str]]:
    positive_days: list[int] = []
    for observed, value in points:
        days_ago = (as_of.date() - observed.date()).days
        if min_days_ago <= days_ago <= 364 and value > 0:
            positive_days.append(days_ago)

    windows: set[str] = set()
    for days_ago in positive_days:
        if days_ago <= 89:
            windows.add(f"days_{min_days_ago}_89")
        elif days_ago <= 179:
            windows.add("days_90_179")
        else:
            windows.add("days_180_364")
    return bool(positive_days), len(positive_days), sorted(windows)


def latest_non_missing(rows: list[dict[str, Any]], field: str) -> Any:
    ordered = sorted(rows, key=lambda row: row_dt(row) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    for row in ordered:
        value = row.get(field)
        if not is_missing(value):
            return value
    return None


def latest_metric_record(rows: list[dict[str, Any]], field: str) -> dict[str, Any] | None:
    ordered = sorted(rows, key=lambda row: row_dt(row) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    for row in ordered:
        value = row.get(field)
        if is_missing(value):
            continue
        observed = row_dt(row)
        return {
            "value": value,
            "source": row.get("source"),
            "metric_source": row.get("metric_source"),
            "metric_database": row.get("metric_database"),
            "country": row.get("country"),
            "observed_at": observed.date().isoformat() if observed else row.get("observed_at"),
        }
    return None


def normalized_context_value(value: Any) -> str | None:
    if is_missing(value):
        return None
    return str(value).strip().lower()


def metric_compatibility_status(records: dict[str, dict[str, Any] | None]) -> str:
    present = [record for record in records.values() if isinstance(record, dict)]
    if not present:
        return "unknown"

    for record in present:
        if any(
            normalized_context_value(record.get(field)) is None
            for field in ("metric_source", "metric_database", "country")
        ):
            return "insufficient_context"

    sources = {normalized_context_value(record.get("metric_source")) for record in present}
    countries = {normalized_context_value(record.get("country")) for record in present}
    databases = {normalized_context_value(record.get("metric_database")) for record in present}
    if len(sources) > 1 or len(countries) > 1 or len(databases) > 1:
        return "mixed_context"
    return "compatible"


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

    baseline_90_7d_values = window_values(points, as_of, 7, 89)
    baseline_90_30d_values = window_values(points, as_of, 30, 89)
    baseline_12m_7d_values = window_values(points, as_of, 7, 364)
    baseline_12m_30d_values = window_values(points, as_of, 30, 364)

    growth_7d, growth_status_7d = growth_stats(recent_7, baseline_90_7d_values)
    growth_30d, growth_status_30d = growth_stats(recent_30, baseline_90_30d_values)

    recent_7_mean = mean(recent_7)
    previous_7_mean = mean(previous_7)
    prior_7_mean = mean(prior_7)

    acceleration = None
    if recent_7_mean is not None and previous_7_mean is not None and prior_7_mean is not None:
        acceleration = (recent_7_mean - previous_7_mean) - (previous_7_mean - prior_7_mean)

    persistence_7d, recent_7d_observations, positive_7d_observations = persistence_stats(recent_7)
    persistence_30d, recent_30d_observations, positive_30d_observations = persistence_stats(recent_30)

    # Preserve the short-window default for compatibility. Classification can select
    # the 30-day evidence when 7-day depth is insufficient, and then uses the matching
    # non-overlapping 30-day baseline fields below.
    default_is_7d = bool(recent_7)
    persistence_values = recent_7 if default_is_7d else recent_30
    persistence_window = "recent_7d" if default_is_7d else ("recent_30d" if recent_30 else None)
    persistence = persistence_7d if default_is_7d else persistence_30d
    positive_count = positive_7d_observations if default_is_7d else positive_30d_observations
    baseline_values = baseline_90_7d_values if default_is_7d else baseline_90_30d_values
    baseline_12m_values = baseline_12m_7d_values if default_is_7d else baseline_12m_30d_values
    recent_values = recent_7 if default_is_7d else recent_30
    growth = growth_7d if default_is_7d else growth_30d
    growth_status = growth_status_7d if default_is_7d else growth_status_30d

    historical_7d_seen, historical_7d_count, historical_7d_windows = positive_history(points, as_of, 7)
    historical_30d_seen, historical_30d_count, historical_30d_windows = positive_history(points, as_of, 30)
    historical_seen = historical_7d_seen if default_is_7d else historical_30d_seen
    historical_count = historical_7d_count if default_is_7d else historical_30d_count
    historical_windows = historical_7d_windows if default_is_7d else historical_30d_windows

    observed_days = sorted({dt.date() for dt, _ in points})
    latest_dt = max((dt for dt, _ in points), default=None)
    latest_age_days = (as_of.date() - latest_dt.date()).days if latest_dt else None
    recent_30_days = {
        dt.date()
        for dt, _ in points
        if 0 <= (as_of.date() - dt.date()).days <= 29
    }
    coverage_ratio = len(recent_30_days) / 30.0
    gaps = [(right - left).days for left, right in zip(observed_days, observed_days[1:])]
    max_gap = max(gaps) if gaps else None

    provenance_status = "verified" if rows and all(r.get("provenance_status") == "verified" for r in rows) else "incomplete"
    observed_first = min((dt for dt, _ in points), default=None)
    carried_first = min((historical_first_dt(row) for row in rows if historical_first_dt(row) is not None), default=None)
    first_dt = min((dt for dt in (observed_first, carried_first) if dt is not None), default=None)
    trend_status = latest_non_missing(rows, "trend_status")

    return {
        "source": key[0],
        "source_type": key[1],
        "country": key[2],
        "signal_unit": key[3],
        "metric_database": key[4],
        "time_window": key[5],
        "observation_count": len(points),
        "first_observed_at": first_dt.date().isoformat() if first_dt else None,
        "last_observed_at": latest_dt.date().isoformat() if latest_dt else None,
        "latest_observation_age_days": latest_age_days,
        "distinct_observation_days": len(observed_days),
        "coverage_ratio": coverage_ratio,
        "max_observation_gap_days": max_gap,
        "recent_7d": recent_7_mean,
        "previous_7d": previous_7_mean,
        "recent_30d": mean(recent_30),
        "previous_30d": mean(previous_30),
        "baseline_90d_7d": mean(baseline_90_7d_values),
        "baseline_90d_30d": mean(baseline_90_30d_values),
        "baseline_7d_observations": len(baseline_90_7d_values),
        "baseline_30d_observations": len(baseline_90_30d_values),
        "baseline_12m_7d": mean(baseline_12m_7d_values),
        "baseline_12m_30d": mean(baseline_12m_30d_values),
        "growth_rate_7d": growth_7d,
        "growth_status_7d": growth_status_7d,
        "growth_rate_30d": growth_30d,
        "growth_status_30d": growth_status_30d,
        "baseline_90d": mean(baseline_values),
        "baseline_12m": mean(baseline_12m_values),
        "baseline_signal": mean(baseline_values),
        "baseline_observations": len(baseline_values),
        "novelty_baseline_7d": mean(baseline_90_7d_values),
        "novelty_baseline_7d_observations": len(baseline_90_7d_values),
        "novelty_baseline_30d": mean(baseline_90_30d_values),
        "novelty_baseline_30d_observations": len(baseline_90_30d_values),
        "historical_positive_7d_seen": historical_7d_seen,
        "historical_positive_7d_observations": historical_7d_count,
        "historical_positive_7d_windows": historical_7d_windows,
        "historical_positive_30d_seen": historical_30d_seen,
        "historical_positive_30d_observations": historical_30d_count,
        "historical_positive_30d_windows": historical_30d_windows,
        "historical_positive_seen": historical_seen,
        "historical_positive_observations": historical_count,
        "historical_positive_windows": historical_windows,
        "recent_signal": mean(recent_values),
        "recent_observations": len(recent_values),
        "recent_7d_observations": recent_7d_observations,
        "recent_30d_observations": recent_30d_observations,
        "growth_rate": growth,
        "growth_status": growth_status,
        "acceleration": acceleration,
        "persistence": persistence,
        "persistence_window": persistence_window,
        "persistence_observations": len(persistence_values),
        "persistence_7d": persistence_7d,
        "persistence_30d": persistence_30d,
        "positive_observations": positive_count,
        "positive_7d_observations": positive_7d_observations,
        "positive_30d_observations": positive_30d_observations,
        "peak_signal": max((value for _, value in points), default=None),
        "latest_signal": points[-1][1] if points else None,
        "trend_status": trend_status,
        "provenance_status": provenance_status,
    }


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
        carried_first_dates = [historical_first_dt(row) for row in keyword_rows if historical_first_dt(row) is not None]
        first_dt = min((dt for dt in observed_dates + carried_first_dates if dt is not None), default=None)
        last_dt = max(observed_dates, default=None)
        root_ids = sorted({str(row.get("root_id")).strip() for row in keyword_rows if not is_missing(row.get("root_id"))})
        sources = {str(row.get("source")).strip() for row in keyword_rows if not is_missing(row.get("source"))}

        metric_provenance = {field: latest_metric_record(keyword_all_valid, field) for field in METRIC_FIELDS}
        metrics = {
            field: metric_provenance[field]["value"] if isinstance(metric_provenance[field], dict) else None
            for field in METRIC_FIELDS
        }
        core_metric_provenance = {field: metric_provenance[field] for field in ("volume", "kd", "cpc")}
        compatibility = metric_compatibility_status(core_metric_provenance)
        required_complete = all(metrics[field] is not None for field in ("volume", "kd", "cpc"))
        if required_complete and compatibility == "compatible":
            metric_status = "complete"
        elif required_complete and compatibility == "mixed_context":
            metric_status = "incompatible"
        else:
            metric_status = "incomplete"

        context = {field: latest_non_missing(keyword_all_valid, field) for field in CONTEXT_FIELDS}
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
            "persistence_window": primary.get("persistence_window") if primary else None,
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
            "metric_provenance": metric_provenance,
            "metric_compatibility_status": compatibility,
            "serp_dedicated_pages": context["serp_dedicated_pages"],
            "serp_ugc_pages": context["serp_ugc_pages"],
            "serp_intent_mismatch": context["serp_intent_mismatch"],
            "emd_status": context["emd_status"],
            "durable_search_intent": context["durable_search_intent"],
            "repeatable_page_or_product_fit": context["repeatable_page_or_product_fit"],
            "trend_status": primary.get("trend_status") if primary else latest_non_missing(keyword_all_valid, "trend_status"),
            "metric_status": metric_status,
            "observed_at": last_dt.date().isoformat() if last_dt else None,
            "unique_observation_count": len(keyword_rows),
            "duplicate_observation_count": len(keyword_all_valid) - len(keyword_rows),
            "aggregation_policy": "no_cross_series_addition",
        }
        candidates.append(candidate)

    return {
        "candidates": candidates,
        "invalid_rows": invalid_rows,
        "invalid_observation_count": len(invalid_rows),
        "duplicate_observation_count": duplicate_observation_count,
    }


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
