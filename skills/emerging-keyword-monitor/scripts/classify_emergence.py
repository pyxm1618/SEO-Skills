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
DEMAND_HISTORY_TYPES = {"newly_observed", "preexisting", "resurgent", "unknown"}
STATE_VALUES = {"new_signal", "watch", "emerging", "breakout", "mature", "noise", "insufficient_evidence"}
UNKNOWN_FIELDS = (
    "root_id",
    "first_observed_at",
    "estimated_birth_window",
    "birth_window_start",
    "birth_window_end",
    "birth_source_resolution",
    "birth_confidence",
    "birth_reason",
    "demand_history_type",
    "age_days",
    "baseline_signal",
    "novelty_baseline_signal",
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


def verified_source_count(candidate: dict[str, Any]) -> int:
    names = {
        str(item.get("source") or "").strip()
        for item in candidate.get("source_evidence") or []
        if isinstance(item, dict)
        and item.get("provenance_status") == "verified"
        and str(item.get("source") or "").strip()
    }
    return len(names)


def normalize_context(value: Any) -> str | None:
    if is_missing(value):
        return None
    return str(value).strip().lower()


def metric_record(row: dict[str, Any], field: str) -> dict[str, Any] | None:
    provenance = row.get("metric_provenance")
    if not isinstance(provenance, dict):
        return None
    record = provenance.get(field)
    return record if isinstance(record, dict) else None


def metric_record_matches_value(record: dict[str, Any] | None, value: float | None) -> bool:
    if record is None or value is None:
        return False
    record_value = finite_number(record.get("value"))
    return record_value is not None and record_value == value


def compatible_metric_records(left: dict[str, Any] | None, right: dict[str, Any] | None) -> bool:
    if left is None or right is None:
        return False
    for field in ("country", "metric_database"):
        left_value = normalize_context(left.get(field))
        right_value = normalize_context(right.get(field))
        if left_value is None or right_value is None or left_value != right_value:
            return False
    return True


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

    volume_record = metric_record(row, "volume")
    kd_record = metric_record(row, "kd")
    cpc_record = metric_record(row, "cpc")
    intitle_record = metric_record(row, "intitle_results")

    required_values = {"volume": volume, "kd": kd, "cpc": cpc}
    required_records = {"volume": volume_record, "kd": kd_record, "cpc": cpc_record}
    all_required_values = all(value is not None for value in required_values.values())
    all_required_traced = all(
        metric_record_matches_value(required_records[field], value)
        for field, value in required_values.items()
        if value is not None
    )
    compatibility = str(row.get("metric_compatibility_status") or "unknown")

    if all_required_values and all_required_traced and compatibility == "compatible":
        metric_status = "complete"
    elif all_required_values and compatibility == "mixed_context":
        metric_status = "incompatible"
    else:
        metric_status = "incomplete"

    kgr = None
    if (
        volume is not None
        and volume > 0
        and intitle is not None
        and metric_record_matches_value(volume_record, volume)
        and metric_record_matches_value(intitle_record, intitle)
        and compatible_metric_records(volume_record, intitle_record)
    ):
        kgr = intitle / volume

    if intitle is not None and volume is None:
        supply_signal = "low_supply_signal"
    elif intitle is not None:
        supply_signal = "observed_supply"
    else:
        supply_signal = None
    return metric_status, kgr, supply_signal, []


def trend_status_of(series: dict[str, Any]) -> str | None:
    value = series.get("trend_status")
    return None if is_missing(value) else str(value).strip().lower()


def freshness_of(series: dict[str, Any], max_age_days: int) -> str:
    age = finite_number(series.get("latest_observation_age_days"))
    if age is None:
        return "unknown"
    return "fresh" if age <= max_age_days else "stale"


def choose_classification_series(
    candidate: dict[str, Any],
    max_age_days: int,
) -> dict[str, Any]:
    primary = candidate.get("primary_series") if isinstance(candidate.get("primary_series"), dict) else {}
    if not primary:
        return {}

    primary_is_ended = trend_status_of(primary) == "lasted"
    primary_is_stale = freshness_of(primary, max_age_days) == "stale"
    if not primary_is_ended and not primary_is_stale:
        return primary

    alternatives: list[dict[str, Any]] = []
    for series in candidate.get("source_evidence") or []:
        if not isinstance(series, dict) or series is primary:
            continue
        if series.get("provenance_status") != "verified":
            continue
        if trend_status_of(series) == "lasted":
            continue
        if freshness_of(series, max_age_days) == "stale":
            continue
        recent = finite_number(series.get("recent_7d"))
        if recent is None:
            recent = finite_number(series.get("recent_30d"))
        if recent is None or recent <= 0:
            continue
        alternatives.append(series)

    if not alternatives:
        return primary

    def sort_key(series: dict[str, Any]) -> tuple[float, int, str]:
        age = finite_number(series.get("latest_observation_age_days"))
        age_rank = age if age is not None else 10_000.0
        observations = int(finite_number(series.get("observation_count")) or 0)
        return (age_rank, -observations, str(series.get("source") or ""))

    return sorted(alternatives, key=sort_key)[0]


def select_persistence_evidence(
    primary: dict[str, Any],
    fallback_persistence: float | None,
    fallback_count: int,
    minimum_observations: int,
) -> tuple[str | None, float | None, int]:
    """Prefer the shortest evidence window that has enough observations for confirmation."""
    options: list[tuple[str, float, int]] = []
    for window, persistence_field, count_field in (
        ("recent_7d", "persistence_7d", "recent_7d_observations"),
        ("recent_30d", "persistence_30d", "recent_30d_observations"),
    ):
        persistence = finite_number(primary.get(persistence_field))
        count = int(finite_number(primary.get(count_field)) or 0)
        if persistence is not None and count > 0:
            options.append((window, persistence, count))

    for option in options:
        if option[2] >= minimum_observations:
            return option

    if options:
        return options[0]

    fallback_window = primary.get("persistence_window")
    if is_missing(fallback_window):
        fallback_window = None
    else:
        fallback_window = str(fallback_window)
    return fallback_window, fallback_persistence, fallback_count


def select_temporal_metrics(
    primary: dict[str, Any],
    persistence_window: str | None,
    fallback_baseline: float | None,
    fallback_recent: float | None,
    fallback_growth: float | None,
    fallback_growth_status: str,
) -> tuple[float | None, float | None, float | None, str, int]:
    if persistence_window == "recent_30d":
        baseline = finite_number(primary.get("baseline_90d_30d"))
        recent = finite_number(primary.get("recent_30d"))
        growth = finite_number(primary.get("growth_rate_30d"))
        growth_status = primary.get("growth_status_30d")
        baseline_obs = int(finite_number(primary.get("baseline_30d_observations")) or 0)
    elif persistence_window == "recent_7d":
        baseline = finite_number(primary.get("baseline_90d_7d"))
        recent = finite_number(primary.get("recent_7d"))
        growth = finite_number(primary.get("growth_rate_7d"))
        growth_status = primary.get("growth_status_7d")
        baseline_obs = int(finite_number(primary.get("baseline_7d_observations")) or 0)
    else:
        return (
            fallback_baseline,
            fallback_recent,
            fallback_growth,
            fallback_growth_status,
            int(finite_number(primary.get("baseline_observations")) or 0),
        )

    if baseline is None and "baseline_90d_30d" not in primary and "baseline_90d_7d" not in primary:
        baseline = fallback_baseline
    if recent is None and "recent_30d" not in primary and "recent_7d" not in primary:
        recent = fallback_recent
    if growth is None and not str(growth_status or "").strip():
        growth = fallback_growth
        growth_status = fallback_growth_status
    if baseline_obs == 0 and "baseline_30d_observations" not in primary and "baseline_7d_observations" not in primary:
        baseline_obs = int(finite_number(primary.get("baseline_observations")) or 0)

    return baseline, recent, growth, str(growth_status or "unknown"), baseline_obs


def select_novelty_baseline(
    primary: dict[str, Any],
    persistence_window: str | None,
    fallback_baseline: float | None,
    fallback_count: int,
) -> tuple[str | None, float | None, int]:
    """Use history strictly before the selected recent persistence evidence window."""
    if persistence_window == "recent_30d":
        return (
            "days_30_89",
            finite_number(primary.get("novelty_baseline_30d")),
            int(finite_number(primary.get("novelty_baseline_30d_observations")) or 0),
        )
    if persistence_window == "recent_7d":
        return (
            "days_7_89",
            finite_number(primary.get("novelty_baseline_7d")),
            int(finite_number(primary.get("novelty_baseline_7d_observations")) or 0),
        )
    return None, fallback_baseline, fallback_count


def select_historical_positive(primary: dict[str, Any], persistence_window: str | None) -> tuple[bool | None, int, list[str]]:
    suffix = "30d" if persistence_window == "recent_30d" else "7d" if persistence_window == "recent_7d" else None
    if suffix:
        seen_key = f"historical_positive_{suffix}_seen"
        count_key = f"historical_positive_{suffix}_observations"
        windows_key = f"historical_positive_{suffix}_windows"
        if seen_key in primary:
            seen = primary.get(seen_key)
            return (
                bool(seen) if isinstance(seen, bool) else None,
                int(finite_number(primary.get(count_key)) or 0),
                list(primary.get(windows_key) or []),
            )

    if "historical_positive_seen" not in primary:
        return None, 0, []
    seen = primary.get("historical_positive_seen")
    return (
        bool(seen) if isinstance(seen, bool) else None,
        int(finite_number(primary.get("historical_positive_observations")) or 0),
        list(primary.get("historical_positive_windows") or []),
    )


def classify_candidate(candidate: dict[str, Any], thresholds: dict[str, Any]) -> dict[str, Any]:
    row = dict(candidate)
    evidence_used: list[str] = []
    errors: list[str] = []

    demand_history_type = row.get("demand_history_type")
    if is_missing(demand_history_type):
        demand_history_type = "unknown"
    else:
        demand_history_type = str(demand_history_type).strip().lower()
        if demand_history_type not in DEMAND_HISTORY_TYPES:
            errors.append("demand_history_type")
    row["demand_history_type"] = demand_history_type

    keyword = str(row.get("keyword") or "").strip()
    if not keyword:
        errors.append("keyword")

    metric_status, kgr, supply_signal, metric_errors = derive_metrics(row)
    errors.extend(metric_errors)
    row["metric_status"] = metric_status
    row["kgr"] = kgr
    row["supply_signal"] = supply_signal

    temporal_cfg = thresholds.get("temporal") or {}
    max_age_days = int(temporal_cfg.get("max_latest_observation_age_days_confirmed", 7))
    primary = choose_classification_series(row, max_age_days)
    row["classification_primary_series"] = primary or None

    fallback_baseline = finite_number(row.get("baseline_signal"))
    fallback_recent = finite_number(row.get("recent_signal"))
    fallback_growth = finite_number(row.get("growth_rate"))
    fallback_growth_status = str(row.get("growth_status") or "unknown")
    fallback_persistence = finite_number(row.get("persistence"))
    age_days = finite_number(row.get("age_days"))
    fallback_recent_obs = int(finite_number(primary.get("recent_observations")) or row.get("persistence_observations") or 0)
    peak = finite_number(primary.get("peak_signal"))
    latest = finite_number(primary.get("latest_signal"))
    verified_sources = verified_source_count(row)
    source_count = int(finite_number(row.get("source_count")) or 0)
    selected_trend_status = trend_status_of(primary)

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
    persistence_window, persistence, recent_obs = select_persistence_evidence(
        primary,
        fallback_persistence,
        fallback_recent_obs,
        evidence_cfg["min_recent_observations_confirmed"],
    )
    row["persistence"] = persistence
    row["persistence_window"] = persistence_window
    row["persistence_observations"] = recent_obs

    baseline, recent, growth, growth_status, baseline_obs = select_temporal_metrics(
        primary,
        persistence_window,
        fallback_baseline,
        fallback_recent,
        fallback_growth,
        fallback_growth_status,
    )
    row["baseline_signal"] = baseline
    row["recent_signal"] = recent
    row["growth_rate"] = growth
    row["growth_status"] = growth_status

    novelty_window, novelty_baseline, novelty_baseline_obs = select_novelty_baseline(
        primary,
        persistence_window,
        baseline,
        baseline_obs,
    )
    row["novelty_baseline_signal"] = novelty_baseline
    row["novelty_baseline_observations"] = novelty_baseline_obs
    row["novelty_baseline_window"] = novelty_window

    historical_positive_seen, historical_positive_observations, historical_positive_windows = select_historical_positive(
        primary,
        persistence_window,
    )
    row["historical_positive_seen"] = historical_positive_seen
    row["historical_positive_observations"] = historical_positive_observations
    row["historical_positive_windows"] = historical_positive_windows

    freshness_status = freshness_of(primary, max_age_days) if primary else "unknown"
    row["freshness_status"] = freshness_status
    row["freshness_threshold_days"] = max_age_days
    row["latest_observation_age_days"] = primary.get("latest_observation_age_days") if primary else None
    row["trend_status"] = selected_trend_status

    confirmed_temporal = (
        recent is not None
        and recent > 0
        and recent_obs >= evidence_cfg["min_recent_observations_confirmed"]
        and persistence is not None
        and persistence >= evidence_cfg["min_persistence_confirmed"]
        and freshness_status != "stale"
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
        reason = "Comparable signal data exists, but no classification series has complete provenance."
    else:
        evidence_used.append(f"verified_sources={verified_sources}")
        evidence_used.append(f"recent_observations={recent_obs}")
        if persistence_window is not None:
            evidence_used.append(f"persistence_window={persistence_window}")
        if persistence is not None:
            evidence_used.append(f"persistence={persistence:.4g}")
        if baseline is not None:
            evidence_used.append(f"baseline_signal={baseline:.4g}")
        if novelty_baseline is not None:
            evidence_used.append(f"novelty_baseline_signal={novelty_baseline:.4g}")
        if novelty_window is not None:
            evidence_used.append(f"novelty_baseline_window={novelty_window}")
        if recent is not None:
            evidence_used.append(f"recent_signal={recent:.4g}")
        if historical_positive_seen is not None:
            evidence_used.append(f"historical_positive_seen={str(historical_positive_seen).lower()}")
        evidence_used.append(f"demand_history_type={demand_history_type}")
        if freshness_status != "unknown":
            evidence_used.append(f"freshness_status={freshness_status}")
        if row.get("latest_observation_age_days") is not None:
            evidence_used.append(f"latest_observation_age_days={row['latest_observation_age_days']}")

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
            and durable is False
            and repeatable_fit is False
        )

        if is_noise:
            status = "noise"
            reason = "Observed spike decayed sharply across follow-up observations and lacks confirmed durable/repeatable search-task evidence."
            evidence_used.append(f"latest_to_peak_ratio={decay_ratio:.4g}")
        elif selected_trend_status == "lasted":
            status = "watch"
            reason = "The selected source series reports that the trend ended or returned toward its usual level, and no independent fresh verified series superseded it."
            evidence_used.append("trend_status=lasted")
        elif freshness_status == "stale":
            status = "watch"
            reason = "The latest observation is older than the v1 freshness threshold, so prior persistence is retained as watch evidence rather than confirmed as currently emerging."
        elif recent <= 0 and (peak is None or peak <= 0):
            status = "insufficient_evidence"
            reason = "No positive relative signal has been observed; a zero source index is not evidence of newly forming demand."
        elif recent_obs <= 1:
            status = "new_signal"
            reason = "A real recent signal is observed, but there is only one recent observation so persistence is not established."
        elif not confirmed_temporal:
            status = "watch"
            reason = "Repeated signal exists, but persistence, freshness, or recent observation depth is below the confirmation threshold."
        elif variant_subtype is not None:
            signal_type = "emerging_variant"
            status = "emerging"
            reason = f"Persistent recent demand is paired with an explicit {variant_subtype} relationship to an existing search expression."
            evidence_used.append(f"variant_subtype={variant_subtype}")
        elif (
            demand_history_type not in {"preexisting", "resurgent"}
            and
            historical_positive_seen is not True
            and novelty_baseline is not None
            and novelty_baseline == 0
            and novelty_baseline_obs >= evidence_cfg["min_baseline_observations"]
        ):
            signal_type = "net_new"
            status = "emerging"
            reason = "Comparable history before the current persistence window contains no reliable positive-demand evidence, while recent observations are persistent; this is newly observed demand within the available evidence window."
            evidence_used.append(f"novelty_baseline_observations={novelty_baseline_obs}")
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
