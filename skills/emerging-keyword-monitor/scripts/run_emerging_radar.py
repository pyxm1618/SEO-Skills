#!/usr/bin/env python3
"""Thin domain-level Emerging Keyword Radar orchestration.

The pure ``run_pipeline`` entry point is dependency-injected for deterministic
tests.  The CLI adapters invoke the existing collector CLIs as subprocesses so
collector-bound evidence receipts remain direct-CLI-bound.
"""

from __future__ import annotations

import argparse
import csv
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

from aggregate_signals import aggregate
from classify_emergence import classify_candidate, load_thresholds
from radar_discovery import build_anchor_pool, canonical_keyword, default_domain_relation, discover_rising_bfs
from route_candidates import route_candidate
from update_emerging_database import load_database, merge_database, write_database


TIMEFRAME_DEFAULTS = (
    ("5y", "today 5-y"),
    ("12m", "today 12-m"),
    ("90d", "today 3-m"),
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _call(fetcher: Callable[..., Any], args: tuple[Any, ...], throttle: Any = None) -> Any:
    if throttle is not None:
        throttle.wait()
    return fetcher(*args)


def _relation(relation_gate: Callable[[str, str, str], Any] | None, domain: str, keyword: str, parent: str) -> tuple[str, str]:
    decision = relation_gate(domain, keyword, parent) if relation_gate else default_domain_relation(domain, keyword, parent)
    if isinstance(decision, dict):
        return str(decision.get("domain_relation") or decision.get("relation") or "unknown"), str(
            decision.get("reason") or "domain relation analysis returned no reason"
        )
    if isinstance(decision, (tuple, list)) and len(decision) >= 2:
        return str(decision[0] or "unknown"), str(decision[1] or "domain relation analysis returned no reason")
    return str(decision or "unknown"), "domain relation analysis returned no reason"


def _supplemental_candidates(
    domain: str,
    anchor: dict[str, Any],
    source: str,
    payload: Any,
    relation_gate: Callable[[str, str, str], Any] | None,
) -> list[dict[str, Any]]:
    if source == "google_autocomplete":
        values = payload.get("suggestions") if isinstance(payload, dict) else None
        field = "query"
    else:
        values = payload.get("rows") if isinstance(payload, dict) else None
        field = "keyword"
    if not isinstance(values, list):
        raise ValueError(f"{source} supplemental payload must contain a list")

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


def _timeline_observations(
    candidates: list[dict[str, Any]],
    timeline_fetcher: Callable[[str, str], Any],
    timeframe_specs: tuple[tuple[str, str], ...],
    throttle: Any,
    blockers: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    for candidate in candidates:
        keyword = candidate["keyword"]
        for time_window, requested_timeframe in timeframe_specs:
            try:
                payload = _call(timeline_fetcher, (keyword, requested_timeframe), throttle)
                series, context = _timeline_points(payload)
                observed_at = context.get("google_trends_observed_at") or context.get("observed_at") or _now()
                source_url = context.get("source_url")
                evidence_ref = context.get("google_trends_evidence_ref") or context.get("raw_evidence_ref")
                screenshot_ref = context.get("google_trends_screenshot_ref") or context.get("screenshot_ref")
                actual_resolution = context.get("actual_resolution") or "unknown"
                for point in series:
                    observations.append(
                        {
                            "keyword": keyword,
                            "domain": candidate.get("domain"),
                            "observed_at": _point_time(point["time"]),
                            "source": "google_trends",
                            "source_type": "interest_over_time",
                            "source_url": source_url,
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
                        }
                    )
            except Exception as exc:
                blockers.append(
                    {
                        "status": "BLOCKED",
                        "stage": "trends_timeline",
                        "keyword": keyword,
                        "time_window": time_window,
                        "reason": str(exc),
                    }
                )
    return observations


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
    timeline_fetcher: Callable[[str, str], Any] | None = None,
    timeframe_specs: tuple[tuple[str, str], ...] = TIMEFRAME_DEFAULTS,
    throttle: Any = None,
    as_of: datetime | None = None,
    discovered_at: str | None = None,
    existing_database: dict[str, Any] | None = None,
    database_path: Path | None = None,
    csv_path: Path | None = None,
) -> dict[str, Any]:
    """Run discovery and optional timeline/classification/persistence stages."""
    if not callable(related_fetcher):
        raise ValueError("related_fetcher is required")
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
    for fetcher, source in (
        (autocomplete_fetcher, "google_autocomplete"),
        (semrush_fetcher, "semrush_ideas"),
    ):
        if fetcher is None:
            continue
        for anchor in anchors:
            try:
                payload = _call(fetcher, (anchor["keyword"],), throttle)
                supplemental_evidence.append(
                    {
                        "source": source,
                        "anchor": anchor["keyword"],
                        "payload": payload,
                        "recursive": False,
                    }
                )
                supplemental_candidates.extend(
                    _supplemental_candidates(domain, anchor, source, payload, relation_gate)
                )
            except Exception as exc:
                blockers.append(
                    {
                        "status": "BLOCKED",
                        "stage": source,
                        "anchor": anchor["keyword"],
                        "reason": str(exc),
                    }
                )

    discovered_candidates = list(discovery.get("candidates") or [])
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in discovered_candidates + supplemental_candidates:
        identity = canonical_keyword(candidate.get("keyword"))
        if not identity or identity in seen:
            continue
        if len(candidates) >= max_candidates:
            break
        seen.add(identity)
        candidates.append({"domain": domain, **candidate})

    observations: list[dict[str, Any]] = []
    if timeline_fetcher is not None:
        observations = _timeline_observations(
            candidates,
            timeline_fetcher,
            timeframe_specs,
            throttle,
            blockers,
        )

    aggregate_result = aggregate(observations, as_of or datetime.now(timezone.utc)) if observations else {"candidates": []}
    aggregate_by_keyword = {
        canonical_keyword(candidate.get("keyword")): candidate
        for candidate in aggregate_result.get("candidates", [])
    }
    classified: list[dict[str, Any]] = []
    for discovery_candidate in candidates:
        keyword = canonical_keyword(discovery_candidate.get("keyword"))
        current = dict(aggregate_by_keyword.get(keyword) or {
            "keyword": discovery_candidate.get("keyword"),
            "source_count": 0,
            "source_evidence": [],
            "primary_series": None,
        })
        for field, value in discovery_candidate.items():
            if field not in current or current.get(field) is None:
                current[field] = value
        current["domain"] = domain
        classified.append(classify_candidate(current, load_thresholds()))

    routes: list[dict[str, Any]] = []
    for candidate in classified:
        route = route_candidate(candidate)
        route["domain"] = domain
        routes.append(route)

    database = None
    if database_path is not None or csv_path is not None or existing_database is not None:
        database = merge_database(
            existing_database if existing_database is not None else load_database(Path(database_path)) if database_path else {"schema_version": 1, "records": []},
            classified,
            routes,
            discovered_at or _now(),
        )
        if database_path is not None and csv_path is not None:
            write_database(database, Path(database_path), Path(csv_path))

    status = "BLOCKED" if blockers or discovery.get("status") == "BLOCKED" else "PASS"
    result = {
        "domain": domain,
        "country": country,
        "status": status,
        "recursive_edge_policy": "google_trends_rising_only",
        "supplemental_recursive": False,
        "anchor_pool": anchors,
        "discovery": discovery,
        "supplemental_evidence": supplemental_evidence,
        "candidates": classified,
        "routes": routes,
        "observations": observations,
        "aggregate": aggregate_result,
        "database": database,
        "blockers": blockers,
        "candidate_counts": {
            "discovered": len(discovered_candidates),
            "supplemental": len(supplemental_candidates),
            "unique_pool": len(candidates),
            "classified": len(classified),
        },
    }
    return result


def load_root_rows(path: Path) -> list[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower() or "item"


def _collector_payload(command: list[str], output_path: Path) -> dict[str, Any]:
    process = subprocess.run(command, text=True, capture_output=True)
    if process.returncode != 0:
        detail = (process.stderr or process.stdout or "collector failed").strip()
        raise RuntimeError(detail[-2000:])
    try:
        payload = json.loads(output_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"collector output is unavailable or invalid: {output_path}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("collector output must be a JSON object")
    return payload


def _validated_collector_fetcher(
    *,
    collector: Path,
    validator: Path,
    stage: str,
    mode: str,
    run_dir: Path,
    evidence_dir: Path,
    country: str,
    language: str,
    timeframe: str | None,
    stage_results: list[dict[str, Any]],
    counter: list[int],
) -> Callable[..., dict[str, Any]]:
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

        validation = subprocess.run(
            [
                sys.executable,
                str(validator),
                "--stage",
                stage,
                "--input",
                str(output),
                "--report",
                str(report),
                "--production",
            ],
            text=True,
            capture_output=True,
        )
        try:
            validation_payload = json.loads(report.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"stage validation report is unavailable: {report}") from exc
        stage_results.append(validation_payload)
        if validation.returncode != 0 or validation_payload.get("status") != "PASS":
            detail = (validation.stderr or validation.stdout or "stage contract blocked").strip()
            raise RuntimeError(f"stage {stage} BLOCKED: {detail[-2000:]}")
        return payload

    return fetch


def _live_runner(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = Path(args.run_dir)
    evidence_dir = run_dir / "evidence"
    run_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    stage_results: list[dict[str, Any]] = []
    counter = [0]
    collector = REPO_ROOT / "runtime" / "collectors" / "google_live_collector.py"
    validator = REPO_ROOT / "runtime" / "stage_validator.py"

    related_fetcher = _validated_collector_fetcher(
        collector=collector,
        validator=validator,
        stage="trends_related",
        mode="trends_related",
        run_dir=run_dir,
        evidence_dir=evidence_dir,
        country=args.country,
        language=args.language,
        timeframe=args.related_timeframe,
        stage_results=stage_results,
        counter=counter,
    )
    autocomplete_fetcher = None
    if args.with_autocomplete:
        autocomplete_fetcher = _validated_collector_fetcher(
            collector=collector,
            validator=validator,
            stage="discovery_autocomplete",
            mode="autocomplete",
            run_dir=run_dir,
            evidence_dir=evidence_dir,
            country=args.country,
            language=args.language,
            timeframe=None,
            stage_results=stage_results,
            counter=counter,
        )

    def timeline_fetcher(keyword: str, requested_timeframe: str) -> dict[str, Any]:
        return _validated_collector_fetcher(
            collector=collector,
            validator=validator,
            stage="trends_timeline",
            mode="trends_timeline",
            run_dir=run_dir,
            evidence_dir=evidence_dir,
            country=args.country,
            language=args.language,
            timeframe=requested_timeframe,
            stage_results=stage_results,
            counter=counter,
        )(keyword)

    root_rows = load_root_rows(Path(args.root_library)) if args.root_library else []
    result = run_pipeline(
        related_fetcher,
        autocomplete_fetcher,
        None,
        domain=args.domain,
        explicit_anchors=args.anchor,
        root_rows=root_rows,
        country=args.country,
        max_depth=args.max_depth,
        per_anchor_limit=args.per_anchor_limit,
        max_candidates=args.max_candidates,
        timeline_fetcher=timeline_fetcher,
        timeframe_specs=(
            ("5y", args.long_timeframe),
            ("12m", args.medium_timeframe),
            ("90d", args.recent_timeframe),
        ),
        as_of=datetime.now(timezone.utc),
        discovered_at=_now(),
        database_path=run_dir / "emerging-keywords.json",
        csv_path=run_dir / "emerging-keywords.csv",
    )
    result["stage_validations"] = stage_results
    result["output_artifacts"] = {
        "run_summary": str(Path(args.output)),
        "database": str(run_dir / "emerging-keywords.json"),
        "csv": str(run_dir / "emerging-keywords.csv"),
        "evidence_dir": str(evidence_dir),
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", required=True)
    parser.add_argument("--anchor", action="append", default=[])
    parser.add_argument("--country", default="US")
    parser.add_argument("--language", default="en")
    parser.add_argument("--related-timeframe", default="today 12-m")
    parser.add_argument("--long-timeframe", default="today 5-y")
    parser.add_argument("--medium-timeframe", default="today 12-m")
    parser.add_argument("--recent-timeframe", default="today 3-m")
    parser.add_argument("--max-depth", type=int, default=2)
    parser.add_argument("--per-anchor-limit", type=int, default=10)
    parser.add_argument("--max-candidates", type=int, default=200)
    parser.add_argument("--root-library")
    parser.add_argument("--with-autocomplete", action="store_true")
    parser.add_argument("--run-dir", default=".seo-run/emerging-radar-live")
    parser.add_argument("--output", default=".seo-run/emerging-radar-live/run-summary.json")
    args = parser.parse_args()
    try:
        result = _live_runner(args)
    except Exception as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"status": result["status"], "output": result["output_artifacts"]}, ensure_ascii=False))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
