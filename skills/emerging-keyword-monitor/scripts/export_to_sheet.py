#!/usr/bin/env python3
"""Mirror Emerging Keyword Radar records into the unified keyword library.

The authoritative Emerging outputs remain the local JSON/CSV database. This is
an optional human-facing output layer: a Sheet failure never changes whether a
Radar run is valid and never rewrites the local database.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable, Protocol

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from update_emerging_database import canonical_keyword, load_database

REPO_ROOT = Path(__file__).resolve().parents[3]
LIBRARY_PATH = REPO_ROOT / "runtime" / "keyword_library_sheet.py"
DEFAULT_WORKSHEET = "关键词库"


def _load_library():
    spec = importlib.util.spec_from_file_location("seo_keyword_library_sheet_for_emerging", LIBRARY_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


library = _load_library()


class SheetClient(Protocol):
    def get_all_values(self) -> list[list[str]]: ...

    def update(self, range_name: str, values: list[list[Any]]) -> Any: ...

    def append_rows(self, values: list[list[Any]]) -> Any: ...


def expand_path(value: str) -> str:
    return os.path.expanduser(os.path.expandvars(str(value)))


def _records(database: dict[str, Any]) -> list[dict[str, Any]]:
    records = database.get("records") if isinstance(database, dict) else None
    if not isinstance(records, list):
        raise ValueError("database must contain a records list")
    out: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("database records must be objects")
        if not canonical_keyword(record.get("keyword")):
            raise ValueError("database record is missing a keyword")
        out.append(dict(record))
    return out


def build_identity_summary(
    database: dict[str, Any],
    delivery_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    records = _records(database)
    identities = [
        library.resolve_identity(
            record,
            run_context=database,
            delivery_context=delivery_context,
        )
        for record in records
    ]
    return {
        "record_count": len(records),
        "stable_row_count": len({identity.stable_key for identity in identities}),
        "stable_keys": [identity.stable_key for identity in identities],
    }


def export(
    client: SheetClient,
    database: dict[str, Any],
    delivery_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Patch Emerging-owned fields in stable keyword rows only."""
    records = _records(database)
    return library.upsert_records(
        client,
        "emerging",
        records,
        run_context=database,
        delivery_context=delivery_context,
    )


def open_worksheet(sheet_id: str, worksheet: str, credentials: str) -> SheetClient:
    return library.open_worksheet(sheet_id, worksheet, credentials)


def main(worksheet_factory: Callable[..., SheetClient] = open_worksheet) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, help="emerging-keywords.json")
    parser.add_argument("--sheet-id")
    parser.add_argument(
        "--worksheet",
        default=os.environ.get("SEO_KEYWORD_LIBRARY_WORKSHEET", DEFAULT_WORKSHEET),
    )
    parser.add_argument("--credentials", help="Google service account JSON path")
    parser.add_argument("--market", help="explicit delivery market when record/run metadata does not carry one")
    parser.add_argument("--language", help="explicit delivery language when record/run metadata does not carry one")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="resolve stable identities without contacting Google",
    )
    args = parser.parse_args()

    try:
        database = load_database(Path(expand_path(args.database)))
        context = library.delivery_context_from_env(args.market, args.language)
        summary = build_identity_summary(database, delivery_context=context)
    except Exception as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2

    if args.dry_run:
        print(
            json.dumps(
                {"worksheet": args.worksheet, **summary},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    sheet_id = args.sheet_id or os.environ.get("SEO_KEYWORD_SHEET_ID")
    credentials = args.credentials or os.environ.get("SEO_SHEETS_CREDENTIALS")
    missing = [
        name
        for name, value in (
            ("--sheet-id/SEO_KEYWORD_SHEET_ID", sheet_id),
            ("--credentials/SEO_SHEETS_CREDENTIALS", credentials),
        )
        if not value
    ]
    if missing:
        print(f"BLOCKED: {' and '.join(missing)} are required without --dry-run", file=sys.stderr)
        return 2

    try:
        worksheet = worksheet_factory(sheet_id, args.worksheet, credentials)
        result = export(worksheet, database, delivery_context=context)
        result["worksheet"] = args.worksheet
    except Exception as exc:
        # Mirror failure remains output-only. Local JSON/CSV is authoritative
        # and is deliberately never mutated here.
        print(f"BLOCKED: sheet export failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
