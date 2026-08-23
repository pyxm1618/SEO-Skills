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
    "novelty_baseline_signal",
    "recent_signal",
    "growth_rate",
    "acceleration",
    "persistence",
    "latest_observation_age_days",
    "coverage_ratio",
    "max_observation_gap_days",
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


def recent_depth(series: dict[str, Any]) -> int:
    return max(
        int(finite_number(series.get("recent_7d_observations")) or 0),
        int(finite_number(series.get("recent_30d_observations")) or 0),
        int(finite_number(series.get("recent_observations")) or 0),
    )


def choose_classification_series(candidate: dict[str, Any], thresholds: dict[str, Any]) -> dict[str, Any]:
    """Prefer an independently verified, fresh, non-ended series with enough recent depth."""
    evidence = [item for item in candidate.get("source_evidence") or [] if isinstance(item, dict)]
    minimum = thresholds["evidence"]["min_recent_observations_confirmed"]
    max_age = thresholds["freshness"]["max_latest_observation_age_days_confirmed"]

    eligible: list[dict[str, Any]] = []
    for item in evidence:
        if item.get("provenance_status") != "verified":
            continue
        trend_status = None if is_missing(item.get("trend_status")) else str(item.get("trend_status")).strip().lower()
        latest_age = finite_number(item.get("latest_observation_age_days"))
        if trend_status == "lasted" or latest_age is None or latest_age > max_age or recent_depth(item) < minimum:
            continue
        eligible.append(item)

    if eligible:
        return sorted(
            eligible,
            key=lambda item: (
                -recent_depth(item),
                finite_number(item.get("latest_observation_age_days")) or 0,
                -int(finite_number(item.get("observation_count")) or 0),
                str(item.get("source") or ""),
                str(item.get("country") or ""),
                str(item.get("metric_database") or ""),
            ),
        )[0]

    primary = candidate.get("primary_series")
    if isinstance(primary, dict):
        return primary
    verified = [item for item in evidence if item.get("provenance_status") == "verified"]
    return verified[0] if verified else (evidence[0] if evidence else {})


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


def select_temporal_values(
    primary: dict[str, Any],
    persistence_window: str | None,
    candidate: dict[str, Any],
) -> tuple[float | None, float | None, float | None, str, int]:
    if persistence_window == "recent_30d":
        recent = finite_number(primary.get("recent_30d"))
        baseline = finite_number(primary.get("baseline_30d"))
        growth = finite_number(primary.get("growth_rate_30d"))
        status = primary.get("growth_status_30d") or "unknown"
        baseline_obs = int(finite_number(primary.get("baseline_30d_observations")) or 0)
    elif persistence_window == "recent_7d":
        recent = finite_number(primary.get("recent_7d"))
        baseline = finite_number(primary.get("baseline_7d"))
        growth = finite_number(primary.get("growth_rate_7d"))
        status = primary.get("growth_status_7d") or "unknown"
        baseline_obs = int(finite_number(primary.get("baseline_7d_observations")) or 0)
    else:
        recent = baseline = growth = None
        status = "unknown"
        baseline_obs = 0

    if recent is None:
        recent = finite_number(candidate.get("recent_signal"))
    if baseline is None:
        baseline = finite_number(candidate.get("baseline_signal"))
    if growth is None:
        growth = finite_number(candidate.get("growth_rate"))
    if status == "unknown" and not is_missing(candidate.get("growth_status")):
        status = str(candidate.get("growth_status"))
    if baseline_obs == 0:
        baseline_obs = int(finite_number(primary.get("baseline_observations")) or 0)
    return recent, baseline, growth, status, baseline_obs


def select_novelty_baseline(
    primary: dict[str, Any],
    persistence_window: str | None,
    fallback_baseline: float | None,
    fallback_count: int,
) -> tuple[str | None, float | None, int]:
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
    if suffix is None:
        return None, 0, []
    seen_field = f"historical_positive_seen_{suffix}"
    if seen_field not in primary:
        return None, 0, []
    seen = primary.get(seen_field)
    seen_value = seen if isinstance(seen, bool) else None
    count = int(finite_number(primary.get(f"historical_positive_observations_{suffix}")) or 0)
    windows = primary.get(f"historical_positive_windows_{suffix}")
    return seen_value, count, list(windows) if isinstance(windows, list) else []


def metric_record(row: dict[str, Any], field: str) -> dict[str, Any] | None:
    provenance = row.get("metric_provenance")
    if isinstance(provenance, dict) and isinstance(provenance.get(field), dict):
        return provenance[field]
    alias = f"{field}_metric"
    return row.get(alias) if isinstance(row.get(alias), dict) else None


def exact_metric_context(record: dict[str, Any]) -> tuple[Any, Any, Any]:
    return (
        record.get("metric_source") or record.get("source"),
        record.get("metric_database"),
        record.get("country"),
    )


def metric_set_compatibility(records: dict[str, dict[str, Any] | None]) -> str:
    present = [record for record in records.values() if record is not None]
    if len(present) < 2:
        return "incomplete"
    contexts = [exact_metric_context(record) for record in present]
    if any(any(is_missing(value) for value in context) for context in contexts):
        return "incomplete"
    return "compatible" if len(set(contexts)) == 1 else "incompatible"


