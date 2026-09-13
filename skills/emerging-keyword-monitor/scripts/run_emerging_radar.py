#!/usr/bin/env python3
"""Domain-level Emerging Keyword Radar orchestration.

The runner keeps one candidate ledger from discovery through acquisition,
classification, routing, persistence, and delivery. Candidates without valid
observations remain explicit ledger records; they are never manufactured into
classifier output merely because the browser failed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[2]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from radar_discovery import (
    HumanInterventionRequired,
    build_anchor_pool,
    canonical_keyword,
    default_domain_relation,
    discover_rising_bfs,
)
from update_emerging_database import carry_forward, load_database, merge_database, write_database


TIMEFRAME_DEFAULTS = (
    ("5y", "today 5-y"),
    ("12m", "today 12-m"),
    ("90d", "today 3-m"),
)
SYSTEMIC_FAILURE_TYPES = frozenset(
    {
        "screenshot_timeout",
        "screenshot_failed",
        "payload_not_observed",
        "browser_closed",
        "collector_failed",
        "stage_validation_failed",
    }
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _call(fetcher: Callable[..., Any], args: tuple[Any, ...], throttle: Any = None) -> Any:
    if throttle is not None:
        throttle.wait()
    return fetcher(*args)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load_canonical_pipeline():
    path = REPO_ROOT / "runtime" / "emerging_pipeline.py"
    spec = importlib.util.spec_from_file_location("seo_emerging_runtime_pipeline", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load canonical Emerging pipeline: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _relation(relation_gate: Callable[[str, str, str], Any] | None, domain: str, keyword: str, parent: str) -> tuple[str, str]:
    decision = relation_gate(domain, keyword, parent) if relation_gate else default_domain_relation(domain, keyword, parent)
    if isinstance(decision, dict):
        return str(decision.get("domain_relation") or decision.get("relation") or "unknown"), str(
            decision.get("reason") or "domain relation analysis returned no reason"
        )
    if isinstance(decision, (tuple, list)) and len(decision) >= 2:
        return str(decision[0] or "unknown"), str(decision[1] or "domain relation analysis returned no reason")
    return str(decision or "unknown"), "domain relation analysis returned no reason"


def _supplemental_values(source: str, payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        raise ValueError(f"{source} supplemental payload must contain a list")
    if source == "google_autocomplete":
        values = payload.get("suggestions")
        if values is None:
            values = payload.get("rows")
    else:
        values = payload.get("rows")
        if values is None:
            values = payload.get("keywords")
    if not isinstance(values, list):
        raise ValueError(f"{source} supplemental payload must contain a list")
    return values


def _supplemental_candidates(
    domain: str,
    anchor: dict[str, Any],
    source: str,
    payload: Any,
    relation_gate: Callable[[str, str, str], Any] | None,
) -> list[dict[str, Any]]:
    values = _supplemental_values(source, payload)
    field = "query" if source == "google_autocomplete" else "keyword"
    candidates: list[dict[str, Any]] = []
    for item in values:
        value = item if isinstance(item, str) else item.get(field) if isinstance(item, dict) else None
        keyword = " ".join(str(value or "").split())
        if not keyword:
            continue
        relation, reason = _relation(relation_gate, domain, keyword, anchor["keyword"])
        candidates.append(
            {
                "keyword": keyword,
                "domain": domain,
                "root_id": anchor.get("root_id"),
                "root_relation": "existing_root" if anchor.get("root_verified") else "root_candidate" if anchor.get("root_status") == "candidate" else "unresolved",
                "parent_anchor": anchor["keyword"],
                "discovery_depth": int(anchor.get("discovery_depth") or 0) + 1,
                "discovery_source": source,
                "domain_relation": relation,
                "domain_relation_reason": reason,
                "recursive_edge": False,
                "supplemental_discovery": True,
                "supplemental_source": source,
                "supplemental_evidence_ref": payload.get("evidence_ref") if isinstance(payload, dict) else None,
            }
        )
    return candidates


def _database_snapshot(existing_database: dict[str, Any] | None, database_path: Path | None) -> dict[str, Any]:
    if existing_database is not None:
        return existing_database
    if database_path is not None:
        return load_database(Path(database_path))
    return {"schema_version": 1, "records": []}


def _stable_candidate_id(domain: str, keyword: str) -> str:
    identity = f"{canonical_keyword(domain)}\x1f{canonical_keyword(keyword)}"
    return "cand_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]


def _candidate_sources(candidate: dict[str, Any]) -> list[str]:
    values = []
    for field in ("discovery_source", "supplemental_source", "anchor_source"):
        value = str(candidate.get(field) or "").strip()
        if value and value not in values:
            values.append(value)
    if candidate.get("carry_forward") and "carry_forward" not in values:
        values.append("carry_forward")
    return values


def _requalify_carry_forward(
    domain: str,
    carried: dict[str, Any],
    relation_gate: Callable[[str, str, str], Any] | None,
) -> dict[str, Any]:
    keyword = " ".join(str(carried.get("keyword") or "").split())
    parent = " ".join(str(carried.get("parent_anchor") or "").split())
    if parent:
        relation, reason = _relation(relation_gate, domain, keyword, parent)
    else:
        prior_relation = str(carried.get("domain_relation") or "").strip()
        prior_reason = str(carried.get("domain_relation_reason") or "").strip()
        if prior_relation in {"in_scope", "out_of_scope", "unknown"} and prior_reason:
            relation, reason = prior_relation, prior_reason
        else:
            relation = "unknown"
            reason = "carry-forward record lacks parent_anchor/domain evidence; manual review required"
    return {
        "domain": domain,
        **carried,
        "keyword": keyword,
        "parent_anchor": parent or carried.get("parent_anchor"),
        "domain_relation": relation,
        "domain_relation_reason": reason,
        "discovery_source": "carry_forward",
        "carry_forward": True,
    }


def _merge_candidate_pool(
    domain: str,
    current_candidates: list[dict[str, Any]],
    database: dict[str, Any],
    relation_gate: Callable[[str, str, str], Any] | None,
    max_total_candidates: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    pooled: list[dict[str, Any]] = []
    overflow: list[dict[str, Any]] = []
    by_keyword: dict[str, int] = {}

    def add(candidate: dict[str, Any]) -> None:
        identity = canonical_keyword(candidate.get("keyword"))
        if not identity:
            return
        if identity in by_keyword:
            current = pooled[by_keyword[identity]]
            current["discovery_sources"] = list(dict.fromkeys(_candidate_sources(current) + _candidate_sources(candidate)))
            for field, value in candidate.items():
                if current.get(field) is None:
                    current[field] = value
            return
        enriched = {"domain": domain, **candidate}
        enriched["candidate_id"] = _stable_candidate_id(domain, enriched.get("keyword"))
        enriched["discovery_sources"] = _candidate_sources(enriched)
        if len(pooled) >= max_total_candidates:
            overflow.append(
                {
                    **enriched,
                    "acquisition_status": "not_attempted",
                    "acquisition_reason": "batch_candidate_limit",
                    "delivery_eligible": False,
                    "final_disposition": "not_attempted_batch_limit",
                }
            )
            return
        by_keyword[identity] = len(pooled)
        pooled.append(enriched)

    for candidate in current_candidates:
        add(candidate)
    for carried in carry_forward(database):
        if canonical_keyword(carried.get("domain")) != canonical_keyword(domain):
            continue
        add(_requalify_carry_forward(domain, carried, relation_gate))
    return pooled, overflow


def _parse_workflow_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _apply_collection_admission(
    ledger: list[dict[str, Any]], database: dict[str, Any], as_of: datetime
) -> None:
    records = database.get("records") if isinstance(database, dict) else []
    history: dict[tuple[str, str], dict[str, Any]] = {}
    for record in records if isinstance(records, list) else []:
        if not isinstance(record, dict):
            continue
        key = (canonical_keyword(record.get("domain")), canonical_keyword(record.get("keyword")))
        if key[1]:
            history[key] = record
    now_value = as_of if as_of.tzinfo is not None else as_of.replace(tzinfo=timezone.utc)
    now_value = now_value.astimezone(timezone.utc)
    for row in ledger:
        if row.get("domain_relation") != "in_scope" or row.get("acquisition_status") != "not_started":
            continue
        prior = history.get((canonical_keyword(row.get("domain")), canonical_keyword(row.get("keyword"))))
        if not prior:
            continue
        monitoring_state = str(prior.get("monitoring_state") or "").strip()
        next_review = _parse_workflow_time(prior.get("next_review_at"))
        row["monitoring_state"] = monitoring_state or row.get("monitoring_state")
        row["next_review_at"] = prior.get("next_review_at")
        if monitoring_state == "paused_review":
            row.update(
                acquisition_status="not_attempted",
                acquisition_reason="paused_review",
                verification_status="not_run",
                delivery_eligible=False,
                final_disposition="paused_review",
            )
        elif next_review is not None and next_review > now_value:
            row.update(
                acquisition_status="not_attempted",
                acquisition_reason="review_not_due",
                verification_status="not_run",
                delivery_eligible=False,
                final_disposition="retry_scheduled",
            )


def _timeline_points(payload: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    context = payload if isinstance(payload, dict) else {}
    series = context.get("series") or context.get("google_trends_series") if isinstance(context, dict) else None
    if not isinstance(series, list):
        if isinstance(payload, list):
            series = payload
            context = {}
        else:
            raise ValueError("timeline payload must contain a series list")
    points: list[dict[str, Any]] = []
    for index, point in enumerate(series):
        if not isinstance(point, dict) or point.get("time") in (None, "") or "value" not in point:
            raise ValueError(f"timeline point {index} is incomplete")
        points.append(point)
    if len(points) < 2:
        raise ValueError("timeline payload requires at least two observed points")
    return points, context


def _point_time(value: Any) -> str:
    try:
        timestamp = float(str(value))
    except (TypeError, ValueError):
        text = str(value).strip()
        if not text:
            raise ValueError("timeline point time is missing")
        return text
    if timestamp <= 0:
        raise ValueError("timeline point timestamp must be positive")
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def _failure_type(exc: Exception | str) -> str:
    text = str(exc).casefold()
    if "screenshot" in text and "timeout" in text:
        return "screenshot_timeout"
    if "screenshot" in text:
        return "screenshot_failed"
    if "payload" in text and ("not observed" in text or "not_observed" in text):
        return "payload_not_observed"
    if "target page" in text or "browser has been closed" in text or "context or browser" in text:
        return "browser_closed"
    if "stage" in text and "validation" in text:
        return "stage_validation_failed"
    return "collector_failed"


def _new_ledger_row(candidate: dict[str, Any]) -> dict[str, Any]:
    relation = str(candidate.get("domain_relation") or "unknown")
    if relation == "out_of_scope":
        acquisition_status, reason, disposition = "not_applicable", "domain_out_of_scope", "excluded_out_of_scope"
    elif relation != "in_scope":
        acquisition_status, reason, disposition = "not_applicable", "domain_review_required", "pending_domain_review"
    else:
        acquisition_status, reason, disposition = "not_started", None, "pending_evidence"
    return {
        **candidate,
        "candidate_id": candidate.get("candidate_id") or _stable_candidate_id(candidate.get("domain"), candidate.get("keyword")),
        "acquisition_status": acquisition_status,
        "acquisition_reason": reason,
        "verification_status": "not_run",
        "observed_windows": [],
        "failed_windows": [],
        "window_attempts": [],
        "current_classification_status": "not_run",
        "classification_status": None,
        "route": None,
        "delivery_eligible": False,
        "final_disposition": disposition,
    }


def _observation_rows(candidate: dict[str, Any], time_window: str, requested_timeframe: str, payload: Any) -> list[dict[str, Any]]:
    series, context = _timeline_points(payload)
    evidence_ref = context.get("google_trends_evidence_ref") or context.get("raw_evidence_ref")
    screenshot_ref = context.get("google_trends_screenshot_ref") or context.get("screenshot_ref")
    actual_resolution = context.get("actual_resolution") or "unknown"
    rows = []
    for point in series:
        rows.append(
            {
                "keyword": candidate["keyword"],
                "domain": candidate.get("domain"),
                "candidate_id": candidate.get("candidate_id"),
                "domain_relation": candidate.get("domain_relation"),
                "domain_relation_reason": candidate.get("domain_relation_reason"),
                "root_id": candidate.get("root_id"),
                "root_relation": candidate.get("root_relation"),
                "root_candidate_hypothesis": candidate.get("root_candidate_hypothesis"),
                "variant_subtype": candidate.get("variant_subtype"),
                "variant_evidence": candidate.get("variant_evidence"),
                "previous_status": candidate.get("previous_status"),
                "first_observed_at": candidate.get("first_observed_at"),
                "observed_at": _point_time(point["time"]),
                "source": "google_trends",
                "source_type": "interest_over_time",
                "source_url": context.get("source_url"),
                "signal_value": point["value"],
                "signal_unit": "normalized_interest_index",
                "country": context.get("google_trends_market") or context.get("market") or "US",
                "time_window": time_window,
                "metric_source": "google_trends",
                "metric_database": context.get("google_trends_market") or context.get("market") or "US",
                "requested_timeframe": context.get("requested_timeframe") or requested_timeframe,
                "actual_resolution": actual_resolution,
                "evidence_ref": evidence_ref,
                "screenshot_ref": screenshot_ref,
                "raw_evidence_ref": evidence_ref,
                "acquisition_status": "data_acquired",
                "verification_status": "verified",
            }
        )
    return rows


def _collect_timelines(
    ledger: list[dict[str, Any]],
    timeline_fetcher: Callable[[str, str], Any],
    timeframe_specs: tuple[tuple[str, str], ...],
    throttle: Any,
    blockers: list[dict[str, Any]],
    *,
    max_consecutive_collection_failures: int,
    max_collection_retries: int,
) -> list[dict[str, Any]]:
    if max_consecutive_collection_failures < 1 or max_collection_retries < 0:
        raise ValueError("collection failure limit must be positive and retries non-negative")
    observations: list[dict[str, Any]] = []
    consecutive_failures = 0
    circuit_open = False

    for row in ledger:
        if row.get("domain_relation") != "in_scope" or row.get("acquisition_status") != "not_started":
            continue
        all_windows_verified = True
        saw_data = False
        valid_no_data = False
        for time_window, requested_timeframe in timeframe_specs:
            if circuit_open:
                row["window_attempts"].append({"time_window": time_window, "status": "not_attempted", "reason": "collection_circuit_open", "attempts": 0})
                row["failed_windows"].append(time_window)
                all_windows_verified = False
                continue

            final_error: Exception | None = None
            final_failure_type = None
            handled = False
            for attempt in range(max_collection_retries + 1):
                try:
                    payload = _call(timeline_fetcher, (row["keyword"], requested_timeframe), throttle)
                    context = payload if isinstance(payload, dict) else {}
                    acquisition = str(context.get("acquisition_status") or "data_acquired")
                    verification = str(context.get("verification_status") or "verified")
                    if verification != "verified":
                        reason = context.get("failure_type") or context.get("failure_reason") or "pending_evidence"
                        raise RuntimeError(str(reason))
                    if acquisition == "valid_no_data":
                        row["window_attempts"].append({"time_window": time_window, "status": "valid_no_data", "attempts": attempt + 1, "raw_evidence_ref": context.get("raw_evidence_ref")})
                        row["observed_windows"].append(time_window)
                        valid_no_data = True
                        consecutive_failures = 0
                        handled = True
                        all_windows_verified = False
                        break
                    if context.get("delivery_eligible") is False:
                        reason = context.get("failure_type") or context.get("failure_reason") or "pending_evidence"
                        raise RuntimeError(str(reason))
                    rows = _observation_rows(row, time_window, requested_timeframe, payload)
                    observations.extend(rows)
                    row["window_attempts"].append({"time_window": time_window, "status": "verified", "attempts": attempt + 1, "observation_count": len(rows)})
                    row["observed_windows"].append(time_window)
                    saw_data = True
                    consecutive_failures = 0
                    handled = True
                    break
                except HumanInterventionRequired:
                    raise
                except Exception as exc:
                    final_error = exc
                    final_failure_type = _failure_type(exc)
                    if attempt < max_collection_retries:
                        continue
            if handled:
                continue

            all_windows_verified = False
            row["failed_windows"].append(time_window)
            row["window_attempts"].append({"time_window": time_window, "status": "failed", "failure_type": final_failure_type, "reason": str(final_error), "attempts": max_collection_retries + 1})
            consecutive_failures += 1
            blockers.append({"status": "BLOCKED", "stage": "trends_timeline", "candidate_id": row["candidate_id"], "keyword": row["keyword"], "time_window": time_window, "failure_type": final_failure_type, "reason": str(final_error)})
            if consecutive_failures >= max_consecutive_collection_failures:
                circuit_open = True
                blockers.append({"status": "BLOCKED", "stage": "trends_timeline", "failure_type": "collection_circuit_open", "reason": f"stopped after {consecutive_failures} consecutive collection failures"})

        if row["failed_windows"]:
            not_attempted = all(item.get("status") == "not_attempted" for item in row["window_attempts"])
            row["acquisition_status"] = "not_attempted" if not_attempted else "failed"
            row["acquisition_reason"] = "collection_circuit_open" if not_attempted else "required_window_failed"
            row["verification_status"] = "not_run" if not_attempted else "pending_evidence"
        elif valid_no_data and not saw_data:
            row["acquisition_status"] = "valid_no_data"
            row["acquisition_reason"] = "source_returned_no_timeline_data"
            row["verification_status"] = "verified_no_data"
            row["final_disposition"] = "valid_no_data"
        elif all_windows_verified and saw_data and len(row["observed_windows"]) == len(timeframe_specs):
            row["acquisition_status"] = "data_acquired"
            row["acquisition_reason"] = None
            row["verification_status"] = "verified"
        else:
            row["acquisition_status"] = "failed"
            row["acquisition_reason"] = "incomplete_required_windows"
            row["verification_status"] = "pending_evidence"

    if circuit_open:
        for row in ledger:
            if row.get("domain_relation") != "in_scope" or row.get("acquisition_status") != "not_started":
                continue
            row["acquisition_status"] = "not_attempted"
            row["acquisition_reason"] = "collection_circuit_open"
            row["verification_status"] = "not_run"
            row["failed_windows"] = [window for window, _ in timeframe_specs]
            row["window_attempts"] = [
                {"time_window": window, "status": "not_attempted", "reason": "collection_circuit_open", "attempts": 0}
                for window, _ in timeframe_specs
            ]
    return observations


def _timeline_observations(
    candidates: list[dict[str, Any]],
    timeline_fetcher: Callable[[str, str], Any],
    *,
    timeframe_specs: tuple[tuple[str, str], ...] = TIMEFRAME_DEFAULTS,
    throttle: Any = None,
    blockers: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Backward-compatible timeline entry point used by older callers/tests.

    Legacy candidate rows predate domain_relation, so this adapter treats them
    as already admitted and delegates immediately to the bounded collector. A
    NEEDS_HUMAN signal is re-raised without attempting the next keyword/window.
    """
    ledger = []
    for candidate in candidates:
        admitted = dict(candidate)
        admitted.setdefault("domain_relation", "in_scope")
        ledger.append(_new_ledger_row(admitted))
    return _collect_timelines(
        ledger,
        timeline_fetcher,
        timeframe_specs,
        throttle,
        blockers if blockers is not None else [],
        max_consecutive_collection_failures=max(1, len(ledger) * max(1, len(timeframe_specs))),
        max_collection_retries=0,
    )


