#!/usr/bin/env python3
"""Classify evidence-backed emerging search demand with an explainable state machine."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

BASE = Path(__file__).resolve().parents[1]
THRESHOLDS_PATH = BASE / "references" / "thresholds.json"
VARIANT_SUBTYPES = {"new_expression", "typo", "modifier_shift"}
STATE_VALUES = {"new_signal", "watch", "emerging", "breakout", "mature", "noise", "insufficient_evidence"}
UNKNOWN_FIELDS = (
    "root_id",
    "first_observed_at",
    "estimated_birth_window",
    "age_days",
    "baseline_signal",
    "recent_signal",
    "growth_rate",
    "acceleration",
    "persistence",
    "anchor_event",
    "anchor_event_date",
    "volume",
    "kd",
    "cpc",
    "intitle_results",
    "serp_dedicated_pages",
    "serp_ugc_pages",
    "serp_intent_mismatch",
    "emd_status",
)


def load_thresholds() -> dict[str, Any]:
    return json.loads(THRESHOLDS_PATH.read_text(encoding="utf-8"))


def is_missing(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip().lower() in {"", "unknown", "null", "none", "n/a", "na"})


def finite_number(value: Any) -> float | None:
    if is_missing(value) or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def valid_nonnegative(value: Any) -> bool:
    number = finite_number(value)
    return number is not None and number >= 0


def verified_source_count(candidate: dict[str, Any]) -> int:
    names = {
        str(item.get("source") or "").strip()
        for item in candidate.get("source_evidence") or []
        if item.get("provenance_status") == "verified" and str(item.get("source") or "").strip()
    }
    return len(names)


def derive_metrics(row: dict[str, Any]) -> tuple[str, float | None, str | None, list[str]]:
    errors: list[str] = []
    volume = finite_number(row.get("volume"))
    kd = finite_number(row.get("kd"))
    cpc = finite_number(row.get("cpc"))
    intitle = finite_number(row.get("intitle_results"))

    if not is_missing(row.get("volume")) and (volume is None or volume < 0):
        errors.append("volume")
    if not is_missing(row.get("kd")) and (kd is None or kd < 0 or kd > 100):
        errors.append("kd")
    if not is_missing(row.get("cpc")) and (cpc is None or cpc < 0):
        errors.append("cpc")
    if not is_missing(row.get("intitle_results")) and (intitle is None or intitle < 0 or not intitle.is_integer()):
        errors.append("intitle_results")

    if errors:
        return "invalid", None, None, errors

    metric_status = "complete" if volume is not None and kd is not None and cpc is not None else "incomplete"
    kgr = None
    if volume is not None and volume > 0 and intitle is not None:
        kgr = intitle / volume
    if intitle is not None and volume is None:
        supply_signal = "low_supply_signal"
    elif intitle is not None:
        supply_signal = "observed_supply"
    else:
        supply_signal = None
    return metric_status, kgr, supply_signal, []


def classify_candidate(candidate: dict[str, Any], thresholds: dict[str, Any]) -> dict[str, Any]:
    row = dict(candidate)
    evidence_used: list[str] = []
    errors: list[str] = []

    keyword = str(row.get("keyword") or "").strip()
    if not keyword:
        errors.append("keyword")

    metric_status, kgr, supply_signal, metric_errors = derive_metrics(row)
    errors.extend(metric_errors)
    row["metric_status"] = metric_status
    row["kgr"] = kgr
    row["supply_signal"] = supply_signal

    primary = row.get("primary_series") if isinstance(row.get("primary_series"), dict) else {}
    baseline = finite_number(row.get("baseline_signal"))
    recent = finite_number(row.get("recent_signal"))
    growth = finite_number(row.get("growth_rate"))
    persistence = finite_number(row.get("persistence"))
    age_days = finite_number(row.get("age_days"))
    baseline_obs = int(finite_number(primary.get("baseline_observations")) or 0)
    recent_obs = int(finite_number(primary.get("recent_observations")) or row.get("persistence_observations") or 0)
    peak = finite_number(primary.get("peak_signal"))
    latest = finite_number(primary.get("latest_signal"))
    verified_sources = verified_source_count(row)
    source_count = int(finite_number(row.get("source_count")) or 0)

    variant_subtype = row.get("variant_subtype")
    if not is_missing(variant_subtype):
        variant_subtype = str(variant_subtype).strip()
        if variant_subtype not in VARIANT_SUBTYPES:
            errors.append("variant_subtype")
        elif is_missing(row.get("variant_evidence")):
            errors.append("variant_evidence")
    else:
        variant_subtype = None
    row["variant_subtype"] = variant_subtype

    evidence_cfg = thresholds["evidence"]
    confirmed_temporal = (
        recent is not None
        and recent > 0
        and recent_obs >= evidence_cfg["min_recent_observations_confirmed"]
        and persistence is not None
        and persistence >= evidence_cfg["min_persistence_confirmed"]
    )
    has_verified_series = verified_sources >= 1 and primary.get("provenance_status") == "verified"

    signal_type = None
    status = "insufficient_evidence"
    reason = "Evidence is insufficient for a temporal classification."

    if errors:
        status = "insufficient_evidence"
        reason = "Candidate contains invalid classification inputs; repair them before temporal classification."
    elif recent is None or not primary:
        status = "insufficient_evidence"
        reason = "No comparable recent signal series is available."
    elif not has_verified_series:
        status = "insufficient_evidence"
        reason = "Comparable signal data exists, but no primary series has complete provenance."
    else:
        evidence_used.append(f"verified_sources={verified_sources}")
        evidence_used.append(f"recent_observations={recent_obs}")
        if persistence is not None:
            evidence_used.append(f"persistence={persistence:.4g}")
        if baseline is not None:
            evidence_used.append(f"baseline_signal={baseline:.4g}")
        if recent is not None:
            evidence_used.append(f"recent_signal={recent:.4g}")

        noise_cfg = thresholds["noise"]
        decay_ratio = None
        if peak is not None and peak > 0 and latest is not None:
            decay_ratio = latest / peak
        durable = row.get("durable_search_intent")
        repeatable_fit = row.get("repeatable_page_or_product_fit")
        is_noise = (
            recent_obs >= evidence_cfg["min_recent_observations_confirmed"]
            and persistence is not None
            and persistence <= noise_cfg["max_persistence"]
            and decay_ratio is not None
            and decay_ratio <= noise_cfg["max_latest_to_peak_ratio"]
            and durable is not True
            and repeatable_fit is not True
        )

        if is_noise:
            status = "noise"
            reason = "Observed spike decayed sharply across follow-up observations and lacks confirmed durable/repeatable search-task evidence."
            evidence_used.append(f"latest_to_peak_ratio={decay_ratio:.4g}")
        elif recent_obs <= 1:
            status = "new_signal"
            reason = "A real recent signal is observed, but there is only one recent observation so persistence is not established."
        elif not confirmed_temporal:
            status = "watch"
            reason = "Repeated signal exists, but persistence or recent observation depth is below the confirmation threshold."
        elif variant_subtype is not None:
            signal_type = "emerging_variant"
            status = "emerging"
            reason = f"Persistent recent demand is paired with an explicit {variant_subtype} relationship to an existing search expression."
            evidence_used.append(f"variant_subtype={variant_subtype}")
        elif (
            baseline is not None
            and baseline == 0
            and baseline_obs >= evidence_cfg["min_baseline_observations"]
        ):
            signal_type = "net_new"
            status = "emerging"
            reason = "Historical comparable observations show no sustained relative signal, while recent observations are persistent; this is newly observed demand within the evidence window."
            evidence_used.append(f"baseline_observations={baseline_obs}")
        elif (
            baseline is not None
            and baseline > 0
            and growth is not None
            and growth >= thresholds["breakout"]["growth_rate_min"]
        ):
            signal_type = "breakout"
            status = "breakout"
            reason = "A positive historical baseline exists and recent persistent signal is materially above that baseline."
            evidence_used.append(f"growth_rate={growth:.4g}")
        elif (
            age_days is not None
            and age_days >= thresholds["mature"]["age_days_min"]
            and baseline is not None
            and baseline > 0
            and growth is not None
            and abs(growth) < thresholds["mature"]["max_abs_growth_rate"]
        ):
            status = "mature"
            reason = "The keyword has a long positive baseline and no material recent acceleration, so it is not treated as emerging."
            evidence_used.append(f"age_days={int(age_days)}")
            evidence_used.append(f"growth_rate={growth:.4g}")
        else:
            status = "watch"
            reason = "Persistent demand is real, but current evidence does not match net-new, breakout, variant, mature, or noise criteria."

    if status in {"emerging", "breakout"}:
        confidence = "high" if source_count >= thresholds["confidence"]["cross_source_min"] and verified_sources >= thresholds["confidence"]["cross_source_min"] else "medium"
    else:
        confidence = "low" if status in {"new_signal", "noise", "insufficient_evidence"} else "medium"

    if not is_missing(row.get("anchor_event")):
        evidence_used.append("anchor_event_context_present")

    previous_status = row.get("previous_status")
    if previous_status not in STATE_VALUES:
        previous_status = None
    row["previous_status"] = previous_status
    row["signal_type"] = signal_type
    row["status"] = status
    row["confidence"] = confidence
    row["status_reason"] = reason
    row["evidence_used"] = evidence_used
    row["unknown_fields"] = sorted(field for field in UNKNOWN_FIELDS if is_missing(row.get(field)))
    row["classification_errors"] = sorted(set(errors))
    row["classification_status"] = "invalid" if errors else "valid"
    row["state_changed"] = previous_status is not None and previous_status != status
    return row


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


def emit(rows: list[dict[str, Any]], fmt: str) -> None:
    if fmt == "json":
        print(json.dumps({"candidates": rows}, ensure_ascii=False, indent=2, allow_nan=False))
        return
    if not rows:
        return
    fields = sorted({key for row in rows for key in row})
    writer = csv.DictWriter(__import__("sys").stdout, fieldnames=fields)
    writer.writeheader()
    for row in rows:
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
    parser.add_argument("--as-of", help="Accepted for pipeline symmetry; classification uses supplied evidence timestamps.")
    args = parser.parse_args()
    thresholds = load_thresholds()
    rows = [classify_candidate(candidate, thresholds) for candidate in load_candidates(Path(args.input))]
    emit(rows, args.format)


if __name__ == "__main__":
    main()
