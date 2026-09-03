#!/usr/bin/env python3
"""Write a validated Discovery handoff to Google Sheets and verify it by readback.

The local Discovery handoff remains the machine-authoritative artifact. Google
Sheets is a mandatory delivery surface: export succeeds only when the current
batch can be read back exactly, with no missing, extra, or duplicate candidate
rows. A successful real export writes a delivery receipt bound to the exact
handoff and decorates that handoff with the receipt path so production handoff
validation can fail closed when Sheet delivery did not happen.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

UNKNOWN = "unknown"
DEFAULT_WORKSHEET = "keyword_discovery"
DELIVERY_SCHEMA = "seo-discovery-sheet-delivery/v1"
DELIVERY_REF_FIELD = "sheet_delivery_receipt_ref"

COLUMNS: tuple[tuple[str, str], ...] = (
    ("Batch ID", "batch_id"),
    ("Candidate ID", "candidate_id"),
    ("Keyword", "keyword"),
    ("Source", "source"),
    ("Source Seed", "source_seed"),
    ("Evidence Receipt", "evidence_receipt_ref"),
    ("Volume", "volume"),
    ("KD", "kd"),
)
HEADER: list[str] = [header for header, _ in COLUMNS]
KEY_COLUMNS = 2


class SheetClient(Protocol):
    def get_all_values(self) -> list[list[str]]: ...

    def update(self, range_name: str, values: list[list[Any]]) -> Any: ...

    def append_rows(self, values: list[list[Any]]) -> Any: ...


def expand_path(value: str) -> str:
    return os.path.expanduser(os.path.expandvars(str(value)))


def file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _canonical_json_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def handoff_binding_payload(handoff: dict[str, Any]) -> dict[str, Any]:
    """Return the exact handoff content covered by a Sheet-delivery receipt.

    The receipt path itself is excluded so the exporter can compute the binding
    before the receipt exists and the validator can recompute it after the
    handoff is decorated with that path. Every other field remains bound.
    """
    if not isinstance(handoff, dict):
        raise ValueError("Discovery handoff must be an object")
    return {key: value for key, value in handoff.items() if key != DELIVERY_REF_FIELD}


def handoff_binding_sha256(handoff: dict[str, Any]) -> str:
    return _canonical_json_sha256(handoff_binding_payload(handoff))


def format_cell(value: Any) -> str:
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


def _validate_handoff(handoff: dict[str, Any]) -> None:
    if not isinstance(handoff, dict):
        raise ValueError("Discovery handoff must be an object")
    if handoff.get("status") != "PASS" or handoff.get("coverage_status") != "PASS":
        raise ValueError("Discovery handoff must have PASS status and PASS coverage")
    if not str(handoff.get("batch_id") or "").strip():
        raise ValueError("Discovery handoff batch_id is required")
    keywords = handoff.get("keywords")
    if not isinstance(keywords, list) or not keywords:
        raise ValueError("Discovery handoff keywords are required")
    seen: set[str] = set()
    for index, item in enumerate(keywords):
        if not isinstance(item, dict):
            raise ValueError(f"Discovery handoff keyword {index} must be an object")
        candidate_id = str(item.get("candidate_id") or "").strip()
        keyword = str(item.get("keyword") or "").strip()
        source = str(item.get("source") or "").strip()
        source_seed = str(item.get("source_seed") or "").strip()
        evidence = str(item.get("evidence_receipt_ref") or "").strip()
        if not all((candidate_id, keyword, source, source_seed, evidence)):
            raise ValueError(f"Discovery handoff keyword {index} is missing provenance")
        if candidate_id in seen:
            raise ValueError(f"Discovery handoff candidate_id is duplicated: {candidate_id}")
        seen.add(candidate_id)


def build_rows(handoff: dict[str, Any]) -> list[list[str]]:
    _validate_handoff(handoff)
    batch_id = str(handoff["batch_id"]).strip()
    rows: list[list[str]] = []
    for item in handoff["keywords"]:
        record = dict(item)
        record["batch_id"] = batch_id
        rows.append([format_cell(record.get(field)) for _, field in COLUMNS])
    return rows


def _row_key(row: list[str]) -> tuple[str, str]:
    batch_id = str(row[0]).strip() if len(row) > 0 else ""
    candidate_id = str(row[1]).strip() if len(row) > 1 else ""
    return batch_id, candidate_id


def _a1(row_number: int, width: int) -> str:
    last = ""
    index = width
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        last = chr(ord("A") + remainder) + last
    return f"A{row_number}:{last}{row_number}"


def plan_writes(existing: list[list[str]], rows: list[list[str]]) -> dict[str, Any]:
    header_needed = not existing or [str(cell).strip() for cell in existing[0]] != HEADER
    index: dict[tuple[str, str], int] = {}
    if existing and not header_needed:
        for row_number, row in enumerate(existing[1:], start=2):
            key = _row_key(row)
            if key != ("", ""):
                index.setdefault(key, row_number)

    updates: list[tuple[str, list[str]]] = []
    appends: list[list[str]] = []
    for row in rows:
        target = index.get(_row_key(row))
        if target is None:
            appends.append(row)
        else:
            updates.append((_a1(target, len(HEADER)), row))
    return {"header_needed": header_needed, "updates": updates, "appends": appends}


def verify_batch(client: SheetClient, handoff: dict[str, Any]) -> int:
    expected_rows = build_rows(handoff)
    expected = {_row_key(row): row for row in expected_rows}
    batch_id = str(handoff["batch_id"]).strip()

    actual_values = client.get_all_values() or []
    if not actual_values or [str(cell).strip() for cell in actual_values[0]] != HEADER:
        raise RuntimeError("sheet verification failed: header mismatch")

    actual: dict[tuple[str, str], list[str]] = {}
    for row in actual_values[1:]:
        if not row or str(row[0]).strip() != batch_id:
            continue
        normalized = [str(cell) for cell in row[: len(HEADER)]]
        if len(normalized) < len(HEADER):
            normalized.extend([""] * (len(HEADER) - len(normalized)))
        key = _row_key(normalized)
        if key in actual:
            raise RuntimeError(f"sheet verification failed: duplicate current-batch row {key}")
        actual[key] = normalized

    if set(actual) != set(expected):
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        raise RuntimeError(
            f"sheet verification failed: current batch key mismatch; missing={missing}; extra={extra}"
        )
    for key, expected_row in expected.items():
        if actual[key] != expected_row:
            raise RuntimeError(f"sheet verification failed: row differs for {key}")
    return len(actual)


def export(client: SheetClient, handoff: dict[str, Any]) -> dict[str, Any]:
    rows = build_rows(handoff)
    existing = client.get_all_values() or []
    plan = plan_writes(existing, rows)

    if plan["header_needed"]:
        client.update(range_name=_a1(1, len(HEADER)), values=[HEADER])
    for range_name, row in plan["updates"]:
        client.update(range_name=range_name, values=[row])
    if plan["appends"]:
        client.append_rows(plan["appends"])

    verified = verify_batch(client, handoff)
    return {
        "status": "PASS",
        "batch_id": str(handoff["batch_id"]).strip(),
        "record_count": len(rows),
        "verified_count": verified,
        "updated_count": len(plan["updates"]),
        "appended_count": len(plan["appends"]),
        "header_written": plan["header_needed"],
    }


def default_delivery_receipt_path(handoff_path: str | Path) -> Path:
    path = Path(expand_path(str(handoff_path)))
    if path.suffix:
        return path.with_name(path.stem + ".sheet-delivery.receipt.json")
    return Path(str(path) + ".sheet-delivery.receipt.json")


def build_delivery_receipt(
    handoff: dict[str, Any],
    result: dict[str, Any],
    sheet_id: str,
    worksheet: str,
) -> dict[str, Any]:
    _validate_handoff(handoff)
    if result.get("status") != "PASS":
        raise ValueError("Sheet export result must be PASS before a delivery receipt can be issued")
    expected_count = len(handoff["keywords"])
    if result.get("record_count") != expected_count or result.get("verified_count") != expected_count:
        raise ValueError("Sheet export result is not an exact verified handoff")
    return {
        "schema": DELIVERY_SCHEMA,
        "status": "PASS",
        "batch_id": str(handoff["batch_id"]).strip(),
        "worksheet": str(worksheet).strip(),
        "sheet_id": str(sheet_id).strip(),
        "record_count": expected_count,
        "verified_count": expected_count,
        "handoff_binding_sha256": handoff_binding_sha256(handoff),
        "exporter_source_sha256": file_sha256(Path(__file__).resolve()),
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }


def persist_delivery_receipt(
    handoff_path: str | Path,
    handoff: dict[str, Any],
    result: dict[str, Any],
    sheet_id: str,
    worksheet: str,
    receipt_path: str | Path | None = None,
) -> Path:
    target = Path(expand_path(str(receipt_path))) if receipt_path else default_delivery_receipt_path(handoff_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    receipt = build_delivery_receipt(handoff, result, sheet_id, worksheet)
    target.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    decorated = dict(handoff)
    decorated[DELIVERY_REF_FIELD] = str(target)
    Path(expand_path(str(handoff_path))).write_text(
        json.dumps(decorated, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return target


def open_worksheet(sheet_id: str, worksheet: str, credentials: str) -> SheetClient:
    try:
        import gspread
    except ImportError as exc:  # pragma: no cover - optional production dependency
        raise RuntimeError("gspread is not installed") from exc
    client = gspread.service_account(filename=expand_path(credentials))
    spreadsheet = client.open_by_key(sheet_id)
    try:
        return spreadsheet.worksheet(worksheet)
    except Exception:
        return spreadsheet.add_worksheet(title=worksheet, rows=1000, cols=len(HEADER))


def load_handoff(path: str) -> dict[str, Any]:
    try:
        payload = json.loads(Path(expand_path(path)).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid Discovery handoff: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Discovery handoff must be a JSON object")
    return payload


def main(worksheet_factory: Callable[..., SheetClient] = open_worksheet) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff", required=True, help="Discovery handoff JSON to deliver and decorate")
    parser.add_argument("--sheet-id")
    parser.add_argument("--worksheet", default=DEFAULT_WORKSHEET)
    parser.add_argument("--credentials")
    parser.add_argument("--receipt", help="optional Sheet-delivery receipt path")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        handoff = load_handoff(args.handoff)
        rows = build_rows(handoff)
    except Exception as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2

    if args.dry_run:
        print(
            json.dumps(
                {"worksheet": args.worksheet, "header": HEADER, "rows": rows},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    sheet_id = args.sheet_id or os.environ.get("SEO_KEYWORD_SHEET_ID")
    credentials = args.credentials or os.environ.get("SEO_SHEETS_CREDENTIALS")
    missing = [
        name
        for name, value in (("--sheet-id/SEO_KEYWORD_SHEET_ID", sheet_id), ("--credentials/SEO_SHEETS_CREDENTIALS", credentials))
        if not value
    ]
    if missing:
        print(f"BLOCKED: {' and '.join(missing)} are required", file=sys.stderr)
        return 2

    try:
        worksheet = worksheet_factory(sheet_id, args.worksheet, credentials)
        result = export(worksheet, handoff)
        result["worksheet"] = args.worksheet
        receipt_path = persist_delivery_receipt(
            args.handoff,
            handoff,
            result,
            str(sheet_id),
            args.worksheet,
            args.receipt,
        )
        result[DELIVERY_REF_FIELD] = str(receipt_path)
    except Exception as exc:
        print(f"BLOCKED: sheet delivery failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