def kgr_inputs_compatible(volume_record: dict[str, Any] | None, intitle_record: dict[str, Any] | None) -> bool:
    if not volume_record or not intitle_record:
        return False
    volume_country = volume_record.get("country")
    intitle_country = intitle_record.get("country")
    if is_missing(volume_country) or is_missing(intitle_country) or volume_country != intitle_country:
        return False
    volume_provider = volume_record.get("metric_source") or volume_record.get("source")
    intitle_provider = intitle_record.get("metric_source") or intitle_record.get("source")
    if volume_provider == intitle_provider:
        volume_db = volume_record.get("metric_database")
        intitle_db = intitle_record.get("metric_database")
        if is_missing(volume_db) or is_missing(intitle_db) or volume_db != intitle_db:
            return False
    return True


def derive_metrics(row: dict[str, Any]) -> tuple[str, str, float | None, str | None, str, list[str]]:
    errors: list[str] = []
    values = {field: finite_number(row.get(field)) for field in ("volume", "kd", "cpc", "intitle_results")}
    volume, kd, cpc, intitle = (values["volume"], values["kd"], values["cpc"], values["intitle_results"])

    if not is_missing(row.get("volume")) and (volume is None or volume < 0):
        errors.append("volume")
    if not is_missing(row.get("kd")) and (kd is None or kd < 0 or kd > 100):
        errors.append("kd")
    if not is_missing(row.get("cpc")) and (cpc is None or cpc < 0):
        errors.append("cpc")
    if not is_missing(row.get("intitle_results")) and (intitle is None or intitle < 0 or not intitle.is_integer()):
        errors.append("intitle_results")
    if errors:
        return "invalid", "incomplete", None, None, "unknown", errors

    records = {field: metric_record(row, field) for field in ("volume", "kd", "cpc", "intitle_results")}
    metric_compatibility = metric_set_compatibility(records)
    core_records = {field: records[field] for field in ("volume", "kd", "cpc")}
    if volume is None or kd is None or cpc is None:
        metric_status = "incomplete"
    elif any(core_records[field] is None for field in core_records):
        metric_status = "incomplete"
    elif len({exact_metric_context(record) for record in core_records.values() if record is not None}) == 1:
        metric_status = "complete"
    else:
        metric_status = "incompatible"

    kgr = None
    kgr_compatibility = "unknown"
    if volume is not None and volume > 0 and intitle is not None:
        if kgr_inputs_compatible(records["volume"], records["intitle_results"]):
            kgr = intitle / volume
            kgr_compatibility = "compatible"
        elif records["volume"] is not None and records["intitle_results"] is not None:
            kgr_compatibility = "incompatible"

    if intitle is not None and volume is None:
        supply_signal = "low_supply_signal"
    elif intitle is not None:
        supply_signal = "observed_supply"
    else:
        supply_signal = None
    return metric_status, metric_compatibility, kgr, supply_signal, kgr_compatibility, []


