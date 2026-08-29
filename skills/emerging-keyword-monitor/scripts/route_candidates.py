#!/usr/bin/env python3
"""Route classified emerging-demand candidates to downstream skills without making SEO selection decisions."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

CONFIRMED_STATUSES = {"emerging", "breakout"}
NON_ACTIONABLE_STATUSES = {"mature", "noise", "insufficient_evidence"}
CANONICAL_SIGNAL_TYPES = {"net_new", "breakout", "emerging_variant", "unknown"}
SELECTION_FIELDS = (
    "keyword",
    "root_id",
    "signal_type",
    "variant_subtype",
    "first_observed_at",
    "age_days",
    "growth_rate",
    "persistence",
    "source_count",
    "source_evidence",
    "volume",
    "kd",
    "cpc",
    "intitle_results",
    "metric_status",
    "metric_provenance",
    "metric_compatibility_status",
    "kgr_compatibility_status",
    "kgr",
    "supply_signal",
    "status",
    "confidence",
)


def is_missing(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip().lower() in {"", "unknown", "null", "none", "n/a", "na"})


def load_candidates(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("candidates", "rows"):
            if isinstance(payload.get(key), list):
                return payload[key]
    raise ValueError("input must be a JSON array/object with candidates|rows, or CSV")


def selection_handoff(candidate: dict[str, Any]) -> dict[str, Any]:
    handoff = {field: candidate.get(field) for field in SELECTION_FIELDS}
    handoff["growth"] = candidate.get("growth_rate")
    return handoff


def has_valid_classifier_output(candidate: dict[str, Any]) -> bool:
    """Accept confirmed states only from the structured classifier contract."""
    if candidate.get("classification_status") != "valid":
        return False
    errors = candidate.get("classification_errors")
    if isinstance(errors, str):
        return errors.strip() == "[]"
    return errors == []


def root_watch_handoff(candidate: dict[str, Any], reason: Any) -> dict[str, Any]:
    return {
        "keyword": str(candidate.get("keyword") or "").strip(),
        "signal_type": candidate.get("signal_type"),
        "status": candidate.get("status"),
        "first_observed_at": candidate.get("first_observed_at"),
        "source_evidence": candidate.get("source_evidence"),
        "root_watch_reason": reason,
    }


def route_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    keyword = str(candidate.get("keyword") or "").strip()
    status = candidate.get("status")
    relation = candidate.get("root_relation")
    root_id = candidate.get("root_id")

    if is_missing(relation):
        relation = "existing_root" if not is_missing(root_id) else "unresolved"

    result = {
        "keyword": keyword,
        "status": status,
        "root_relation": relation,
        "route": "no_handoff",
        "handoff": None,
        "mutates_root_library": False,
        "route_reason": "No downstream handoff for the current state.",
    }

    if status in NON_ACTIONABLE_STATUSES:
        return result

    if status in CONFIRMED_STATUSES:
        if not has_valid_classifier_output(candidate):
            result["route_reason"] = "A confirmed route requires a valid classify_emergence.py output."
            return result
        if candidate.get("signal_type") not in CANONICAL_SIGNAL_TYPES - {"unknown"}:
            result["route_reason"] = "A confirmed route requires a canonical signal_type from classify_emergence.py."
            return result

    if relation == "unresolved":
        result["route"] = "new_root_watchlist"
        result["handoff"] = root_watch_handoff(candidate, candidate.get("root_watch_reason"))
        result["route_reason"] = "No stable root relationship is established; retain the candidate for root watch."
        return result

    if relation == "root_candidate":
        hypothesis = candidate.get("root_candidate_hypothesis")
        if status not in CONFIRMED_STATUSES:
            result["route"] = "new_root_watchlist"
            result["handoff"] = root_watch_handoff(
                candidate,
                "root-candidate hypothesis is retained until emergence is confirmed",
            )
            result["route_reason"] = "Root-candidate handoff requires status emerging or breakout; unconfirmed demand remains on the root watchlist."
            return result
        if is_missing(hypothesis):
            result["route"] = "new_root_watchlist"
            result["handoff"] = root_watch_handoff(
                candidate,
                "root_candidate annotation lacks a reviewable hypothesis",
            )
            result["route_reason"] = "Root-candidate routing requires an explicit reviewable cluster hypothesis."
            return result
        result["route"] = "root_candidate_handoff"
        result["handoff"] = {
            "keyword": keyword,
            "signal_type": candidate.get("signal_type"),
            "status": status,
            "first_observed_at": candidate.get("first_observed_at"),
            "source_evidence": candidate.get("source_evidence"),
            "root_candidate_hypothesis": hypothesis,
            "related_keywords": candidate.get("related_keywords"),
        }
        result["route_reason"] = "Confirmed emerging demand has an explicit stable-demand-family hypothesis ready for keyword-root-library review."
        return result

    if relation == "existing_root":
        if status in CONFIRMED_STATUSES and not is_missing(root_id):
            result["route"] = "selection_handoff"
            result["handoff"] = selection_handoff(candidate)
            result["route_reason"] = "Confirmed emerging demand maps to an existing root and is ready for downstream SEO selection."
        elif status in {"new_signal", "watch"}:
            result["route"] = "monitor_only"
            result["route_reason"] = "The root is known, but emergence is not yet confirmed."
        else:
            result["route_reason"] = "Existing-root candidate is not in a confirmed emerging state."
        return result

    result["route"] = "new_root_watchlist"
    result["handoff"] = root_watch_handoff(candidate, f"unknown root_relation={relation}")
    result["route_reason"] = "Unknown root relationship is retained for review rather than guessed."
    return result


def emit(routes: list[dict[str, Any]], fmt: str) -> None:
    if fmt == "json":
        print(json.dumps({"routes": routes}, ensure_ascii=False, indent=2, allow_nan=False))
        return
    if not routes:
        return
    fields = sorted({key for row in routes for key in row})
    writer = csv.DictWriter(__import__("sys").stdout, fieldnames=fields)
    writer.writeheader()
    for row in routes:
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
    args = parser.parse_args()
    routes = [route_candidate(candidate) for candidate in load_candidates(Path(args.input))]
    emit(routes, args.format)


if __name__ == "__main__":
    main()