def _eligible_candidate_ids(ledger: list[dict[str, Any]]) -> set[str]:
    return {
        row["candidate_id"]
        for row in ledger
        if row.get("domain_relation") == "in_scope"
        and row.get("acquisition_status") == "data_acquired"
        and row.get("verification_status") == "verified"
    }


def _classify_and_route(
    domain: str,
    ledger: list[dict[str, Any]],
    observations: list[dict[str, Any]],
    as_of: datetime,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    eligible_ids = _eligible_candidate_ids(ledger)
    eligible_observations = [row for row in observations if row.get("candidate_id") in eligible_ids]
    canonical = _load_canonical_pipeline().classify_and_route_rows(eligible_observations, as_of)
    classified = canonical["classified"]
    routes = canonical["routed"]
    for row in classified:
        row["domain"] = row.get("domain") or domain
        row["acquisition_status"] = "data_acquired"
        row["current_classification_status"] = "confirmed"
        row["delivery_eligible"] = True
    return canonical["aggregated"], classified, routes


def _finalize_ledger(ledger: list[dict[str, Any]], classified: list[dict[str, Any]], routes: list[dict[str, Any]]) -> None:
    classified_by_id = {row.get("candidate_id"): row for row in classified}
    route_by_id = {row.get("candidate_id"): row for row in routes}
    for row in ledger:
        candidate_id = row["candidate_id"]
        current = classified_by_id.get(candidate_id)
        if current is None:
            if row.get("domain_relation") == "out_of_scope":
                row["final_disposition"] = "excluded_out_of_scope"
            elif row.get("domain_relation") != "in_scope":
                row["final_disposition"] = "pending_domain_review"
            elif row.get("acquisition_status") == "valid_no_data":
                row["final_disposition"] = "valid_no_data"
            elif row.get("acquisition_status") == "not_attempted" and row.get("acquisition_reason") == "batch_candidate_limit":
                row["final_disposition"] = "not_attempted_batch_limit"
            else:
                row["final_disposition"] = "pending_evidence"
            row["delivery_eligible"] = False
            row["current_classification_status"] = "unknown"
            continue
        row["classification_status"] = current.get("status")
        row["signal_type"] = current.get("signal_type")
        row["current_classification_status"] = "confirmed"
        row["delivery_eligible"] = True
        route = route_by_id.get(candidate_id) or {}
        row["route"] = route.get("route")
        row["final_disposition"] = "selection_handoff" if route.get("route") == "selection_handoff" else "monitor_record"


def _reconciliation(ledger: list[dict[str, Any]], classified: list[dict[str, Any]], routes: list[dict[str, Any]]) -> dict[str, Any]:
    delivery_ids = [str(row["candidate_id"]) for row in ledger if row.get("delivery_eligible") is True]
    return _load_canonical_pipeline().reconcile_identity_sets(ledger, classified, routes, delivery_ids)


def run_pipeline(
    related_fetcher: Callable[[str], Any],
    autocomplete_fetcher: Callable[[str], Any] | None = None,
    semrush_fetcher: Callable[[str], Any] | None = None,
    *,
    domain: str,
    explicit_anchors: list[Any] | None = None,
    root_rows: list[dict[str, Any]] | None = None,
    relation_gate: Callable[[str, str, str], Any] | None = None,
    country: str = "US",
    max_depth: int = 2,
    per_anchor_limit: int = 10,
    max_candidates: int = 200,
    max_total_candidates: int | None = None,
    timeline_fetcher: Callable[[str, str], Any] | None = None,
    timeframe_specs: tuple[tuple[str, str], ...] = TIMEFRAME_DEFAULTS,
    max_consecutive_collection_failures: int = 3,
    max_collection_retries: int = 1,
    throttle: Any = None,
    as_of: datetime | None = None,
    discovered_at: str | None = None,
    existing_database: dict[str, Any] | None = None,
    database_path: Path | None = None,
    csv_path: Path | None = None,
) -> dict[str, Any]:
    if not callable(related_fetcher):
        raise ValueError("related_fetcher is required")
    total_limit = int(max_total_candidates if max_total_candidates is not None else max_candidates)
    if total_limit < 1:
        raise ValueError("max_total_candidates must be positive")

    anchors = build_anchor_pool(domain, explicit_anchors, root_rows)
    discovery = discover_rising_bfs(
        domain,
        anchors,
        lambda anchor: _call(related_fetcher, (anchor,), throttle),
        relation_gate=relation_gate,
        max_depth=max_depth,
        per_anchor_limit=per_anchor_limit,
        max_candidates=max_candidates,
    )
    blockers = list(discovery.get("blockers") or [])
    supplemental_evidence: list[dict[str, Any]] = []
    supplemental_candidates: list[dict[str, Any]] = []
    for fetcher, source in ((autocomplete_fetcher, "google_autocomplete"), (semrush_fetcher, "semrush_ideas")):
        if fetcher is None:
            continue
        for anchor in anchors:
            try:
                payload = _call(fetcher, (anchor["keyword"],), throttle)
                if payload is None:
                    continue
                supplemental_evidence.append({"source": source, "anchor": anchor["keyword"], "payload": payload, "recursive": False})
                supplemental_candidates.extend(_supplemental_candidates(domain, anchor, source, payload, relation_gate))
            except HumanInterventionRequired:
                raise
            except Exception as exc:
                blockers.append({"status": "BLOCKED", "stage": source, "anchor": anchor["keyword"], "reason": str(exc)})

    discovered_candidates = list(discovery.get("candidates") or [])
    current_candidates: list[dict[str, Any]] = []
    current_by_keyword: dict[str, int] = {}
    for candidate in discovered_candidates + supplemental_candidates:
        identity = canonical_keyword(candidate.get("keyword"))
        if not identity:
            continue
        if identity in current_by_keyword:
            current = current_candidates[current_by_keyword[identity]]
            current["discovery_sources"] = list(dict.fromkeys(_candidate_sources(current) + _candidate_sources(candidate)))
            continue
        current_by_keyword[identity] = len(current_candidates)
        current_candidates.append({"domain": domain, **candidate})

    database_requested = database_path is not None or csv_path is not None or existing_database is not None
    database_source = _database_snapshot(existing_database, database_path) if database_requested else {"schema_version": 1, "records": []}
    scoped_candidates, overflow = _merge_candidate_pool(domain, current_candidates, database_source, relation_gate, total_limit)
    ledger = [_new_ledger_row(candidate) for candidate in scoped_candidates]
    for candidate in overflow:
        row = _new_ledger_row(candidate)
        row.update(acquisition_status="not_attempted", acquisition_reason="batch_candidate_limit", verification_status="not_run", delivery_eligible=False, final_disposition="not_attempted_batch_limit")
        ledger.append(row)

    run_as_of = as_of or datetime.now(timezone.utc)
    _apply_collection_admission(ledger, database_source, run_as_of)
    observations: list[dict[str, Any]] = []
    if timeline_fetcher is not None:
        observations = _collect_timelines(
            ledger,
            timeline_fetcher,
            timeframe_specs,
            throttle,
            blockers,
            max_consecutive_collection_failures=max_consecutive_collection_failures,
            max_collection_retries=max_collection_retries,
        )

    aggregate_result, classified, routes = _classify_and_route(domain, ledger, observations, run_as_of)
    _finalize_ledger(ledger, classified, routes)
    reconciliation = _reconciliation(ledger, classified, routes)

    database = None
    if database_requested:
        classified_by_id = {row.get("candidate_id"): row for row in classified}
        persistence_rows: list[dict[str, Any]] = []
        for ledger_row in ledger:
            current = classified_by_id.get(ledger_row.get("candidate_id"))
            if current is not None:
                persisted = dict(current)
                for field in ("domain_relation", "domain_relation_reason", "acquisition_status", "acquisition_reason", "verification_status", "final_disposition"):
                    persisted[field] = ledger_row.get(field)
                persisted["delivery_eligible"] = ledger_row.get("delivery_eligible") is True
                persistence_rows.append(persisted)
            else:
                persistence_rows.append(dict(ledger_row))
        database = merge_database(database_source, persistence_rows, routes, discovered_at or _now())
        database["run_status"] = "BLOCKED" if blockers or discovery.get("status") == "BLOCKED" else "PASS"
        database["market"] = country
        database["candidate_scope"] = {"candidate_ids": reconciliation["candidate_ids"], "identity_sha256": reconciliation["identity_sha256"]}
        database["delivery_manifest"] = {"delivery_ids": reconciliation["delivery_ids"], "identity_sha256": reconciliation["identity_sha256"]}
        if database_path is not None and csv_path is not None:
            write_database(database, Path(database_path), Path(csv_path))

    status = "BLOCKED" if blockers or discovery.get("status") == "BLOCKED" else "PASS"
    return {
        "domain": domain,
        "country": country,
        "status": status,
        "recursive_edge_policy": "google_trends_rising_only",
        "supplemental_recursive": False,
        "anchor_pool": anchors,
        "discovery": discovery,
        "supplemental_evidence": supplemental_evidence,
        "candidate_ledger": ledger,
        "candidates": classified,
        "routes": routes,
        "observations": observations,
        "aggregate": aggregate_result,
        "database": database,
        "blockers": blockers,
        "reconciliation": reconciliation,
        "delivery_manifest": {"delivery_ids": reconciliation["delivery_ids"], "identity_sha256": reconciliation["identity_sha256"]},
        "output_artifacts": {},
        "candidate_counts": {"discovered": len(discovered_candidates), "supplemental": len(supplemental_candidates), "ledger": len(ledger), "classified": len(classified), "delivered": reconciliation["delivery_count"]},
    }


def load_root_rows(path: Path) -> list[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _slug(value: str) -> str:
    text = str(value or "").strip()
    readable = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    return f"{readable}-{digest}" if readable else f"item-{digest}"


def _read_structured_partial(output_path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(output_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(payload, dict) and payload.get("acquisition_status"):
        return payload
    return None


def _collector_payload(command: list[str], output_path: Path) -> dict[str, Any]:
    process = subprocess.run(command, text=True, capture_output=True)
    if process.returncode == 3 or "NEEDS_HUMAN" in (process.stderr or ""):
        detail = (process.stderr or "Google verification required (NEEDS_HUMAN)").strip()
        raise HumanInterventionRequired(detail)
    if process.returncode != 0:
        partial = _read_structured_partial(output_path)
        if partial is not None:
            partial["collector_exit_code"] = process.returncode
            partial["collector_stderr"] = (process.stderr or "").strip()[-2000:]
            return partial
        detail = (process.stderr or process.stdout or "collector failed").strip()
        raise RuntimeError(detail[-2000:])
    try:
        payload = json.loads(output_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"collector output is unavailable or invalid: {output_path}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("collector output must be a JSON object")
    return payload


def load_semrush_request_map(paths: list[str | Path]) -> dict[str, Path]:
    indexed: dict[str, Path] = {}
    for raw_path in paths:
        path = Path(raw_path)
        if not path.is_file():
            raise ValueError(f"Semrush request descriptor is missing: {path}")
        try:
            descriptor = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Semrush request descriptor is invalid JSON: {path}") from exc
        if not isinstance(descriptor, dict) or descriptor.get("mode") != "ideas":
            raise ValueError(f"Semrush request descriptor must be an Ideas capture: {path}")
        seed = canonical_keyword(descriptor.get("seed"))
        if not seed:
            raise ValueError(f"Semrush Ideas descriptor seed is missing: {path}")
        previous = indexed.get(seed)
        if previous is not None and previous != path:
            raise ValueError(f"duplicate Semrush Ideas descriptor seed: {seed}")
        indexed[seed] = path
    return indexed


def _validated_semrush_fetcher(*, request_map: dict[str, Path], collector: Path, validator: Path, run_dir: Path, stage_results: list[dict[str, Any]], counter: list[int]) -> Callable[[str], dict[str, Any] | None]:
    def fetch(anchor: str) -> dict[str, Any] | None:
        request = request_map.get(canonical_keyword(anchor))
        if request is None:
            return None
        counter[0] += 1
        prefix = f"{counter[0]:03d}-{_slug(anchor)}-discovery_semrush_ideas"
        output = run_dir / f"{prefix}.json"
        raw_output = run_dir / f"{prefix}.raw.json"
        report = run_dir / f"{prefix}.validation.json"
        payload = _collector_payload([sys.executable, str(collector), "--request", str(request), "--output", str(output), "--raw-output", str(raw_output)], output)
        validation = subprocess.run([sys.executable, str(validator), "--stage", "discovery_semrush_ideas", "--input", str(output), "--report", str(report), "--production"], text=True, capture_output=True)
        validation_payload = json.loads(report.read_text(encoding="utf-8"))
        stage_results.append(validation_payload)
        if validation.returncode != 0 or validation_payload.get("status") != "PASS":
            detail = (validation.stderr or validation.stdout or "stage contract blocked").strip()
            raise RuntimeError(f"stage discovery_semrush_ideas validation BLOCKED: {detail[-2000:]}")
        return payload
    return fetch


def _run_blocker_reason(result: dict[str, Any]) -> str:
    for blocker in result.get("blockers") or []:
        if isinstance(blocker, dict) and str(blocker.get("reason") or "").strip():
            return str(blocker["reason"]).strip()
    return "emerging radar run is blocked"


def write_validated_run_summary(result: dict[str, Any], summary_path: Path, *, validator_path: Path | None = None) -> dict[str, Any]:
    summary_path = Path(summary_path)
    report_path = summary_path.with_name(f"{summary_path.stem}.validation.json")
    receipt_path = report_path.with_suffix(".receipt.json")
    artifacts = dict(result.get("output_artifacts") or {})
    artifacts["run_summary"] = str(summary_path)
    artifacts["emerging_radar_run_validation"] = str(report_path)
    result["output_artifacts"] = artifacts
    stage_record: dict[str, Any] = {"status": result.get("status")}
    if result.get("status") == "PASS":
        stage_record["validation_receipt_ref"] = str(receipt_path)
    else:
        stage_record["blocked_reason"] = _run_blocker_reason(result)
    stages = dict(result.get("stages") or {})
    stages["emerging_radar_run"] = stage_record
    result["stages"] = stages
    _write_json(summary_path, result)

    validator = Path(validator_path) if validator_path else REPO_ROOT / "runtime" / "stage_validator.py"
    command = [sys.executable, str(validator), "--stage", "emerging_radar_run", "--input", str(summary_path), "--report", str(report_path)]
    if result.get("status") == "PASS":
        command.append("--production")
    validation = subprocess.run(command, text=True, capture_output=True)
    report_payload = json.loads(report_path.read_text(encoding="utf-8"))
    if validation.returncode != 0 or report_payload.get("status") != "PASS":
        detail = (validation.stderr or validation.stdout or "emerging_radar_run contract blocked").strip()
        if result.get("status") == "PASS":
            reason = f"emerging_radar_run validation failed: {detail[-2000:]}"
            result["status"] = "BLOCKED"
            result.setdefault("blockers", []).append({"status": "BLOCKED", "stage": "emerging_radar_run", "reason": reason})
            result["stages"]["emerging_radar_run"] = {"status": "BLOCKED", "blocked_reason": reason}
            _write_json(summary_path, result)
        raise RuntimeError(detail[-2000:])
    if result.get("status") == "PASS" and not receipt_path.is_file():
        raise RuntimeError(f"emerging_radar_run validation receipt is unavailable: {receipt_path}")
    return report_payload


def _validated_collector_fetcher(*, collector: Path, validator: Path, stage: str, mode: str, run_dir: Path, evidence_dir: Path, country: str, language: str, timeframe: str | None, stage_results: list[dict[str, Any]], counter: list[int]) -> Callable[..., dict[str, Any]]:
    def fetch(identity: str) -> dict[str, Any]:
        counter[0] += 1
        prefix = f"{counter[0]:03d}-{_slug(identity)}-{stage}"
        output = run_dir / f"{prefix}.json"
        report = run_dir / f"{prefix}.validation.json"
        command = [sys.executable, str(collector), mode]
        if mode == "autocomplete":
            command.extend(["--seed", identity, "--country", country, "--language", language])
        else:
            command.extend(["--keyword", identity, "--market", country])
            if timeframe is not None:
                command.extend(["--timeframe", timeframe])
        command.extend(["--evidence-dir", str(evidence_dir), "--output", str(output)])
        payload = _collector_payload(command, output)
        verification_status = payload.get("verification_status")
        delivery_eligible = payload.get("delivery_eligible")
        if verification_status not in (None, "verified") or delivery_eligible is False:
            stage_results.append({"stage": stage, "status": "BLOCKED" if verification_status == "pending_evidence" else "OBSERVED_NO_DATA", "keyword": identity, "acquisition_status": payload.get("acquisition_status"), "failure_type": payload.get("failure_type")})
            if stage == "trends_timeline":
                return payload
            if payload.get("acquisition_status") == "valid_no_data" and verification_status == "verified":
                return payload
            reason = payload.get("failure_type") or payload.get("failure_reason") or "evidence_incomplete"
            raise RuntimeError(f"stage {stage} evidence incomplete: {reason}")
        validation = subprocess.run([sys.executable, str(validator), "--stage", stage, "--input", str(output), "--report", str(report), "--production"], text=True, capture_output=True)
        validation_payload = json.loads(report.read_text(encoding="utf-8"))
        stage_results.append(validation_payload)
        if validation.returncode != 0 or validation_payload.get("status") != "PASS":
            detail = (validation.stderr or validation.stdout or "stage contract blocked").strip()
            raise RuntimeError(f"stage {stage} validation BLOCKED: {detail[-2000:]}")
        return payload
    return fetch


def _parse_as_of(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _live_runner(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = Path(args.run_dir)
    evidence_dir = run_dir / "evidence"
    run_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    stage_results: list[dict[str, Any]] = []
    counter = [0]
    google_collector = REPO_ROOT / "runtime" / "collectors" / "google_live_collector.py"
    trends_collector = REPO_ROOT / "runtime" / "collectors" / "google_trends_collector.py"
    validator = REPO_ROOT / "runtime" / "stage_validator.py"

    related_fetcher = _validated_collector_fetcher(collector=trends_collector, validator=validator, stage="trends_related", mode="trends_related", run_dir=run_dir, evidence_dir=evidence_dir, country=args.country, language=args.language, timeframe=args.related_timeframe, stage_results=stage_results, counter=counter)
    autocomplete_fetcher = None
    if args.with_autocomplete:
        autocomplete_fetcher = _validated_collector_fetcher(collector=google_collector, validator=validator, stage="discovery_autocomplete", mode="autocomplete", run_dir=run_dir, evidence_dir=evidence_dir, country=args.country, language=args.language, timeframe=None, stage_results=stage_results, counter=counter)
    semrush_fetcher = None
    if args.semrush_request:
        semrush_fetcher = _validated_semrush_fetcher(request_map=load_semrush_request_map(args.semrush_request), collector=REPO_ROOT / "runtime" / "collectors" / "semrush_relay_collector.py", validator=validator, run_dir=run_dir, stage_results=stage_results, counter=counter)

    def timeline_fetcher(keyword: str, requested_timeframe: str) -> dict[str, Any]:
        return _validated_collector_fetcher(collector=trends_collector, validator=validator, stage="trends_timeline", mode="trends_timeline", run_dir=run_dir, evidence_dir=evidence_dir, country=args.country, language=args.language, timeframe=requested_timeframe, stage_results=stage_results, counter=counter)(keyword)

    root_rows = load_root_rows(Path(args.root_library)) if args.root_library else []
    as_of = _parse_as_of(args.as_of)
    result = run_pipeline(
        related_fetcher,
        autocomplete_fetcher,
        semrush_fetcher,
        domain=args.domain,
        explicit_anchors=args.anchor,
        root_rows=root_rows,
        country=args.country,
        max_depth=args.max_depth,
        per_anchor_limit=args.per_anchor_limit,
        max_candidates=args.max_candidates,
        max_total_candidates=args.max_total_candidates,
        timeline_fetcher=timeline_fetcher,
        timeframe_specs=(("5y", args.long_timeframe), ("12m", args.medium_timeframe), ("90d", args.recent_timeframe)),
        max_consecutive_collection_failures=args.max_consecutive_collection_failures,
        max_collection_retries=args.max_collection_retries,
        as_of=as_of,
        discovered_at=as_of.isoformat(),
        database_path=run_dir / "emerging-keywords.json",
        csv_path=run_dir / "emerging-keywords.csv",
    )
    result["as_of"] = as_of.isoformat()
    result["stage_validations"] = stage_results
    result["output_artifacts"] = {"run_summary": str(Path(args.output)), "database": str(run_dir / "emerging-keywords.json"), "csv": str(run_dir / "emerging-keywords.csv"), "evidence_dir": str(evidence_dir)}
    write_validated_run_summary(result, Path(args.output), validator_path=validator)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", required=True)
    parser.add_argument("--anchor", action="append", default=[])
    parser.add_argument("--country", default="US")
    parser.add_argument("--language", default="en")
    parser.add_argument("--as-of", help="fixed ISO-8601 evidence cutoff for reproducible runs")
    parser.add_argument("--related-timeframe", default="today 12-m")
    parser.add_argument("--long-timeframe", default="today 5-y")
    parser.add_argument("--medium-timeframe", default="today 12-m")
    parser.add_argument("--recent-timeframe", default="today 3-m")
    parser.add_argument("--max-depth", type=int, default=2)
    parser.add_argument("--per-anchor-limit", type=int, default=10)
    parser.add_argument("--max-candidates", type=int, default=200)
    parser.add_argument("--max-total-candidates", type=int, default=200)
    parser.add_argument("--max-collection-retries", type=int, default=1)
    parser.add_argument("--max-consecutive-collection-failures", type=int, default=3)
    parser.add_argument("--root-library")
    parser.add_argument("--with-autocomplete", action="store_true")
    parser.add_argument("--semrush-request", action="append", default=[], help="current authenticated Semrush Ideas descriptor; repeat once per captured seed")
    parser.add_argument("--run-dir", default=".seo-run/emerging-radar-live")
    parser.add_argument("--output", default=".seo-run/emerging-radar-live/run-summary.json")
    args = parser.parse_args()
    try:
        result = _live_runner(args)
    except HumanInterventionRequired as exc:
        print(f"\n{'=' * 70}", file=sys.stderr)
        print(f"NEEDS_HUMAN: Radar paused. Google requires manual verification.\n{exc}", file=sys.stderr)
        print(f"{'=' * 70}\n", file=sys.stderr)
        return 3
    except Exception as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"status": result["status"], "output": result["output_artifacts"], "reconciliation": result["reconciliation"]}, ensure_ascii=False))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
