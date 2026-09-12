#!/usr/bin/env python3
"""Deliver a validated Discovery handoff to the unified SEO keyword library.

The local Discovery handoff remains the machine-authoritative artifact. Google
Sheets remains a mandatory delivery surface for formal Discovery handoff. The
v2 delivery verifies stable keyword rows while preserving every Discovery
candidate/source/provenance binding, including many candidates that resolve to
one stable keyword row.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

UNKNOWN = "unknown"
DEFAULT_WORKSHEET = "关键词库"
DELIVERY_SCHEMA = "seo-discovery-sheet-delivery/v2"
DELIVERY_REF_FIELD = "sheet_delivery_receipt_ref"

REPO_ROOT = Path(__file__).resolve().parents[3]
LIBRARY_PATH = REPO_ROOT / "runtime" / "keyword_library_sheet.py"


def _load_library():
    spec = importlib.util.spec_from_file_location("seo_keyword_library_sheet_for_discovery", LIBRARY_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


library = _load_library()
LIBRARY_HEADER = library.HEADER


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
    if not isinstance(handoff, dict):
        raise ValueError("Discovery handoff must be an object")
    return {key: value for key, value in handoff.items() if key != DELIVERY_REF_FIELD}


def handoff_binding_sha256(handoff: dict[str, Any]) -> str:
    return _canonical_json_sha256(handoff_binding_payload(handoff))


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


def _delivery_context(delivery_context: dict[str, Any] | None = None) -> dict[str, str]:
    out: dict[str, str] = {}
    for field in ("market", "language"):
        value = (delivery_context or {}).get(field)
        if not library.is_missing(value):
            out[field] = str(value).strip()
    return out


def build_candidate_bindings(
    handoff: dict[str, Any],
    delivery_context: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    """Bind every Discovery candidate to its unified stable keyword identity."""
    _validate_handoff(handoff)
    batch_id = str(handoff["batch_id"]).strip()
    context = _delivery_context(delivery_context)
    bindings: list[dict[str, str]] = []
    for item in handoff["keywords"]:
        identity = library.resolve_identity(item, run_context=handoff, delivery_context=context)
        bindings.append(
            {
                "candidate_id": str(item["candidate_id"]).strip(),
                "batch_id": batch_id,
                "keyword": library.collapse_keyword(item["keyword"]),
                "normalized_keyword": identity.normalized_keyword,
                "market": identity.market,
                "language": identity.language,
                "stable_key": identity.stable_key,
                "source": str(item["source"]).strip(),
                "source_seed": str(item["source_seed"]).strip(),
                "evidence_receipt_ref": str(item["evidence_receipt_ref"]).strip(),
            }
        )
    return bindings


def _header_map(values: list[list[str]]) -> dict[str, int]:
    if not values:
        raise RuntimeError("sheet verification failed: missing header")
    header = [str(cell).strip() for cell in values[0]]
    missing = [name for name in LIBRARY_HEADER if name not in header]
    if missing:
        raise RuntimeError(f"sheet verification failed: unified keyword library header mismatch; missing={missing}")
    if len({name for name in header if name}) != len([name for name in header if name]):
        raise RuntimeError("sheet verification failed: duplicate header")
    return {name: index for index, name in enumerate(header)}


def _cell(row: list[str], index: int) -> str:
    return str(row[index]) if index < len(row) else ""


def _stable_rows(values: list[list[str]], mapping: dict[str, int]) -> dict[str, tuple[int, list[str]]]:
    key_col = mapping["stable_keyword_key"]
    rows: dict[str, tuple[int, list[str]]] = {}
    for row_number, row in enumerate(values[1:], start=2):
        if not any(str(cell).strip() for cell in row):
            continue
        key = _cell(row, key_col).strip()
        if library.is_missing(key):
            raise RuntimeError(f"sheet verification failed: row {row_number} missing stable key")
        if key in rows:
            raise RuntimeError(f"sheet verification failed: duplicate stable row {key}")
        rows[key] = (row_number, row)
    return rows


def _parse_provenance(value: Any, stable_key: str) -> list[dict[str, Any]]:
    if library.is_missing(value):
        return []
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"sheet verification failed: invalid Discovery provenance JSON for {stable_key}"
        ) from exc
    if not isinstance(parsed, list) or not all(isinstance(item, dict) for item in parsed):
        raise RuntimeError(f"sheet verification failed: Discovery provenance must be a list for {stable_key}")
    return parsed


def _candidate_provenance(binding: dict[str, str]) -> dict[str, str]:
    return {
        "candidate_id": binding["candidate_id"],
        "batch_id": binding["batch_id"],
        "source": binding["source"],
        "source_seed": binding["source_seed"],
        "evidence_receipt_ref": binding["evidence_receipt_ref"],
    }


def verify_delivery(
    client: SheetClient,
    handoff: dict[str, Any],
    candidate_bindings: list[dict[str, str]] | None = None,
    delivery_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Verify all current candidates resolve to intact stable rows/provenance."""
    _validate_handoff(handoff)
    expected = candidate_bindings or build_candidate_bindings(handoff, delivery_context=delivery_context)
    if len(expected) != len(handoff["keywords"]):
        raise RuntimeError("sheet verification failed: candidate binding count mismatch")

    values = client.get_all_values() or []
    mapping = _header_map(values)
    rows = _stable_rows(values, mapping)
    provenance_col = mapping["discovery_provenance"]
    keyword_col = mapping["关键词"]
    normalized_col = mapping["normalized_keyword"]
    market_col = mapping["market"]
    language_col = mapping["language"]

    stable_keys = {binding["stable_key"] for binding in expected}
    verified_candidates = 0
    for binding in expected:
        key = binding["stable_key"]
        if key not in rows:
            raise RuntimeError(f"sheet verification failed: missing stable row {key}")
        _, row = rows[key]
        if library.canonical_keyword(_cell(row, keyword_col)) != binding["normalized_keyword"]:
            raise RuntimeError(f"sheet verification failed: keyword differs for {key}")
        if _cell(row, normalized_col).strip() != binding["normalized_keyword"]:
            raise RuntimeError(f"sheet verification failed: normalized keyword differs for {key}")
        if _cell(row, market_col).strip() != binding["market"]:
            raise RuntimeError(f"sheet verification failed: market differs for {key}")
        if _cell(row, language_col).strip() != binding["language"]:
            raise RuntimeError(f"sheet verification failed: language differs for {key}")

        provenance = _parse_provenance(_cell(row, provenance_col), key)
        expected_provenance = _candidate_provenance(binding)
        if expected_provenance not in provenance:
            raise RuntimeError(
                f"sheet verification failed: candidate provenance missing for {binding['candidate_id']}"
            )
        verified_candidates += 1

    return {
        "status": "PASS",
        "batch_id": str(handoff["batch_id"]).strip(),
        "candidate_count": len(expected),
        "verified_candidate_count": verified_candidates,
        "stable_row_count": len(stable_keys),
        "verified_stable_row_count": len(stable_keys),
        "candidate_bindings": expected,
    }