def classify_candidate(candidate: dict[str, Any], thresholds: dict[str, Any]) -> dict[str, Any]:
    row = dict(candidate)
    evidence_used: list[str] = []
    errors: list[str] = []

    keyword = str(row.get("keyword") or "").strip()
    if not keyword:
        errors.append("keyword")

    metric_status, metric_compatibility, kgr, supply_signal, kgr_compatibility, metric_errors = derive_metrics(row)
    errors.extend(metric_errors)
    row["metric_status"] = metric_status
    row["metric_compatibility_status"] = metric_compatibility
    row["kgr"] = kgr
    row["kgr_compatibility_status"] = kgr_compatibility
    row["supply_signal"] = supply_signal

    primary = choose_classification_series(row, thresholds)
    row["primary_series"] = primary
    row["classification_series_source"] = primary.get("source") if primary else None

    fallback_persistence = finite_number(row.get("persistence"))
    fallback_recent_obs = int(finite_number(primary.get("recent_observations")) or row.get("persistence_observations") or 0)
    evidence_cfg = thresholds["evidence"]
    persistence_window, persistence, recent_obs = select_persistence_evidence(
        primary,
        fallback_persistence,
        fallback_recent_obs,
        evidence_cfg["min_recent_observations_confirmed"],
    )
    recent, baseline, growth, growth_status, baseline_obs = select_temporal_values(primary, persistence_window, row)
    row["persistence"] = persistence
    row["persistence_window"] = persistence_window
    row["persistence_observations"] = recent_obs
    row["recent_signal"] = recent
    row["baseline_signal"] = baseline
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

    historical_positive_seen, historical_positive_observations, historical_positive_windows = select_historical_positive(primary, persistence_window)
    row["historical_positive_seen"] = historical_positive_seen
    row["historical_positive_observations"] = historical_positive_observations
    row["historical_positive_windows"] = historical_positive_windows

    latest_age = finite_number(primary.get("latest_observation_age_days"))
    if latest_age is None:
        latest_age = finite_number(row.get("latest_observation_age_days"))
    distinct_days = int(finite_number(primary.get("distinct_observation_days")) or row.get("distinct_observation_days") or 0)
    coverage_ratio = finite_number(primary.get("coverage_ratio"))
    if coverage_ratio is None:
        coverage_ratio = finite_number(row.get("coverage_ratio"))
    max_gap = finite_number(primary.get("max_observation_gap_days"))
    if max_gap is None:
        max_gap = finite_number(row.get("max_observation_gap_days"))
    row["latest_observation_age_days"] = latest_age
    row["distinct_observation_days"] = distinct_days
    row["coverage_ratio"] = coverage_ratio
    row["max_observation_gap_days"] = max_gap

    freshness_limit = thresholds["freshness"]["max_latest_observation_age_days_confirmed"]
    fresh_enough = latest_age is not None and latest_age <= freshness_limit
    age_days = finite_number(row.get("age_days"))
    peak = finite_number(primary.get("peak_signal"))
    latest = finite_number(primary.get("latest_signal"))
    verified_sources = verified_source_count(row)
    source_count = int(finite_number(row.get("source_count")) or 0)
    trend_status = None if is_missing(primary.get("trend_status")) else str(primary.get("trend_status")).strip().lower()
    row["trend_status"] = trend_status

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

    confirmed_temporal = (
        recent is not None
        and recent > 0
        and recent_obs >= evidence_cfg["min_recent_observations_confirmed"]
        and persistence is not None
        and persistence >= evidence_cfg["min_persistence_confirmed"]
        and fresh_enough
    )
    has_verified_series = verified_sources >= 1 and primary.get("provenance_status") == "verified"

    signal_type = None
    status = "insufficient_evidence"
    reason = "Evidence is insufficient for a temporal classification."

    if errors:
        reason = "Candidate contains invalid classification inputs; repair them before temporal classification."
    elif recent is None or not primary:
        reason = "No comparable recent signal series is available."
    elif not has_verified_series:
        reason = "Comparable signal data exists, but no primary series has complete provenance."
    else:
        evidence_used.append(f"verified_sources={verified_sources}")
        evidence_used.append(f"recent_observations={recent_obs}")
        if persistence_window is not None:
            evidence_used.append(f"persistence_window={persistence_window}")
        if persistence is not None:
            evidence_used.append(f"persistence={persistence:.4g}")
        if latest_age is not None:
            evidence_used.append(f"latest_observation_age_days={int(latest_age)}")
        if baseline is not None:
            evidence_used.append(f"baseline_signal={baseline:.4g}")
        if novelty_baseline is not None:
            evidence_used.append(f"novelty_baseline_signal={novelty_baseline:.4g}")
        if novelty_window is not None:
            evidence_used.append(f"novelty_baseline_window={novelty_window}")
        if historical_positive_seen is not None:
            evidence_used.append(f"historical_positive_seen={str(historical_positive_seen).lower()}")
        if recent is not None:
            evidence_used.append(f"recent_signal={recent:.4g}")

        noise_cfg = thresholds["noise"]
        decay_ratio = latest / peak if peak is not None and peak > 0 and latest is not None else None
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
        elif recent <= 0 and (peak is None or peak <= 0):
            status = "insufficient_evidence"
            reason = "No positive relative signal has been observed; a zero source index is not evidence of newly forming demand."
        elif trend_status == "lasted":
            status = "watch"
            reason = "The selected source series reports that the trend ended or returned toward its usual level, with no independent fresh verified series qualifying to replace it."
            evidence_used.append("selected_series_trend_status=lasted")
        elif recent_obs <= 1:
            if fresh_enough:
                status = "new_signal"
                reason = "A real recent signal is observed, but there is only one recent observation so persistence is not established."
            else:
                status = "watch"
                reason = "The signal has too little follow-up evidence and the latest observation is not fresh enough for confirmation."
        elif not fresh_enough:
            status = "watch"
            reason = "Repeated signal exists, but the latest observation is too old or freshness is unknown; confirmed emerging/breakout status requires fresh evidence."
        elif not confirmed_temporal:
            status = "watch"
            reason = "Repeated signal exists, but persistence or recent observation depth is below the confirmation threshold."
        elif variant_subtype is not None:
            signal_type = "emerging_variant"
            status = "emerging"
            reason = f"Persistent recent demand is paired with an explicit {variant_subtype} relationship to an existing search expression."
            evidence_used.append(f"variant_subtype={variant_subtype}")
        elif (
            novelty_baseline is not None
            and novelty_baseline == 0
            and novelty_baseline_obs >= evidence_cfg["min_baseline_observations"]
            and historical_positive_seen is False
        ):
            signal_type = "net_new"
            status = "emerging"
            reason = "Comparable evidence before the current persistence window shows no positive demand in the available 12-month history, while recent observations are persistent."
            evidence_used.append(f"novelty_baseline_observations={novelty_baseline_obs}")
        elif (
            baseline is not None
            and baseline > 0
            and growth is not None
            and growth >= thresholds["breakout"]["growth_rate_min"]
        ):
            signal_type = "breakout"
            status = "breakout"
            reason = "A positive non-overlapping historical baseline exists and recent persistent signal is materially above that baseline."
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
