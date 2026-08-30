#!/usr/bin/env python3
"""Infer demand history from one actual comparable long-history series.

Google Trends indexes are normalized per query timeframe.  This module therefore
accepts one series at a time and deliberately has no code for joining or
comparing values from different timeframes.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_BIRTH_THRESHOLDS: dict[str, Any] = {
    "min_history_observations": 6,
    "min_baseline_observations": 3,
    "min_formation_observations": 3,
    "min_follow_up_observations": 2,
    "min_follow_up_persistence": 0.66,
    "baseline_max_signal": 5,
    "min_signal": 5,
    "min_lift_ratio": 1.5,
    "quiet_max_signal": 5,
    "min_historical_positive_observations": 3,
    "min_quiet_observations": 3,
}


def load_thresholds(path: Path | None = None) -> dict[str, Any]:
    """Load the skill thresholds without making them part of the input series."""
    thresholds_path = path or Path(__file__).resolve().parents[1] / "references" / "thresholds.json"
    return json.loads(thresholds_path.read_text(encoding="utf-8"))


def _birth_thresholds(thresholds: dict[str, Any] | None) -> dict[str, Any]:
    source = thresholds or {}
    if isinstance(source.get("birth"), dict):
        source = source["birth"]
    return {**DEFAULT_BIRTH_THRESHOLDS, **source}


def _positive_int(config: dict[str, Any], name: str) -> int:
    try:
        value = int(config[name])
    except (KeyError, TypeError, ValueError):
        return int(DEFAULT_BIRTH_THRESHOLDS[name])
    return max(1, value)


def _non_negative_float(config: dict[str, Any], name: str) -> float:
    try:
        value = float(config[name])
    except (KeyError, TypeError, ValueError):
        return float(DEFAULT_BIRTH_THRESHOLDS[name])
    return value if math.isfinite(value) and value >= 0 else float(DEFAULT_BIRTH_THRESHOLDS[name])


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, datetime.min.time())
    else:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            if len(text) == 10:
                parsed = datetime.combine(date.fromisoformat(text), datetime.min.time())
            else:
                normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
                parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalise_points(points: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    normalized: list[dict[str, Any]] = []
    invalid_count = 0
    for raw in points:
        if not isinstance(raw, dict):
            invalid_count += 1
            continue
        raw_time = raw.get("time", raw.get("observed_at"))
        parsed_time = _parse_time(raw_time)
        raw_value = raw.get("value", raw.get("signal_value"))
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            value = None
        if parsed_time is None or value is None or not math.isfinite(value) or value < 0:
            invalid_count += 1
            continue
        normalized.append(
            {
                "time": parsed_time,
                "raw_time": raw_time,
                "value": value,
            }
        )
    normalized.sort(key=lambda point: point["time"])
    return normalized, invalid_count


def _resolution_label(source_resolution: Any) -> str:
    return str(source_resolution or "unknown").strip().lower()


def _bucket_label(value: datetime, source_resolution: Any) -> str:
    resolution = _resolution_label(source_resolution)
    if resolution in {"daily", "day", "1d", "24h"} or "daily" in resolution or "day" in resolution:
        return value.date().isoformat()
    # Weekly and monthly Trends buckets do not justify a fabricated day-level
    # birth date. Month labels are conservative even when the raw bucket starts
    # on a particular weekday.
    return value.strftime("%Y-%m")


def _window(points: list[dict[str, Any]], start: int, end: int, source_resolution: Any) -> str | None:
    if start < 0 or end < start or end >= len(points):
        return None
    first = _bucket_label(points[start]["time"], source_resolution)
    last = _bucket_label(points[end]["time"], source_resolution)
    return first if first == last else f"{first} ~ {last}"


def _run_end(points: list[dict[str, Any]], start: int, predicate) -> int:
    end = start
    while end + 1 < len(points) and predicate(points[end + 1]["value"]):
        end += 1
    return end


def _runs(points: list[dict[str, Any]], predicate) -> list[tuple[int, int]]:
    found: list[tuple[int, int]] = []
    index = 0
    while index < len(points):
        if not predicate(points[index]["value"]):
            index += 1
            continue
        end = _run_end(points, index, predicate)
        found.append((index, end))
        index = end + 1
    return found


def _evidence(points: list[dict[str, Any]], ranges: list[tuple[int, int, str]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for start, end, role in ranges:
        for index in range(start, end + 1):
            point = points[index]
            output.append(
                {
                    "observed_at": point["time"].date().isoformat(),
                    "value": point["value"],
                    "role": role,
                }
            )
    return output


def _base_result(source_resolution: Any, reason: str) -> dict[str, Any]:
    return {
        "demand_history_type": "unknown",
        "estimated_birth_window": None,
        "birth_window_start": None,
        "birth_window_end": None,
        "birth_source_resolution": source_resolution or "unknown",
        "birth_confidence": "low",
        "birth_reason": reason,
        "birth_evidence_series": [],
        "historical_positive_seen": None,
        "historical_positive_observations": None,
        "historical_positive_windows": [],
        "resurgence_window": None,
        "resurgence_window_start": None,
        "resurgence_window_end": None,
        "history_observation_count": 0,
    }


def _set_window_fields(
    result: dict[str, Any],
    points: list[dict[str, Any]],
    start: int,
    end: int,
    source_resolution: Any,
    prefix: str,
) -> None:
    start_label = _bucket_label(points[start]["time"], source_resolution)
    end_label = _bucket_label(points[end]["time"], source_resolution)
    result[f"{prefix}_start"] = start_label
    result[f"{prefix}_end"] = end_label
    if prefix == "birth_window":
        result["estimated_birth_window"] = _window(points, start, end, source_resolution)
    elif prefix == "resurgence_window":
        result["resurgence_window"] = _window(points, start, end, source_resolution)


def _find_resurgence(
    points: list[dict[str, Any]],
    config: dict[str, Any],
) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int]] | None:
    quiet_max = _non_negative_float(config, "quiet_max_signal")
    min_old = _positive_int(config, "min_historical_positive_observations")
    min_quiet = _positive_int(config, "min_quiet_observations")
    min_recent = _positive_int(config, "min_formation_observations")
    positive_runs = _runs(points, lambda value: value > quiet_max)
    for old_start, old_end in positive_runs:
        if old_end - old_start + 1 < min_old:
            continue
        quiet_start = old_end + 1
        if quiet_start >= len(points) or points[quiet_start]["value"] > quiet_max:
            continue
        quiet_end = _run_end(points, quiet_start, lambda value: value <= quiet_max)
        if quiet_end - quiet_start + 1 < min_quiet:
            continue
        recent_start = quiet_end + 1
        if recent_start >= len(points):
            continue
        recent_end = _run_end(points, recent_start, lambda value: value > quiet_max)
        if recent_end - recent_start + 1 < min_recent:
            continue
        return (old_start, old_end), (quiet_start, quiet_end), (recent_start, recent_end)
    return None


def _find_low_baseline_formation(
    points: list[dict[str, Any]],
    config: dict[str, Any],
) -> tuple[int, int, int, int] | None:
    min_baseline = _positive_int(config, "min_baseline_observations")
    min_formation = _positive_int(config, "min_formation_observations")
    min_follow_up = _positive_int(config, "min_follow_up_observations")
    min_follow_persistence = _non_negative_float(config, "min_follow_up_persistence")
    baseline_max = _non_negative_float(config, "baseline_max_signal")
    min_signal = _non_negative_float(config, "min_signal")
    lift_ratio = _non_negative_float(config, "min_lift_ratio")

    for start in range(min_baseline, len(points) - min_formation + 1):
        baseline_start = start - min_baseline
        baseline = points[baseline_start:start]
        if not all(point["value"] <= baseline_max for point in baseline):
            continue
        baseline_mean = sum(point["value"] for point in baseline) / len(baseline)
        threshold = max(min_signal, baseline_mean * lift_ratio)
        if points[start]["value"] <= threshold:
            continue
        end = _run_end(points, start, lambda value: value > threshold)
        formation_count = end - start + 1
        if formation_count < min_formation + min_follow_up:
            continue
        follow_up = points[start + min_formation : start + min_formation + min_follow_up]
        follow_up_positive = sum(point["value"] > threshold for point in follow_up)
        if follow_up_positive / len(follow_up) < min_follow_persistence:
            continue
        return baseline_start, start, end, end
    return None


def infer_demand_history(
    points: list[dict[str, Any]],
    thresholds: dict[str, Any] | None = None,
    source_resolution: str | None = None,
) -> dict[str, Any]:
    """Classify one actual long-history series without cross-timeframe arithmetic."""

    config = _birth_thresholds(thresholds)
    result = _base_result(source_resolution, "insufficient_history")
    normalized, invalid_count = _normalise_points(points)
    result["history_observation_count"] = len(normalized)
    if invalid_count:
        result["birth_reason"] = "invalid_observations"
        return result

    minimum_history = _positive_int(config, "min_history_observations")
    if len(normalized) < minimum_history:
        return result

    quiet_max = _non_negative_float(config, "quiet_max_signal")
    established_runs = _runs(normalized, lambda value: value > quiet_max)
    positive_before_count = sum(point["value"] > 0 for point in normalized)
    result["historical_positive_observations"] = positive_before_count
    result["historical_positive_windows"] = [
        _window(normalized, start, end, source_resolution) for start, end in established_runs
    ]

    resurgence = _find_resurgence(normalized, config)
    if resurgence is not None:
        old_run, _quiet_run, recent_run = resurgence
        result["demand_history_type"] = "resurgent"
        result["historical_positive_seen"] = True
        result["birth_reason"] = "before_available_history" if old_run[0] == 0 else "quiet_gap_followed_by_persistent_rise"
        result["birth_confidence"] = "low"
        _set_window_fields(result, normalized, recent_run[0], recent_run[1], source_resolution, "resurgence_window")
        result["birth_evidence_series"] = _evidence(
            normalized,
            [
                (old_run[0], old_run[1], "historical_positive"),
                (_quiet_run[0], _quiet_run[1], "observed_quiet"),
                (recent_run[0], recent_run[1], "resurgence"),
            ],
        )
        if old_run[0] > 0:
            result["historical_positive_seen"] = True
        return result

    initial_run = established_runs[0] if established_runs and established_runs[0][0] == 0 else None
    min_old = _positive_int(config, "min_historical_positive_observations")
    if initial_run is not None and initial_run[1] - initial_run[0] + 1 >= min_old:
        result["demand_history_type"] = "preexisting"
        result["historical_positive_seen"] = True
        result["birth_reason"] = "before_available_history"
        result["birth_evidence_series"] = _evidence(
            normalized, [(initial_run[0], initial_run[1], "historical_positive")]
        )
        return result

    formation = _find_low_baseline_formation(normalized, config)
    if formation is None:
        result["historical_positive_seen"] = bool(established_runs)
        result["birth_reason"] = "isolated_spike" if any(
            point["value"] > _non_negative_float(config, "min_signal") for point in normalized
        ) else "no_sustained_formation"
        result["historical_positive_observations"] = positive_before_count
        return result

    baseline_start, formation_start, formation_end, _ = formation
    earlier_established = [
        run for run in established_runs if run[1] < formation_start and run[1] - run[0] + 1 >= min_old
    ]
    result["historical_positive_seen"] = bool(earlier_established)
    if earlier_established:
        result["demand_history_type"] = "unknown"
        result["birth_reason"] = "historical_positive_without_confirmed_resurgence"
        result["birth_evidence_series"] = _evidence(
            normalized,
            [(start, end, "historical_positive") for start, end in earlier_established]
            + [(baseline_start, formation_start - 1, "low_baseline"), (formation_start, formation_end, "formation")],
        )
        return result

    result["demand_history_type"] = "newly_observed"
    result["birth_reason"] = "persistent_rise_after_low_baseline"
    result["birth_confidence"] = "medium"
    _set_window_fields(result, normalized, formation_start, formation_end, source_resolution, "birth_window")
    result["birth_evidence_series"] = _evidence(
        normalized,
        [
            (baseline_start, formation_start - 1, "low_baseline"),
            (formation_start, formation_end, "formation_and_follow_up"),
        ],
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="JSON array or object containing points")
    parser.add_argument("--resolution", default="unknown")
    parser.add_argument("--thresholds", type=Path)
    args = parser.parse_args()
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    points = payload if isinstance(payload, list) else payload.get("points", payload.get("observations", []))
    thresholds = load_thresholds(args.thresholds) if args.thresholds else load_thresholds()
    print(json.dumps(infer_demand_history(points, thresholds, args.resolution), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