def export(
    client: SheetClient,
    handoff: dict[str, Any],
    delivery_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _validate_handoff(handoff)
    context = _delivery_context(delivery_context)
    bindings = build_candidate_bindings(handoff, delivery_context=context)
    records = []
    batch_id = str(handoff["batch_id"]).strip()
    for item in handoff["keywords"]:
        record = dict(item)
        record["batch_id"] = batch_id
        records.append(record)

    write_result = library.upsert_records(
        client,
        "discovery",
        records,
        run_context=handoff,
        delivery_context=context,
    )
    verified = verify_delivery(
        client,
        handoff,
        candidate_bindings=bindings,
        delivery_context=context,
    )
    verified.update(
        {
            "updated_count": write_result["updated_count"],
            "appended_count": write_result["appended_count"],
            "header_written": write_result["header_written"],
        }
    )
    return verified


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
    delivery_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _validate_handoff(handoff)
    if result.get("status") != "PASS":
        raise ValueError("Sheet export result must be PASS before a delivery receipt can be issued")
    expected_candidate_count = len(handoff["keywords"])
    bindings = result.get("candidate_bindings")
    if not isinstance(bindings, list) or len(bindings) != expected_candidate_count:
        raise ValueError("Sheet export result is missing exact candidate bindings")
    expected_stable_count = len({item.get("stable_key") for item in bindings if isinstance(item, dict)})
    if result.get("candidate_count") != expected_candidate_count:
        raise ValueError("Sheet export candidate_count does not match handoff")
    if result.get("verified_candidate_count") != expected_candidate_count:
        raise ValueError("Sheet export did not verify every Discovery candidate")
    if result.get("stable_row_count") != expected_stable_count:
        raise ValueError("Sheet export stable_row_count mismatch")
    if result.get("verified_stable_row_count") != expected_stable_count:
        raise ValueError("Sheet export did not verify every stable row")
    return {
        "schema": DELIVERY_SCHEMA,
        "status": "PASS",
        "batch_id": str(handoff["batch_id"]).strip(),
        "worksheet": str(worksheet).strip(),
        "sheet_id": str(sheet_id).strip(),
        "candidate_count": expected_candidate_count,
        "verified_candidate_count": expected_candidate_count,
        "stable_row_count": expected_stable_count,
        "verified_stable_row_count": expected_stable_count,
        "candidate_bindings": bindings,
        "delivery_context": _delivery_context(delivery_context),
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
    delivery_context: dict[str, Any] | None = None,
) -> Path:
    target = Path(expand_path(str(receipt_path))) if receipt_path else default_delivery_receipt_path(handoff_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    receipt = build_delivery_receipt(
        handoff,
        result,
        sheet_id,
        worksheet,
        delivery_context=delivery_context,
    )
    target.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    decorated = dict(handoff)
    decorated[DELIVERY_REF_FIELD] = str(target)
    Path(expand_path(str(handoff_path))).write_text(
        json.dumps(decorated, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return target


def open_worksheet(sheet_id: str, worksheet: str, credentials: str) -> SheetClient:
    return library.open_worksheet(sheet_id, worksheet, credentials)


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
    parser.add_argument(
        "--worksheet",
        default=os.environ.get("SEO_KEYWORD_LIBRARY_WORKSHEET", DEFAULT_WORKSHEET),
    )
    parser.add_argument("--credentials")
    parser.add_argument("--market", help="explicit delivery market when handoff/records do not carry one")
    parser.add_argument("--language", help="explicit delivery language when handoff/records do not carry one")
    parser.add_argument("--receipt", help="optional Sheet-delivery receipt path")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        handoff = load_handoff(args.handoff)
        context = library.delivery_context_from_env(args.market, args.language)
        bindings = build_candidate_bindings(handoff, delivery_context=context)
    except Exception as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2

    if args.dry_run:
        print(
            json.dumps(
                {
                    "worksheet": args.worksheet,
                    "candidate_count": len(bindings),
                    "stable_row_count": len({item["stable_key"] for item in bindings}),
                    "candidate_bindings": bindings,
                },
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
        print(f"BLOCKED: {' and '.join(missing)} are required", file=sys.stderr)
        return 2

    try:
        worksheet = worksheet_factory(sheet_id, args.worksheet, credentials)
        result = export(worksheet, handoff, delivery_context=context)
        result["worksheet"] = args.worksheet
        receipt_path = persist_delivery_receipt(
            args.handoff,
            handoff,
            result,
            str(sheet_id),
            args.worksheet,
            args.receipt,
            delivery_context=context,
        )
        result[DELIVERY_REF_FIELD] = str(receipt_path)
    except Exception as exc:
        print(f"BLOCKED: sheet delivery failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
