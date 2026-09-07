#!/usr/bin/env python3
"""Compatibility wrapper that adds cross-run carry-forward to the Emerging Radar."""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

SCRIPT_DIR = Path(__file__).resolve().parent
LEGACY_PATH = SCRIPT_DIR / "run_emerging_radar_legacy.py"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


def _load_legacy():
    spec = importlib.util.spec_from_file_location("seo_emerging_radar_legacy", LEGACY_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load Emerging Radar legacy module: {LEGACY_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_legacy = _load_legacy()

# Preserve the existing module API; only run_pipeline is replaced below.
for _name in dir(_legacy):
    if not _name.startswith("__") and _name not in globals():
        globals()[_name] = getattr(_legacy, _name)

from update_emerging_database import carry_forward


def _database_snapshot(
    existing_database: dict[str, Any] | None,
    database_path: Path | None,
) -> dict[str, Any]:
    if existing_database is not None:
        return existing_database
    if database_path is not None:
        return _legacy.load_database(Path(database_path))
    return {"schema_version": 1, "records": []}


def _candidate_pool(
    domain: str,
    current_candidates: list[dict[str, Any]],
    database: dict[str, Any],
) -> list[dict[str, Any]]:
    """Merge current discovery with watching records; current evidence wins."""
    candidates: list[dict[str, Any]] = []
    index: dict[str, int] = {}

    for candidate in current_candidates:
        identity = _legacy.canonical_keyword(candidate.get("keyword"))
        if not identity:
            continue
        index[identity] = len(candidates)
        candidates.append({"domain": domain, **candidate})

    normalized_domain = _legacy.canonical_keyword(domain)
    for carried in carry_forward(database):
        if _legacy.canonical_keyword(carried.get("domain")) != normalized_domain:
            continue
        identity = _legacy.canonical_keyword(carried.get("keyword"))
        if not identity:
            continue
        if identity in index:
            current = candidates[index[identity]]
            for field, value in carried.items():
                if field not in current or current.get(field) is None:
                    current[field] = value
            continue
        index[identity] = len(candidates)
        candidates.append({"domain": domain, **carried})

    return candidates


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
    timeframe_specs: tuple[tuple[str, str], ...] = _legacy.TIMEFRAME_DEFAULTS,
    throttle: Any = None,
    as_of: datetime | None = None,
    discovered_at: str | None = None,
    existing_database: dict[str, Any] | None = None,
    database_path: Path | None = None,
    csv_path: Path | None = None,
) -> dict[str, Any]:
    """Run the existing radar while carrying forward still-watching records."""
    if not callable(related_fetcher):
        raise ValueError("related_fetcher is required")

    anchors = _legacy.build_anchor_pool(domain, explicit_anchors, root_rows)
    discovery = _legacy.discover_rising_bfs(
        domain,
        anchors,
        lambda anchor: _legacy._call(related_fetcher, (anchor,), throttle),
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
                payload = _legacy._call(fetcher, (anchor["keyword"],), throttle)
                if payload is None:
                    continue
                supplemental_evidence.append(
                    {
                        "source": source,
                        "anchor": anchor["keyword"],
                        "payload": payload,
                        "recursive": False,
                    }
                )
                supplemental_candidates.extend(
                    _legacy._supplemental_candidates(domain, anchor, source, payload, relation_gate)
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
    current_candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in discovered_candidates + supplemental_candidates:
        identity = _legacy.canonical_keyword(candidate.get("keyword"))
        if not identity or identity in seen:
            continue
        if len(current_candidates) >= max_candidates:
            break
        seen.add(identity)
        current_candidates.append({"domain": domain, **candidate})

    database_requested = database_path is not None or csv_path is not None or existing_database is not None
    database_source = _database_snapshot(existing_database, database_path) if database_requested else {"schema_version": 1, "records": []}
    candidates = _candidate_pool(domain, current_candidates, database_source)

    observations: list[dict[str, Any]] = []
    if timeline_fetcher is not None:
        observations = _legacy._timeline_observations(
            candidates,
            timeline_fetcher,
            timeframe_specs,
            throttle,
            blockers,
        )

    aggregate_result = _legacy.aggregate(observations, as_of or datetime.now(timezone.utc)) if observations else {"candidates": []}
    aggregate_by_keyword = {
        _legacy.canonical_keyword(candidate.get("keyword")): candidate
        for candidate in aggregate_result.get("candidates", [])
    }

    classified: list[dict[str, Any]] = []
    thresholds = _legacy.load_thresholds()
    for discovery_candidate in candidates:
        keyword = _legacy.canonical_keyword(discovery_candidate.get("keyword"))
        current = dict(
            aggregate_by_keyword.get(keyword)
            or {
                "keyword": discovery_candidate.get("keyword"),
                "source_count": 0,
                "source_evidence": [],
                "primary_series": None,
            }
        )
        for field, value in discovery_candidate.items():
            if field not in current or current.get(field) is None:
                current[field] = value
        current["domain"] = domain
        classified.append(_legacy.classify_candidate(current, thresholds))

    routes: list[dict[str, Any]] = []
    for candidate in classified:
        route = _legacy.route_candidate(candidate)
        route["domain"] = domain
        routes.append(route)

    database = None
    if database_requested:
        database = _legacy.merge_database(
            database_source,
            classified,
            routes,
            discovered_at or _legacy._now(),
        )
        if database_path is not None and csv_path is not None:
            _legacy.write_database(database, Path(database_path), Path(csv_path))

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
        "candidates": classified,
        "routes": routes,
        "observations": observations,
        "aggregate": aggregate_result,
        "database": database,
        "blockers": blockers,
        "output_artifacts": {},
        "candidate_counts": {
            "discovered": len(discovered_candidates),
            "supplemental": len(supplemental_candidates),
            "unique_pool": len(candidates),
            "classified": len(classified),
        },
    }


# The existing live runner resolves this global at call time, so patching it
# keeps CLI behavior and dependency-injected behavior on the same implementation.
_legacy.run_pipeline = run_pipeline


def main() -> int:
    _legacy.run_pipeline = run_pipeline
    return _legacy.main()


if __name__ == "__main__":
    raise SystemExit(main())
