#!/usr/bin/env python3
"""Persist Emerging Keyword Radar records without collapsing unknown values."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def canonical_keyword(value: Any) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def is_missing(value: Any) -> bool:
    return value is None or (
        isinstance(value, str)
        and value.strip().casefold() in {"", "unknown", "null", "none", "n/a", "na"}
    )


def _date_key(value: Any) -> datetime | None:
    if is_missing(value):
        return None
    text = str(value).strip()
    try:
        normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _earliest(left: Any, right: Any) -> Any:
    left_dt = _date_key(left)
    right_dt = _date_key(right)
    if left_dt is None:
        return right
    if right_dt is None:
        return left
    return left if left_dt <= right_dt else right


def _record_key(record: dict[str, Any]) -> tuple[str, str]:
    return canonical_keyword(record.get("domain")), canonical_keyword(record.get("keyword"))


def _route_index(routes: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    indexed: dict[tuple[str, str], dict[str, Any]] = {}
    for route in routes:
        if not isinstance(route, dict):
            continue
        keyword = canonical_keyword(route.get("keyword"))
        if not keyword:
            continue
        indexed[(canonical_keyword(route.get("domain")), keyword)] = route
        indexed.setdefault(("", keyword), route)
    return indexed


def _history_entry(record: dict[str, Any], route: dict[str, Any] | None) -> dict[str, Any]:
    entry = {
        "observed_at": record.get("last_seen_at") or record.get("observed_at"),
        "status": record.get("status"),
        "signal_type": record.get("signal_type"),
        "confidence": record.get("confidence"),
        "source_evidence": record.get("source_evidence"),
    }
    if route is not None:
        entry["route"] = route.get("route")
    return entry


def merge_database(
    existing: dict[str, Any] | None,
    classified_candidates: list[dict[str, Any]],
    routes: list[dict[str, Any]],
    discovered_at: str,
) -> dict[str, Any]:
    """Merge current classified snapshots while retaining prior state and evidence."""
    existing_payload = existing if isinstance(existing, dict) else {}
    current_records = existing_payload.get("records")
    if not isinstance(current_records, list):
        current_records = []

    records: dict[tuple[str, str], dict[str, Any]] = {}
    for old_record in current_records:
        if not isinstance(old_record, dict):
            raise ValueError("database records must be objects")
        key = _record_key(old_record)
        if not key[0] or not key[1]:
            raise ValueError("database records require domain and keyword")
        records[key] = dict(old_record)

    route_by_key = _route_index(routes)
    for candidate in classified_candidates:
        if not isinstance(candidate, dict):
            raise ValueError("classified candidates must be objects")
        key = _record_key(candidate)
        if not key[0] or not key[1]:
            raise ValueError("classified candidates require domain and keyword")

        route = route_by_key.get(key) or route_by_key.get(("", key[1]))
        previous = records.get(key)
        record = dict(candidate)
        record["domain"] = candidate.get("domain")
        record["keyword"] = candidate.get("keyword")
        if previous is None:
            record["previous_status"] = None
            record["previous_source_evidence"] = None
            record["status_history"] = list(candidate.get("status_history") or [])
        else:
            record["first_observed_at"] = _earliest(
                previous.get("first_observed_at"), candidate.get("first_observed_at")
            )
            record["previous_status"] = previous.get("status")
            record["previous_source_evidence"] = previous.get("source_evidence")
            history = list(previous.get("status_history") or [])
            if not is_missing(previous.get("status")):
                history.append(_history_entry(previous, route))
            record["status_history"] = history

        record["last_seen_at"] = discovered_at
        if route is not None:
            record["route"] = route.get("route")
            record["route_reason"] = route.get("route_reason")
            record["route_handoff"] = route.get("handoff")
        records[key] = record

    ordered = [records[key] for key in sorted(records)]
    schema_version = existing_payload.get("schema_version", 1)
    return {
        "schema_version": schema_version,
        "updated_at": discovered_at,
        "records": ordered,
    }


def _serial_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if value is None:
        return ""
    return value


def write_database(database: dict[str, Any], database_path: Path, csv_path: Path) -> None:
    """Write JSON and a flat CSV while leaving unknown values blank in CSV."""
    database_path = Path(database_path)
    csv_path = Path(csv_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    database_path.write_text(
        json.dumps(database, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )

    records = database.get("records") if isinstance(database, dict) else []
    records = records if isinstance(records, list) else []
    fields = sorted({key for record in records if isinstance(record, dict) for key in record})
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        if not fields:
            return
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in records:
            writer.writerow({field: _serial_value(record.get(field)) for field in fields})


def load_database(path: Path) -> dict[str, Any]:
    if not Path(path).exists():
        return {"schema_version": 1, "records": []}
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("records", []), list):
        raise ValueError("database must be an object with a records list")
    return payload


def _load_list(path: Path, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in keys:
            if isinstance(payload.get(key), list):
                return payload[key]
    raise ValueError(f"{path} must contain one of {', '.join(keys)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="classified candidate JSON")
    parser.add_argument("--routes", required=True, help="route JSON")
    parser.add_argument("--database", required=True)
    parser.add_argument("--csv", required=True)
    parser.add_argument("--discovered-at", default=datetime.now(timezone.utc).isoformat())
    args = parser.parse_args()
    database = merge_database(
        load_database(Path(args.database)),
        _load_list(Path(args.input), ("candidates", "rows")),
        _load_list(Path(args.routes), ("routes", "rows")),
        args.discovered_at,
    )
    write_database(database, Path(args.database), Path(args.csv))


if __name__ == "__main__":
    main()
