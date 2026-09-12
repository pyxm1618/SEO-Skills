#!/usr/bin/env python3
"""Shared Google Sheet writer for the long-lived SEO keyword library.

This module is delivery plumbing only. It owns stable keyword identity, the
human-facing/technical Sheet schema, field ownership, field-level upserts and
readback verification. It does not participate in SEO acquisition or decisions.
"""

from __future__ import annotations

import json
import math
import os
import re
from datetime import datetime, timezone
from typing import Any, Protocol

UNKNOWN = "unknown"
DEFAULT_WORKSHEET = "关键词库"
HUMAN_STATUSES = frozenset({"新发现", "已选", "已建站", "放弃"})

# Visible columns must stay first and intentionally small. Everything after
# these is technical/audit context and is hidden by the real Sheet bootstrap.
COLUMNS: tuple[tuple[str, str], ...] = (
    ("关键词", "keyword"),
    ("月搜索量", "volume"),
    ("趋势类型", "trend_type"),
    ("出生窗口", "estimated_birth_window"),
    ("KD", "kd"),
    ("CPC", "cpc"),
    ("KDRoi", "kdroi"),
    ("意图", "intent"),
    ("状态", "workflow_status"),
    ("market", "market"),
    ("language", "language"),
    ("normalized_keyword", "normalized_keyword"),
    ("stable_keyword_key", "stable_keyword_key"),
    ("domain", "domain"),
    ("Root", "root"),
    ("Root ID", "root_id"),
    ("source", "source"),
    ("source_seed", "source_seed"),
    ("candidate_id", "candidate_id"),
    ("batch_id", "batch_id"),
    ("discovery_evidence_refs", "discovery_evidence_refs"),
    ("discovery_provenance", "discovery_provenance"),
    ("first_observed_at", "first_observed_at"),
    ("birth_confidence", "birth_confidence"),
    ("birth_reason", "birth_reason"),
    ("growth_rate", "growth_rate"),
    ("persistence", "persistence"),
    ("demand_history_type", "demand_history_type"),
    ("signal_type", "signal_type"),
    ("emerging_status", "emerging_status"),
    ("previous_status", "previous_status"),
    ("emerging_evidence_refs", "emerging_evidence_refs"),
    ("emerging_domain", "emerging_domain"),
    ("emerging_root_id", "emerging_root_id"),
    ("KGR", "kgr"),
    ("intitle_results", "intitle_results"),
    ("SERP weak evidence", "serp_weak_evidence"),
    ("SERP weak points", "serp_weak_points"),
    ("selection_mechanical_status", "mechanical_status"),
    ("metric_source", "metric_source"),
    ("metric_database", "metric_database"),
    ("metric_stage", "metric_stage"),
    ("provenance_status", "provenance_status"),
    ("observed_at", "observed_at"),
    ("last_updated", "last_updated"),
    ("receipt_refs", "receipt_refs"),
)
HEADER = [header for header, _ in COLUMNS]
VISIBLE_COLUMN_COUNT = 9
FIELD_TO_HEADER = {field: header for header, field in COLUMNS}
HEADER_TO_FIELD = {header: field for header, field in COLUMNS}

DISCOVERY_FIELDS = frozenset(
    {
        "domain",
        "root",
        "root_id",
        "source",
        "source_seed",
        "candidate_id",
        "batch_id",
        "discovery_evidence_refs",
        "discovery_provenance",
        "receipt_refs",
        "last_updated",
    }
)
EMERGING_FIELDS = frozenset(
    {
        "trend_type",
        "estimated_birth_window",
        "first_observed_at",
        "birth_confidence",
        "birth_reason",
        "growth_rate",
        "persistence",
        "demand_history_type",
        "signal_type",
        "emerging_status",
        "previous_status",
        "emerging_evidence_refs",
        "emerging_domain",
        "emerging_root_id",
        "receipt_refs",
        "last_updated",
    }
)
SELECTION_FIELDS = frozenset(
    {
        "volume",
        "kd",
        "cpc",
        "kdroi",
        "intent",
        "kgr",
        "intitle_results",
        "serp_weak_evidence",
        "serp_weak_points",
        "mechanical_status",
        "metric_source",
        "metric_database",
        "metric_stage",
        "provenance_status",
        "observed_at",
        "receipt_refs",
        "last_updated",
    }
)
OWNER_FIELDS = {
    "discovery": DISCOVERY_FIELDS,
    "emerging": EMERGING_FIELDS,
    "selection": SELECTION_FIELDS,
}


