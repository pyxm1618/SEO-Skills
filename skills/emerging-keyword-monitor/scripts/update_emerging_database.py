#!/usr/bin/env python3
"""Persist Emerging Keyword Radar records without collapsing unknown values."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timedelta, timezone
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


WATCHING_STATUSES = frozenset({"new_signal", "watch", "insufficient_evidence"})
GRADUATING_STATUSES = frozenset({"emerging", "breakout"})
RETIRING_STATUSES = frozenset({"noise", "mature"})
CONFIRMED_CLASSIFIER_STATUSES = WATCHING_STATUSES | GRADUATING_STATUSES | RETIRING_STATUSES
ACQUISITION_FAILURE_STATES = frozenset({"failed", "not_attempted", "pending_evidence"})
MAX_ACQUISITION_FAILURES = 3
RETRY_INTERVAL_DAYS = 7


def observation_state(status: Any) -> str:
    """Derive the lifecycle bucket from the last confirmed classifier status."""
    value = str(status or "").strip()
    if value in GRADUATING_STATUSES:
        return "graduated"
    if value in RETIRING_STATUSES:
        return "retired"
    if value in WATCHING_STATUSES:
        return "watching"
    return "watching"


def carry_forward(database: dict[str, Any], include_graduated: bool = False,
                  include_retired: bool = False) -> list[dict[str, Any]]:
    """Records the next run should observe again, with their prior confirmed state.

    A paused acquisition retry is deliberately not converted into ``noise`` or
    deletion.  It stays in the database for human review; default automatic
    carry-forward resumes only when it is not paused.
    """
    records = database.get("records") if isinstance(database, dict) else []
    out = []
    for record in records if isinstance(records, list) else []:
        if not isinstance(record, dict):
            continue
        if record.get("monitoring_state") == "paused_review":
            continue
        state = record.get("observation_state") or observation_state(record.get("status"))
        if state == "graduated" and not include_graduated:
            continue
        if state == "retired" and not include_retired:
            continue
        out.append(
            {
                "domain": record.get("domain"),
                "keyword": record.get("keyword"),
                "root_id": record.get("root_id"),
                "previous_status": record.get("last_confirmed_status") or record.get("status"),
                "first_observed_at": record.get("first_observed_at"),
                "observation_count": record.get("observation_count"),
                "acquisition_failure_count": record.get("acquisition_failure_count", 0),
                "next_review_at": record.get("next_review_at"),
            }
        )
    out.sort(key=lambda row: (canonical_keyword(row["domain"]), canonical_keyword(row["keyword"])))
    return out


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


def _has_confirmed_classification(candidate: dict[str, Any]) -> bool:
    current = str(candidate.get("current_classification_status") or "").strip().casefold()
    if current in {"confirmed", "valid"}:
        return True
    if current in {"unknown", "failed", "not_run", "pending"}:
        return False
    acquisition = str(candidate.get("acquisition_status") or "").strip().casefold()
    if acquisition in ACQUISITION_FAILURE_STATES:
        return False
    # Backward compatibility: historical callers pass canonical ``status``
    # without the newer acquisition fields.  Those remain real classifications.
    return str(candidate.get("status") or "").strip() in CONFIRMED_CLASSIFIER_STATUSES


def _next_review(discovered_at: str, failure_count: int) -> str | None:
    if failure_count >= MAX_ACQUISITION_FAILURES:
        return None
    observed = _date_key(discovered_at) or datetime.now(timezone.utc)
    return (observed + timedelta(days=RETRY_INTERVAL_DAYS)).isoformat()


def _merge_acquisition_failure(
    previous: dict[str, Any] | None,
    candidate: dict[str, Any],
    discovered_at: str,
) -> dict[str, Any]:
    """Persist current collection state without replacing a prior verdict."""
    record = dict(previous or {})
    previous_confirmed_status = (
        (previous or {}).get("last_confirmed_status")
        or (previous or {}).get("status")
    )
    previous_confirmed_evidence = (
        (previous or {}).get("last_confirmed_source_evidence")
        or (previous or {}).get("source_evidence")
    )
    previous_confirmed_at = (
        (previous or {}).get("last_confirmed_at")
        or (previous or {}).get("last_seen_at")
    )

    # Only current-run operational/domain fields may overwrite the stored row.
    for field in (
        "domain",
        "keyword",
        "candidate_id",
        "domain_relation",
        "domain_relation_reason",
        "root_id",
        "root_relation",
        "parent_anchor",
        "discovery_source",
        "acquisition_status",
        "acquisition_reason",
        "failure_type",
        "verification_status",
        "screenshot_status",
        "raw_evidence_ref",
        "delivery_eligible",
        "final_disposition",
    ):
        if field in candidate:
            record[field] = candidate.get(field)

    record["last_seen_at"] = discovered_at
    record["last_run_acquisition_status"] = candidate.get("acquisition_status") or "failed"
    record["last_run_acquisition_reason"] = candidate.get("acquisition_reason") or candidate.get("failure_type")
    record["current_classification_status"] = "unknown"
    record["last_confirmed_status"] = previous_confirmed_status
    record["last_confirmed_source_evidence"] = previous_confirmed_evidence
    record["last_confirmed_at"] = previous_confirmed_at
    if previous_confirmed_status is not None:
        record["status"] = previous_confirmed_status
        record["source_evidence"] = previous_confirmed_evidence
        record["observation_state"] = observation_state(previous_confirmed_status)
    else:
        record.pop("status", None)
        record.setdefault("source_evidence", [])
        record["observation_state"] = "watching"

    failure_count = int((previous or {}).get("acquisition_failure_count") or 0) + 1
    record["acquisition_failure_count"] = failure_count
    if failure_count >= MAX_ACQUISITION_FAILURES:
        record["monitoring_state"] = "paused_review"
        record["next_review_at"] = None
    else:
        record["monitoring_state"] = "retry_scheduled"
        record["next_review_at"] = _next_review(discovered_at, failure_count)
    record["delivery_eligible"] = False
    record["observation_count"] = int((previous or {}).get("observation_count") or 0)
    record.setdefault("status_history", list((previous or {}).get("status_history") or []))
    return record


def merge_database(
    existing: dict[str, Any] | None,
    classified_candidates: list[dict[str, Any]],
    routes: list[dict[str, Any]],
    discovered_at: str,
) -> dict[str, Any]:
    """Merge current snapshots while retaining prior confirmed state/evidence.

    Acquisition state and classifier state are independent.  A current browser,
    screenshot, or response-capture failure can never replace the last confirmed
    ``mature``/``watch``/``emerging`` verdict with ``insufficient_evidence``.
    """
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
        if not _has_confirmed_classification(candidate):
            records[key] = _merge_acquisition_failure(previous, candidate, discovered_at)
            continue

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
            record["previous_status"] = previous.get("last_confirmed_status") or previous.get("status")
            record["previous_source_evidence"] = previous.get("last_confirmed_source_evidence") or previous.get("source_evidence")
            history = list(previous.get("status_history") or [])
            if not is_missing(previous.get("status")):
                history.append(_history_entry(previous, route))
            record["status_history"] = history

        record["last_seen_at"] = discovered_at
        record["observation_count"] = int(previous.get("observation_count") or 0) + 1 if previous else 1
        record["observation_state"] = observation_state(candidate.get("status"))
        record["current_classification_status"] = "confirmed"
        record["last_confirmed_status"] = candidate.get("status")
        record["last_confirmed_source_evidence"] = candidate.get("source_evidence")
        record["last_confirmed_at"] = discovered_at
        record["last_run_acquisition_status"] = candidate.get("acquisition_status") or "data_acquired"
        record["last_run_acquisition_reason"] = candidate.get("acquisition_reason")
        record["acquisition_failure_count"] = 0
        record["monitoring_state"] = record["observation_state"]
        record["next_review_at"] = None
        if route is not None:
            record["route"] = route.get("route")
            record["route_reason"] = route.get("route_reason")
            record["route_handoff"] = route.get("handoff")
        records[key] = record

    ordered = [records[key] for key in sorted(records)]
    payload = {
        key: value
        for key, value in existing_payload.items()
        if key not in {"records", "updated_at"}
    }
    payload.setdefault("schema_version", 1)
    payload["updated_at"] = discovered_at
    payload["records"] = ordered
    return payload


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
    parser.add_argument("--input", help="classified candidate JSON")
    parser.add_argument("--routes", help="route JSON")
    parser.add_argument("--database", required=True)
    parser.add_argument("--csv")
    parser.add_argument("--discovered-at", default=datetime.now(timezone.utc).isoformat())
    parser.add_argument(
        "--carry-forward",
        metavar="PATH",
        help=(
            "Write records eligible for the next observation batch. Graduated, retired, "
            "and acquisition-paused review records are excluded by default."
        ),
    )
    parser.add_argument("--include-graduated", action="store_true")
    parser.add_argument("--include-retired", action="store_true")
    args = parser.parse_args()

    if args.carry_forward:
        rows = carry_forward(
            load_database(Path(args.database)), args.include_graduated, args.include_retired
        )
        Path(args.carry_forward).parent.mkdir(parents=True, exist_ok=True)
        Path(args.carry_forward).write_text(
            json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"{len(rows)} records carried forward -> {args.carry_forward}")
        return

    if not args.input or not args.routes or not args.csv:
        parser.error("--input, --routes and --csv are required when merging")
    database = merge_database(
        load_database(Path(args.database)),
        _load_list(Path(args.input), ("candidates", "rows")),
        _load_list(Path(args.routes), ("routes", "rows")),
        args.discovered_at,
    )
    write_database(database, Path(args.database), Path(args.csv))


if __name__ == "__main__":
    main()
