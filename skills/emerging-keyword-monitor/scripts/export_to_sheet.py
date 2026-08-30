#!/usr/bin/env python3
"""Export the Emerging Keyword Radar database to a Google Sheet.

This is an export layer, not a data source. The authoritative outputs stay the
local ``emerging-keywords.json`` / ``.csv`` written by ``update_emerging_database``.
Nothing here participates in stage contracts, evidence receipts, or the pipeline
source-hash binding, so a Sheet failure never changes whether a radar run is
valid -- it only means the mirror is stale.

Two invariants are enforced while building rows:

1. ``unknown`` stays ``unknown``. A missing metric is never rendered as an empty
   cell or as ``0``; that collapse is the exact failure this repository exists to
   prevent.
2. Google's own ``Breakout`` label is exported in its own column and is never
   merged into the classifier's ``signal_type``/``status``. They answer different
   questions and Google's label is a source fact, not a verdict.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable, Protocol

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from update_emerging_database import canonical_keyword, load_database

UNKNOWN = "unknown"

# (header, record field). Order is the column order in the sheet.
COLUMNS: tuple[tuple[str, str], ...] = (
    ("Domain", "domain"),
    ("Keyword", "keyword"),
    ("Discovery source", "discovery_source"),
    ("Discovery depth", "discovery_depth"),
    ("Parent anchor", "parent_anchor"),
    ("First observed", "first_observed_at"),
    ("Birth window", "estimated_birth_window"),
    ("Birth confidence", "birth_confidence"),
    ("Birth reason", "birth_reason"),
    ("Demand history", "demand_history_type"),
    ("Growth rate", "growth_rate"),
    ("Growth status", "growth_status"),
    ("Persistence", "persistence"),
    ("Signal type (classifier)", "signal_type"),
    ("Status (classifier)", "status"),
    ("Confidence", "confidence"),
    ("Google rising label (source)", "google_rising_label"),
    ("Google breakout flag (source)", "is_google_breakout"),
    ("Root id", "root_id"),
    ("Root relation", "root_relation"),
    ("Volume", "volume"),
    ("KD", "kd"),
    ("Metric status", "metric_status"),
    ("Route", "route"),
    ("Route reason", "route_reason"),
    ("Previous status", "previous_status"),
    ("Last seen", "last_seen_at"),
)

HEADER: list[str] = [header for header, _ in COLUMNS]
KEY_COLUMNS = 2  # Domain + Keyword identify a row.


class SheetClient(Protocol):
    """Minimal worksheet surface, satisfied by a gspread worksheet."""

    def get_all_values(self) -> list[list[str]]: ...

    def update(self, range_name: str, values: list[list[Any]]) -> Any: ...

    def append_rows(self, values: list[list[Any]]) -> Any: ...


def format_cell(value: Any) -> str:
    """Render one value without ever collapsing unknown into blank or zero."""
    if value is None:
        return UNKNOWN
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        text = value.strip()
        return text if text else UNKNOWN
    if isinstance(value, (int, float)):
        return repr(value) if isinstance(value, float) else str(value)
    if isinstance(value, (list, dict)):
        if not value:
            return UNKNOWN
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def build_row(record: dict[str, Any]) -> list[str]:
    return [format_cell(record.get(field)) for _, field in COLUMNS]


def build_rows(database: dict[str, Any]) -> list[list[str]]:
    """Build one row per database record, ordered by domain then keyword."""
    records = database.get("records") if isinstance(database, dict) else None
    if not isinstance(records, list):
        raise ValueError("database must contain a records list")
    rows = []
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("database records must be objects")
        if not canonical_keyword(record.get("keyword")):
            raise ValueError("database record is missing a keyword")
        rows.append(build_row(record))
    rows.sort(key=lambda row: (row[0].casefold(), row[1].casefold()))
    return rows


def _row_key(row: list[str]) -> tuple[str, str]:
    domain = canonical_keyword(row[0]) if len(row) > 0 else ""
    keyword = canonical_keyword(row[1]) if len(row) > 1 else ""
    return domain, keyword


def _a1(row_number: int, width: int) -> str:
    last = ""
    index = width
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        last = chr(ord("A") + remainder) + last
    return f"A{row_number}:{last}{row_number}"


def plan_writes(existing: list[list[str]], rows: list[list[str]]) -> dict[str, Any]:
    """Decide header/update/append operations without touching the network."""
    header_needed = not existing or [cell.strip() for cell in existing[0]] != HEADER
    index: dict[tuple[str, str], int] = {}
    if existing and not header_needed:
        for offset, row in enumerate(existing[1:], start=2):
            key = _row_key(row)
            if key != ("", ""):
                index.setdefault(key, offset)

    updates: list[tuple[str, list[str]]] = []
    appends: list[list[str]] = []
    for row in rows:
        target = index.get(_row_key(row))
        if target is None:
            appends.append(row)
        else:
            updates.append((_a1(target, len(HEADER)), row))
    return {"header_needed": header_needed, "updates": updates, "appends": appends}


def export(client: SheetClient, database: dict[str, Any]) -> dict[str, Any]:
    """Upsert every record by (domain, keyword); never append a duplicate row."""
    rows = build_rows(database)
    existing = client.get_all_values() or []
    plan = plan_writes(existing, rows)

    if plan["header_needed"]:
        client.update(_a1(1, len(HEADER)), [HEADER])
    for range_name, row in plan["updates"]:
        client.update(range_name, [row])
    if plan["appends"]:
        client.append_rows(plan["appends"])

    return {
        "status": "PASS",
        "record_count": len(rows),
        "updated_count": len(plan["updates"]),
        "appended_count": len(plan["appends"]),
        "header_written": plan["header_needed"],
    }


def open_worksheet(sheet_id: str, worksheet: str, credentials: str) -> SheetClient:
    """Open a gspread worksheet. Imported lazily so the pure logic needs no deps."""
    try:
        import gspread
    except ImportError as exc:  # pragma: no cover - depends on optional install
        raise RuntimeError(
            "gspread is not installed; install it or run with --dry-run"
        ) from exc
    client = gspread.service_account(filename=credentials)
    spreadsheet = client.open_by_key(sheet_id)
    try:
        return spreadsheet.worksheet(worksheet)
    except Exception:
        return spreadsheet.add_worksheet(title=worksheet, rows=1000, cols=len(HEADER))


def main(worksheet_factory: Callable[..., SheetClient] = open_worksheet) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, help="emerging-keywords.json")
    parser.add_argument("--sheet-id")
    parser.add_argument("--worksheet", default="Emerging Keywords")
    parser.add_argument("--credentials", help="Google service account JSON path")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="build and print the rows without contacting Google",
    )
    args = parser.parse_args()

    database = load_database(Path(args.database))
    if args.dry_run:
        rows = build_rows(database)
        print(json.dumps({"header": HEADER, "rows": rows}, ensure_ascii=False, indent=2))
        return 0

    missing = [name for name, value in (("--sheet-id", args.sheet_id), ("--credentials", args.credentials)) if not value]
    if missing:
        print(f"BLOCKED: {' and '.join(missing)} are required without --dry-run", file=sys.stderr)
        return 2

    try:
        worksheet = worksheet_factory(args.sheet_id, args.worksheet, args.credentials)
        result = export(worksheet, database)
    except Exception as exc:
        # The export is a mirror. Report the failure loudly and exit non-zero,
        # but never rewrite or invalidate the local authoritative outputs.
        print(f"BLOCKED: sheet export failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