class SheetClient(Protocol):
    def get_all_values(self) -> list[list[str]]: ...

    def update(self, range_name: str, values: list[list[Any]]) -> Any: ...

    def append_rows(self, values: list[list[Any]]) -> Any: ...


class KeywordIdentity:
    __slots__ = ("keyword", "normalized_keyword", "market", "language", "stable_key")

    def __init__(self, keyword: str, normalized_keyword: str, market: str, language: str):
        self.keyword = keyword
        self.normalized_keyword = normalized_keyword
        self.market = market
        self.language = language
        self.stable_key = f"{normalized_keyword} | {market} | {language}"


def is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().casefold() in {"", "unknown", "null", "none", "n/a", "na"}
    return False


def collapse_keyword(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def canonical_keyword(value: Any) -> str:
    return collapse_keyword(value).casefold()


def canonical_language(value: Any) -> str:
    """Canonicalize a BCP47-like language tag without guessing missing context."""
    parts = [part for part in str(value or "").strip().replace("_", "-").split("-") if part]
    if not parts:
        return ""
    out = [parts[0].lower()]
    for part in parts[1:]:
        if len(part) == 2 and part.isalpha():
            out.append(part.upper())
        elif len(part) == 4 and part.isalpha():
            out.append(part.title())
        else:
            out.append(part.lower())
    return "-".join(out)


def format_cell(value: Any) -> str:
    if is_missing(value):
        return UNKNOWN
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if not math.isfinite(value):
            return UNKNOWN
        return repr(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, (list, dict)):
        if not value:
            return UNKNOWN
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return str(value).strip()


def _context_value(record: dict[str, Any], run_context: dict[str, Any] | None,
                   delivery_context: dict[str, Any] | None, field: str, aliases: tuple[str, ...] = ()) -> Any:
    for source in (record, run_context or {}, delivery_context or {}):
        for name in (field,) + aliases:
            value = source.get(name) if isinstance(source, dict) else None
            if not is_missing(value):
                return value
    return None


def resolve_identity(record: dict[str, Any], run_context: dict[str, Any] | None = None,
                     delivery_context: dict[str, Any] | None = None) -> KeywordIdentity:
    if not isinstance(record, dict):
        raise ValueError("keyword record must be an object")
    keyword = collapse_keyword(record.get("keyword", record.get("phrase")))
    if not keyword:
        raise ValueError("keyword is required for stable identity")
    market = _context_value(record, run_context, delivery_context, "market", ("country",))
    language = _context_value(record, run_context, delivery_context, "language")
    if is_missing(market):
        raise ValueError("market is required for stable keyword identity")
    if is_missing(language):
        raise ValueError("language is required for stable keyword identity")
    normalized = canonical_keyword(keyword)
    market_value = str(market).strip().upper()
    language_value = canonical_language(language)
    return KeywordIdentity(keyword, normalized, market_value, language_value)


def derive_trend_type(record: dict[str, Any]) -> str:
    """Map existing canonical temporal classification to the display label only."""
    signal_type = str(record.get("signal_type") or "").strip().casefold()
    demand_history = str(record.get("demand_history_type") or "").strip().casefold()
    status = str(record.get("status") or record.get("emerging_status") or "").strip().casefold()
    if signal_type == "net_new" or demand_history == "newly_observed":
        return "新词"
    if signal_type == "breakout" or status == "breakout":
        return "上升"
    return UNKNOWN


def _column_letters(index: int) -> str:
    value = index + 1
    out = ""
    while value:
        value, remainder = divmod(value - 1, 26)
        out = chr(ord("A") + remainder) + out
    return out


def _cell_a1(row_number: int, column_index: int) -> str:
    col = _column_letters(column_index)
    return f"{col}{row_number}:{col}{row_number}"


def _row_a1(row_number: int, width: int) -> str:
    return f"A{row_number}:{_column_letters(width - 1)}{row_number}"


def _has_data_rows(values: list[list[str]]) -> bool:
    for row in values[1:]:
        if any(str(cell).strip() for cell in row):
            return True
    return False


def _hide_technical_columns(client: SheetClient) -> None:
    hide = getattr(client, "hide_columns", None)
    if callable(hide):
        hide(VISIBLE_COLUMN_COUNT, len(HEADER))


def ensure_capacity(client: SheetClient, minimum_columns: int = len(HEADER)) -> bool:
    """Resize real gspread worksheets before writes that exceed grid capacity."""
    raw_count = getattr(client, "col_count", None)
    if isinstance(raw_count, bool) or not isinstance(raw_count, (int, float)):
        # Lightweight adapters/fakes without grid metadata are not assumed to be
        # capacity-constrained. Real gspread Worksheet exposes col_count.
        return False
    current_columns = int(raw_count)
    if current_columns >= minimum_columns:
        return False
    resize = getattr(client, "resize", None)
    if not callable(resize):
        raise RuntimeError(
            f"keyword library worksheet has {current_columns} columns but needs {minimum_columns}; resize unavailable"
        )
    resize(cols=minimum_columns)
    verified_count = getattr(client, "col_count", minimum_columns)
    if isinstance(verified_count, (int, float)) and int(verified_count) < minimum_columns:
        raise RuntimeError(
            f"keyword library worksheet resize failed; has {int(verified_count)} columns, needs {minimum_columns}"
        )
    return True


def ensure_schema(client: SheetClient) -> tuple[list[list[str]], list[str], dict[str, int], bool]:
    ensure_capacity(client, len(HEADER))
    values = client.get_all_values() or []
    header = [str(cell).strip() for cell in values[0]] if values else []
    header_written = False

    if not values or not header:
        client.update(range_name=_row_a1(1, len(HEADER)), values=[HEADER])
        _hide_technical_columns(client)
        return [list(HEADER)], list(HEADER), {name: i for i, name in enumerate(HEADER)}, True

    duplicates = {name for name in header if name and header.count(name) > 1}
    if duplicates:
        raise RuntimeError(f"keyword library sheet schema has duplicate headers: {sorted(duplicates)}")

    if all(name in header for name in HEADER):
        return values, header, {name: i for i, name in enumerate(header)}, False

    if _has_data_rows(values):
        missing = [name for name in HEADER if name not in header]
        raise RuntimeError(f"keyword library sheet schema mismatch with existing data; missing={missing}")

    # Empty legacy/header-only worksheet: safe one-time bootstrap.
    client.update(range_name=_row_a1(1, len(HEADER)), values=[HEADER])
    _hide_technical_columns(client)
    header_written = True
    return [list(HEADER)], list(HEADER), {name: i for i, name in enumerate(HEADER)}, header_written


def _row_value(row: list[str], index: int) -> str:
    return str(row[index]) if index < len(row) else ""


def _build_index(values: list[list[str]], header_map: dict[str, int]) -> dict[str, tuple[int, list[str]]]:
    key_col = header_map["stable_keyword_key"]
    index: dict[str, tuple[int, list[str]]] = {}
    for row_number, row in enumerate(values[1:], start=2):
        if not any(str(cell).strip() for cell in row):
            continue
        key = _row_value(row, key_col).strip()
        if is_missing(key):
            raise RuntimeError(f"keyword library row {row_number} is missing stable_keyword_key")
        if key in index:
            raise RuntimeError(f"keyword library duplicate stable identity: {key}")
        normalized = list(map(str, row))
        if len(normalized) < len(header_map):
            normalized.extend([""] * (len(header_map) - len(normalized)))
        index[key] = (row_number, normalized)
    return index


def _parse_json_list(value: Any, field: str) -> list[Any]:
    if is_missing(value):
        return []
    if isinstance(value, list):
        return list(value)
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{field} contains invalid JSON and cannot be safely merged") from exc
    if not isinstance(parsed, list):
        raise RuntimeError(f"{field} must contain a JSON list")
    return parsed


def _merge_unique(existing: Any, additions: list[Any], field: str) -> list[Any]:
    values = _parse_json_list(existing, field)
    seen = {json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")) for item in values}
    for item in additions:
        marker = json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if marker not in seen:
            values.append(item)
            seen.add(marker)
    return values


def _discovery_patch(record: dict[str, Any], existing: dict[str, str]) -> dict[str, Any]:
    patch: dict[str, Any] = {}
    for field in ("domain", "root", "root_id", "source", "source_seed", "candidate_id", "batch_id"):
        if field in record:
            patch[field] = record.get(field)

    evidence = record.get("evidence_receipt_ref", record.get("evidence_ref"))
    if not is_missing(evidence):
        patch["discovery_evidence_refs"] = _merge_unique(
            existing.get("discovery_evidence_refs"), [str(evidence).strip()], "discovery_evidence_refs"
        )

    provenance = {
        field: record.get(field)
        for field in ("candidate_id", "batch_id", "source", "source_seed", "evidence_receipt_ref")
        if not is_missing(record.get(field))
    }
    if provenance:
        patch["discovery_provenance"] = _merge_unique(
            existing.get("discovery_provenance"), [provenance], "discovery_provenance"
        )
    return patch


def _emerging_patch(record: dict[str, Any]) -> dict[str, Any]:
    aliases = {
        "estimated_birth_window": "estimated_birth_window",
        "first_observed_at": "first_observed_at",
        "birth_confidence": "birth_confidence",
        "birth_reason": "birth_reason",
        "growth_rate": "growth_rate",
        "persistence": "persistence",
        "demand_history_type": "demand_history_type",
        "signal_type": "signal_type",
        "status": "emerging_status",
        "previous_status": "previous_status",
        "domain": "emerging_domain",
        "root_id": "emerging_root_id",
    }
    patch = {target: record.get(source) for source, target in aliases.items() if source in record}
    if any(name in record for name in ("signal_type", "demand_history_type", "status", "emerging_status")):
        patch["trend_type"] = derive_trend_type(record)
    refs = []
    for source in ("evidence_ref", "evidence_receipt_ref"):
        if not is_missing(record.get(source)):
            refs.append(str(record[source]).strip())
    if refs:
        patch["emerging_evidence_refs"] = refs
    return patch


def _selection_patch(record: dict[str, Any]) -> dict[str, Any]:
    patch: dict[str, Any] = {}
    simple = (
        "volume",
        "cpc",
        "kdroi",
        "kgr",
        "intitle_results",
        "serp_weak_evidence",
        "serp_weak_points",
        "mechanical_status",
        "metric_source",
        "metric_database",
        "metric_stage",
        "provenance_status",
        "observed_at",
    )
    for field in simple:
        if field in record:
            patch[field] = record.get(field)
    if "difficulty" in record:
        patch["kd"] = record.get("difficulty")
    elif "kd" in record:
        patch["kd"] = record.get("kd")
    if "intent" in record and not is_missing(record.get("intent")):
        patch["intent"] = record.get("intent")
    return patch


def _owner_patch(owner: str, record: dict[str, Any], existing: dict[str, str]) -> dict[str, Any]:
    if owner == "discovery":
        patch = _discovery_patch(record, existing)
    elif owner == "emerging":
        patch = _emerging_patch(record)
    elif owner == "selection":
        patch = _selection_patch(record)
    else:
        raise ValueError(f"unsupported keyword library owner: {owner}")
    patch["last_updated"] = datetime.now(timezone.utc).isoformat()
    allowed = OWNER_FIELDS[owner]
    return {field: value for field, value in patch.items() if field in allowed}


def _row_as_fields(row: list[str], header_map: dict[str, int]) -> dict[str, str]:
    return {
        field: _row_value(row, header_map[header])
        for header, field in COLUMNS
        if header in header_map
    }


def _new_row(header: list[str], header_map: dict[str, int], identity: KeywordIdentity) -> list[str]:
    row = [""] * len(header)
    for name in HEADER:
        row[header_map[name]] = UNKNOWN
    row[header_map["关键词"]] = identity.keyword
    row[header_map["market"]] = identity.market
    row[header_map["language"]] = identity.language
    row[header_map["normalized_keyword"]] = identity.normalized_keyword
    row[header_map["stable_keyword_key"]] = identity.stable_key
    row[header_map["状态"]] = "新发现"
    return row


def upsert_records(client: SheetClient, owner: str, records: list[dict[str, Any]],
                   run_context: dict[str, Any] | None = None,
                   delivery_context: dict[str, Any] | None = None) -> dict[str, Any]:
    if owner not in OWNER_FIELDS:
        raise ValueError(f"unsupported keyword library owner: {owner}")
    if not isinstance(records, list):
        raise ValueError("records must be a list")

    values, header, header_map, header_written = ensure_schema(client)
    index = _build_index(values, header_map)
    working: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    for record in records:
        identity = resolve_identity(record, run_context=run_context, delivery_context=delivery_context)
        key = identity.stable_key
        if key not in working:
            if key in index:
                row_number, original = index[key]
                row = list(original)
                if len(row) < len(header):
                    row.extend([""] * (len(header) - len(row)))
                created = False
            else:
                row_number = None
                row = _new_row(header, header_map, identity)
                created = True
            working[key] = {
                "identity": identity,
                "row_number": row_number,
                "row": row,
                "original": list(row),
                "created": created,
                "touched": set(),
            }
            order.append(key)

        state = working[key]
        current = _row_as_fields(state["row"], header_map)
        patch = _owner_patch(owner, record, current)
        for field, value in patch.items():
            # Human workflow status is intentionally not an owner-patch field.
            header_name = FIELD_TO_HEADER[field]
            column = header_map[header_name]
            state["row"][column] = format_cell(value)
            state["touched"].add(field)

    existing_updates: list[tuple[int, int, str]] = []
    new_rows: list[list[str]] = []
    appended_keys: list[str] = []
    updated_keys: list[str] = []

    for key in order:
        state = working[key]
        if state["created"]:
            new_rows.append(state["row"])
            appended_keys.append(key)
            continue
        changed = False
        original = state["original"]
        row = state["row"]
        for field in state["touched"]:
            column = header_map[FIELD_TO_HEADER[field]]
            before = _row_value(original, column)
            after = _row_value(row, column)
            if before != after:
                existing_updates.append((state["row_number"], column, after))
                changed = True
        if changed:
            updated_keys.append(key)

    for row_number, column, value in existing_updates:
        client.update(range_name=_cell_a1(row_number, column), values=[[value]])
    if new_rows:
        client.append_rows(new_rows)

    readback = client.get_all_values() or []
    if not readback or not all(name in [str(cell).strip() for cell in readback[0]] for name in HEADER):
        raise RuntimeError("keyword library readback verification failed: schema mismatch")
    read_header = [str(cell).strip() for cell in readback[0]]
    read_map = {name: i for i, name in enumerate(read_header)}
    read_index = _build_index(readback, read_map)

    bindings = []
    for key in order:
        if key not in read_index:
            raise RuntimeError(f"keyword library readback verification failed: missing stable row {key}")
        row_number, row = read_index[key]
        state = working[key]
        expected_fields = set(state["touched"]) | {"market", "language", "normalized_keyword", "stable_keyword_key"}
        if state["created"]:
            expected_fields |= {"keyword", "workflow_status"}
        for field in expected_fields:
            header_name = FIELD_TO_HEADER[field]
            expected = _row_value(state["row"], header_map[header_name])
            actual = _row_value(row, read_map[header_name])
            if actual != expected:
                raise RuntimeError(
                    f"keyword library readback verification failed: {key} field {field} differs; "
                    f"expected={expected!r} actual={actual!r}"
                )
        bindings.append({"stable_key": key, "row_number": row_number})

    return {
        "status": "PASS",
        "owner": owner,
        "record_count": len(records),
        "stable_row_count": len(order),
        "updated_count": len(updated_keys),
        "appended_count": len(appended_keys),
        "header_written": header_written,
        "bindings": bindings,
    }


def expand_path(value: str) -> str:
    return os.path.expanduser(os.path.expandvars(str(value)))


def open_worksheet(sheet_id: str, worksheet: str, credentials: str) -> SheetClient:
    try:
        import gspread
    except ImportError as exc:  # pragma: no cover - optional production dependency
        raise RuntimeError("gspread is not installed") from exc
    client = gspread.service_account(filename=expand_path(credentials))
    spreadsheet = client.open_by_key(sheet_id)
    try:
        return spreadsheet.worksheet(worksheet)
    except Exception as exc:
        raise RuntimeError(f"keyword library worksheet not found: {worksheet}") from exc


def delivery_context_from_env(market: str | None = None, language: str | None = None) -> dict[str, str]:
    context: dict[str, str] = {}
    market_value = market or os.environ.get("SEO_KEYWORD_LIBRARY_MARKET")
    language_value = language or os.environ.get("SEO_KEYWORD_LIBRARY_LANGUAGE")
    if not is_missing(market_value):
        context["market"] = str(market_value).strip()
    if not is_missing(language_value):
        context["language"] = str(language_value).strip()
    return context