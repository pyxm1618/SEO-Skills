#!/usr/bin/env python3
"""Validate emerging-keyword observation rows without fabricating missing data."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

PROVENANCE_FIELDS = (
    "source",
    "source_type",
    "source_url",
    "observed_at",
    "country",
    "time_window",
)
NUMERIC_FIELDS = {
    "signal_value": (0.0, None, False),
    "volume": (0.0, None, False),
    "cpc": (0.0, None, False),
    "kd": (0.0, 100.0, False),
    "difficulty": (0.0, 100.0, False),
    "intitle_results": (0.0, None, True),
    "serp_dedicated_pages": (0.0, 10.0, True),
    "serp_ugc_pages": (0.0, 10.0, True),
}
NULL_STRINGS = {"", "unknown", "null", "none", "n/a", "na"}


def is_missing(value: Any) -> bool:
    if value is None:
        return True
    return isinstance(value, str) and value.strip().lower() in NULL_STRINGS


def normalize_text(value: Any) -> Any:
    if is_missing(value):
        return None
    if isinstance(value, str):
        return value.strip()
    return value


def parse_number(value: Any, *, integer: bool = False) -> tuple[Any, str | None]:
    if is_missing(value):
        return None, None
    if isinstance(value, bool):
        return value, "not_numeric"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value, "not_numeric"
    if not math.isfinite(number):
        return value, "not_finite"
    if integer:
        if not number.is_integer():
            return value, "not_integer"
        return int(number), None
    return number, None


def parse_iso(value: Any) -> tuple[datetime | None, str | None]:
    if is_missing(value):
        return None, None
    text = str(value).strip()
    try:
        if len(text) == 10:
            return datetime.combine(date.fromisoformat(text), datetime.min.time(), tzinfo=timezone.utc), None
        normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc), None
    except ValueError:
        return None, "invalid_date"


def canonical_keyword(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().lower().split())


def duplicate_key(row: dict[str, Any]) -> str:
    fields = (
        "keyword",
        "observed_at",
        "source",
        "source_type",
        "source_url",
        "root_id",
        "signal_value",
        "signal_unit",
        "country",
        "time_window",
        "metric_source",
        "metric_database",
    )
    values = []
    for field in fields:
        value = row.get(field)
        if field == "keyword":
            value = canonical_keyword(value)
        elif isinstance(value, str):
            value = value.strip().lower()
        values.append(value)
    return json.dumps(values, sort_keys=False, ensure_ascii=False, default=str)


def normalize_row(raw: dict[str, Any], as_of: datetime) -> dict[str, Any]:
    row = dict(raw)
    errors: list[str] = []

    for key, value in list(row.items()):
        if isinstance(value, str):
            row[key] = normalize_text(value)

    keyword = normalize_text(row.get("keyword"))
    row["keyword"] = keyword
    if keyword is None or not str(keyword).strip():
        errors.append("keyword")

    for field, (minimum, maximum, integer) in NUMERIC_FIELDS.items():
        if field not in row:
            row[field] = None
            continue
        parsed, error = parse_number(row.get(field), integer=integer)
        row[field] = parsed
        if error:
            errors.append(field)
            continue
        if parsed is not None:
            if parsed < minimum:
                errors.append(field)
            if maximum is not None and parsed > maximum:
                errors.append(field)

    if row.get("kd") is None and row.get("difficulty") is not None:
        row["kd"] = row["difficulty"]
    if row.get("difficulty") is None and row.get("kd") is not None:
        row["difficulty"] = row["kd"]

    observed_dt, observed_error = parse_iso(row.get("observed_at"))
    if observed_error:
        errors.append("observed_at")
    elif observed_dt is not None and observed_dt > as_of:
        errors.append("observed_at_future")

    first_dt, first_error = parse_iso(row.get("first_observed_at"))
    if first_error:
        errors.append("first_observed_at")
    elif first_dt is not None:
        if first_dt > as_of:
            errors.append("first_observed_at_future")
        if observed_dt is not None and first_dt > observed_dt:
            errors.append("first_observed_at_after_observation")

    anchor_dt, anchor_error = parse_iso(row.get("anchor_event_date"))
    if anchor_error:
        errors.append("anchor_event_date")
    elif anchor_dt is not None and anchor_dt > as_of:
        # Future anchors may be planned events, so preserve them as data rather than invalidating.
        pass

    missing_provenance = [field for field in PROVENANCE_FIELDS if is_missing(row.get(field))]
    row["missing_provenance"] = missing_provenance
    row["provenance_status"] = "verified" if not missing_provenance else "incomplete"
    row["validation_errors"] = sorted(set(errors))
    row["validation_status"] = "invalid" if errors else "valid"
    return row


def validate_rows(rows: list[dict[str, Any]], as_of: datetime) -> list[dict[str, Any]]:
    normalized = [normalize_row(row, as_of) for row in rows]
    keys = [duplicate_key(row) for row in normalized]
    counts = Counter(keys)
    for row, key in zip(normalized, keys):
        row["duplicate_count"] = counts[key]
        row["duplicate_warning"] = counts[key] > 1
    return normalized


def load_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("observations", "rows"):
            if isinstance(payload.get(key), list):
                return payload[key]
    raise ValueError("input must be a JSON array/object with observations|rows, or CSV")


def emit(rows: list[dict[str, Any]], fmt: str) -> None:
    if fmt == "json":
        print(json.dumps({"rows": rows}, ensure_ascii=False, indent=2, allow_nan=False))
        return
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
    parser.add_argument("--as-of", help="ISO date/datetime used for future-date validation")
    args = parser.parse_args()
    if args.as_of:
        as_of, error = parse_iso(args.as_of)
        if error or as_of is None:
            raise SystemExit("--as-of must be a valid ISO date/datetime")
        if len(args.as_of.strip()) == 10:
            as_of = as_of.replace(hour=23, minute=59, second=59, microsecond=999999)
    else:
        as_of = datetime.now(timezone.utc)
    rows = validate_rows(load_rows(Path(args.input)), as_of)
    emit(rows, args.format)


if __name__ == "__main__":
    main()
