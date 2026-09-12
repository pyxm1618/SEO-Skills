#!/usr/bin/env python3
"""Mirror delivery-eligible Emerging records into the unified keyword library.

The local Radar database is a monitoring database, not a delivery list.  This
module enforces run state and per-record delivery eligibility before any Sheet
client is touched.  A BLOCKED run may still be inspected with ``--dry-run`` but
can never perform a production Sheet mutation.
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


def _run_status(database: dict[str, Any], run_context: dict[str, Any] | None) -> str:
    context = run_context or {}
    value = context.get("status") or database.get("run_status")
    return str(value).strip().upper() if value not in (None, "") else "UNKNOWN"


def _candidate_id(record: dict[str, Any]) -> str | None:
    value = str(record.get("candidate_id") or "").strip()
    return value or None


def select_delivery_records(
    database: dict[str, Any],
    run_context: dict[str, Any] | None = None,
    *,
    allow_blocked_dry_run: bool = False,
) -> dict[str, Any]:
    """Resolve the Sheet delivery set and review set without touching a client.

    Production delivery is fail-closed: a run must explicitly be PASS and every
    database record must carry a delivery_eligible decision. Historical files
    can still be inspected with allow_blocked_dry_run=True, but that mode cannot
    authorize a production mutation.
    """
    records = _records(database)
    status = _run_status(database, run_context)
    if status != "PASS" and not allow_blocked_dry_run:
        raise RuntimeError(f"run status {status} is not eligible for production Sheet mutation")

    has_explicit_eligibility = all("delivery_eligible" in record for record in records)
    if not has_explicit_eligibility and not allow_blocked_dry_run:
        raise RuntimeError("production Sheet mutation requires explicit delivery_eligible on every record")
    if has_explicit_eligibility:
        delivery_records = [record for record in records if record.get("delivery_eligible") is True]
        review_records = [record for record in records if record.get("delivery_eligible") is not True]
    else:
        delivery_records = list(records)
        review_records = []

    manifest = database.get("delivery_manifest")
    if isinstance(manifest, dict) and "delivery_ids" in manifest:
        expected = {str(value) for value in manifest.get("delivery_ids") or []}
        actual_ids = [_candidate_id(record) for record in delivery_records]
        if any(value is None for value in actual_ids):
            raise ValueError("delivery manifest requires candidate_id on every delivery record")
        actual = {str(value) for value in actual_ids if value is not None}
        if actual != expected:
            raise ValueError(
                "delivery manifest identity mismatch: "
                f"expected={sorted(expected)} actual={sorted(actual)}"
            )
        if len(actual_ids) != len(actual):
            raise ValueError("delivery manifest contains duplicate candidate identities")

    return {
        "run_status": status,
        "blocked": status != "PASS",
        "delivery_records": delivery_records,
        "review_records": review_records,
        "delivery_count": len(delivery_records),
        "review_count": len(review_records),
        "legacy_delivery_fallback": not has_explicit_eligibility,
    }


def build_identity_summary(
    database: dict[str, Any],
    delivery_context: dict[str, Any] | None = None,
    run_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    selection = select_delivery_records(
        database,
        run_context=run_context,
        allow_blocked_dry_run=True,
    )
    records = selection["delivery_records"]
    identities = [
        library.resolve_identity(
            record,
            run_context=database,
            delivery_context=delivery_context,
        )
        for record in records
    ]
    return {
        "run_status": selection["run_status"],
        "blocked": selection["blocked"],
        "record_count": len(records),
        "review_count": selection["review_count"],
        "stable_row_count": len({identity.stable_key for identity in identities}),
        "stable_keys": [identity.stable_key for identity in identities],
        "delivery_candidate_ids": [
            record.get("candidate_id") for record in records if record.get("candidate_id")
        ],
    }


def export(
    client: SheetClient,
    database: dict[str, Any],
    delivery_context: dict[str, Any] | None = None,
    *,
    run_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Patch Emerging-owned fields for delivery-eligible stable rows only."""
    # This gate is intentionally before *any* Sheet read/write.  Do not move it
    # into ``keyword_library_sheet`` where a client may already have been read.
    selection = select_delivery_records(database, run_context=run_context)
    result = library.upsert_records(
        client,
        "emerging",
        selection["delivery_records"],
        run_context=database,
        delivery_context=delivery_context,
    )
    result["delivery_count"] = selection["delivery_count"]
    result["review_count"] = selection["review_count"]
    return result


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
        help="resolve the eligible delivery set and stable identities without contacting Google",
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

    # Re-check before credentials/client creation.  This guarantees a BLOCKED
    # run produces zero Sheet reads and zero Sheet writes.
    if summary["blocked"]:
        print("BLOCKED: BLOCKED run is not eligible for production Sheet mutation", file=sys.stderr)
        return 2

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
        print(f"BLOCKED: sheet export failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
