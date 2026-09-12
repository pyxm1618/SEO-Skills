#!/usr/bin/env python3
"""Run, replay, and attest the canonical Emerging Monitor pipeline.

The canonical pipeline owns aggregation, classification, routing, and identity
reconciliation. A Radar run may additionally provide a candidate ledger so
that candidates with no observations remain part of the attested run scope.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
SCRIPT_PATHS = {
    "validate_observations.py": ROOT.parent / "skills" / "emerging-keyword-monitor" / "scripts" / "validate_observations.py",
    "birth_history.py": ROOT.parent / "skills" / "emerging-keyword-monitor" / "scripts" / "birth_history.py",
    "aggregate_signals.py": ROOT.parent / "skills" / "emerging-keyword-monitor" / "scripts" / "aggregate_signals.py",
    "classify_emergence.py": ROOT.parent / "skills" / "emerging-keyword-monitor" / "scripts" / "classify_emergence.py",
    "route_candidates.py": ROOT.parent / "skills" / "emerging-keyword-monitor" / "scripts" / "route_candidates.py",
}
THRESHOLDS_PATH = ROOT.parent / "skills" / "emerging-keyword-monitor" / "references" / "thresholds.json"
PIPELINE_SOURCE_PATH = Path(__file__).resolve()

CANDIDATE_CONTEXT_FIELDS = (
    "candidate_id",
    "domain",
    "domain_relation",
    "domain_relation_reason",
    "variant_subtype",
    "variant_evidence",
    "root_id",
    "root_relation",
    "root_candidate_hypothesis",
    "previous_status",
    "acquisition_status",
    "verification_status",
)


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load Emerging pipeline module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _modules() -> dict[str, Any]:
    validate = _load_module(SCRIPT_PATHS["validate_observations.py"], "seo_emerging_validate_observations")
    sys.modules["validate_observations"] = validate
    birth_history = _load_module(SCRIPT_PATHS["birth_history.py"], "seo_emerging_birth_history")
    sys.modules["birth_history"] = birth_history
    aggregate = _load_module(SCRIPT_PATHS["aggregate_signals.py"], "seo_emerging_aggregate_signals")
    classify = _load_module(SCRIPT_PATHS["classify_emergence.py"], "seo_emerging_classify_emergence")
    route = _load_module(SCRIPT_PATHS["route_candidates.py"], "seo_emerging_route_candidates")
    return {"validate": validate, "aggregate": aggregate, "classify": classify, "route": route}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_sha256(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _as_of_datetime(value: str | datetime, aggregate: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return aggregate.end_of_day(value)


def parse_as_of(value: str) -> datetime:
    return _as_of_datetime(value, _modules()["aggregate"])


def _is_missing(value: Any) -> bool:
    return value is None or (
        isinstance(value, str)
        and value.strip().casefold() in {"", "unknown", "null", "none", "n/a", "na"}
    )


def _candidate_context(raw_rows: list[dict[str, Any]], aggregate: Any) -> dict[str, dict[str, Any]]:
    contexts: dict[str, dict[str, Any]] = {}
    for row in raw_rows:
        if not isinstance(row, dict):
            continue
        keyword = aggregate.canonical_keyword(row.get("keyword"))
        if not keyword:
            continue
        context = contexts.setdefault(keyword, {})
        for field in CANDIDATE_CONTEXT_FIELDS:
            value = row.get(field)
            if _is_missing(value):
                continue
            if field in context and context[field] != value:
                raise ValueError(f"conflicting candidate context for {keyword}: {field}")
            context[field] = value
    return contexts


def _merge_candidate_context(aggregated: dict[str, Any], raw_rows: list[dict[str, Any]], aggregate: Any) -> None:
    contexts = _candidate_context(raw_rows, aggregate)
    for candidate in aggregated.get("candidates", []):
        if not isinstance(candidate, dict):
            continue
        context = contexts.get(aggregate.canonical_keyword(candidate.get("keyword")), {})
        for field, value in context.items():
            if _is_missing(candidate.get(field)):
                candidate[field] = value


def classify_and_route_rows(raw_rows: list[dict[str, Any]], as_of: str | datetime) -> dict[str, Any]:
    """Canonical aggregation -> classification -> routing for acquired rows."""
    modules = _modules()
    as_of_datetime = _as_of_datetime(as_of, modules["aggregate"])
    aggregated = modules["aggregate"].aggregate(raw_rows, as_of_datetime) if raw_rows else {"candidates": []}
    _merge_candidate_context(aggregated, raw_rows, modules["aggregate"])
    thresholds = modules["classify"].load_thresholds()
    classified_rows = [
        modules["classify"].classify_candidate(candidate, thresholds)
        for candidate in aggregated.get("candidates", [])
    ]
    routed_rows: list[dict[str, Any]] = []
    for candidate in classified_rows:
        routed = modules["route"].route_candidate(candidate)
        for field in ("candidate_id", "domain"):
            if not _is_missing(candidate.get(field)) and _is_missing(routed.get(field)):
                routed[field] = candidate[field]
        routed_rows.append(routed)
    return {"aggregated": aggregated, "classified": classified_rows, "routed": routed_rows}


def replay_pipeline(input_path: Path, as_of: str | datetime) -> dict[str, dict[str, Any]]:
    modules = _modules()
    input_path = Path(input_path)
    as_of_datetime = _as_of_datetime(as_of, modules["aggregate"])
    raw_rows = modules["validate"].load_rows(input_path)
    validated_rows = modules["validate"].validate_rows(raw_rows, as_of_datetime)
    canonical = classify_and_route_rows(raw_rows, as_of_datetime)
    return {
        "validated": {"rows": validated_rows},
        "aggregated": canonical["aggregated"],
        "classified": {"candidates": canonical["classified"]},
        "routed": {"routes": canonical["routed"]},
    }


def _candidate_id(row: dict[str, Any]) -> str | None:
    value = str(row.get("candidate_id") or "").strip()
    if value:
        return value
    keyword = " ".join(str(row.get("keyword") or "").casefold().split())
    return f"keyword:{keyword}" if keyword else None


def _load_candidate_ledger(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("candidate_ledger")
    if not isinstance(payload, list) or not all(isinstance(row, dict) for row in payload):
        raise ValueError("candidate ledger must be a JSON list or object containing candidate_ledger")
    return payload


def reconcile_identity_sets(
    candidate_ledger: list[dict[str, Any]],
    classified_rows: list[dict[str, Any]],
    routed_rows: list[dict[str, Any]],
    delivery_ids: list[str] | None = None,
) -> dict[str, Any]:
    candidate_ids = [_candidate_id(row) for row in candidate_ledger]
    if any(value is None for value in candidate_ids):
        raise ValueError("every candidate ledger row must have candidate_id or keyword")
    candidate_ids = [str(value) for value in candidate_ids]
    classified_ids = [value for row in classified_rows if (value := _candidate_id(row))]
    route_ids = [value for row in routed_rows if (value := _candidate_id(row))]
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError("candidate ledger contains duplicate identities")
    if len(classified_ids) != len(set(classified_ids)):
        raise ValueError("classified output contains duplicate identities")
    if len(route_ids) != len(set(route_ids)):
        raise ValueError("routed output contains duplicate identities")
    candidate_set = set(candidate_ids)
    classified_set = set(classified_ids)
    route_set = set(route_ids)
    delivery_set = set(str(value) for value in (delivery_ids or classified_ids))
    if not classified_set <= candidate_set:
        raise ValueError("classified identity exists outside candidate ledger")
    if route_set != classified_set:
        raise ValueError("route identity set must exactly equal classified identity set")
    if not delivery_set <= route_set:
        raise ValueError("delivery identity set must be a subset of routed identities")

    dispositions = Counter(str(row.get("final_disposition") or "unknown") for row in candidate_ledger)
    identity_payload = {
        "candidate_ids": candidate_ids,
        "classified_ids": classified_ids,
        "route_ids": route_ids,
        "delivery_ids": sorted(delivery_set),
    }
    return {
        **identity_payload,
        "candidate_count": len(candidate_ids),
        "classified_count": len(classified_ids),
        "route_count": len(route_ids),
        "delivery_count": len(delivery_set),
        "terminal_state_counts": dict(sorted(dispositions.items())),
        "terminal_state_count": sum(dispositions.values()),
        "identity_sha256": _json_sha256(identity_payload),
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def run_pipeline(
    input_path: Path,
    output_dir: Path,
    as_of: str,
    receipt_path: Path | None = None,
    candidate_ledger_path: Path | None = None,
) -> dict[str, Any]:
    input_path = Path(input_path).expanduser().resolve()
    if not input_path.is_file():
        raise FileNotFoundError(f"Emerging observations input is missing: {input_path}")
    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = (Path(receipt_path).expanduser() if receipt_path else output_dir / "receipt.json").resolve()
    output_paths = {name: output_dir / f"{name}.json" for name in ("validated", "aggregated", "classified", "routed")}
    all_paths = [*output_paths.values(), receipt_path]
    existing = [path for path in all_paths if path.exists()]
    if existing:
        raise FileExistsError(f"Emerging pipeline output already exists: {existing[0]}")

    modules = _modules()
    as_of_datetime = _as_of_datetime(as_of, modules["aggregate"])
    outputs = replay_pipeline(input_path, as_of_datetime)
    for name, payload in outputs.items():
        _write_json(output_paths[name], payload)

    classified_rows = outputs["classified"]["candidates"]
    routed_rows = outputs["routed"]["routes"]
    ledger_ref = None
    if candidate_ledger_path is not None:
        ledger_path = Path(candidate_ledger_path).expanduser().resolve()
        if not ledger_path.is_file():
            raise FileNotFoundError(f"Emerging candidate ledger is missing: {ledger_path}")
        candidate_ledger = _load_candidate_ledger(ledger_path)
        ledger_ref = {"path": str(ledger_path), "sha256": _sha256(ledger_path)}
    else:
        candidate_ledger = [
            {"candidate_id": _candidate_id(row), "keyword": row.get("keyword"), "final_disposition": "classified"}
            for row in classified_rows
        ]
    reconciliation = reconcile_identity_sets(candidate_ledger, classified_rows, routed_rows)

    receipt = {
        "schema": "seo-emerging-pipeline/v2",
        "as_of": as_of_datetime.isoformat(),
        "observation_input": {"path": str(input_path), "sha256": _sha256(input_path)},
        "candidate_ledger": ledger_ref,
        "reconciliation": reconciliation,
        "pipeline": {"path": str(PIPELINE_SOURCE_PATH), "sha256": _sha256(PIPELINE_SOURCE_PATH)},
        "scripts": {
            name: {"path": str(path.resolve()), "sha256": _sha256(path)}
            for name, path in SCRIPT_PATHS.items()
        },
        "thresholds": {"path": str(THRESHOLDS_PATH.resolve()), "sha256": _sha256(THRESHOLDS_PATH)},
        "outputs": {
            name: {"path": str(path.resolve()), "sha256": _sha256(path)}
            for name, path in output_paths.items()
        },
        "route_handoff_ref": str(output_paths["routed"].resolve()),
    }
    _write_json(receipt_path, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--receipt")
    parser.add_argument("--candidate-ledger", help="optional JSON ledger used to attest zero-observation candidates")
    args = parser.parse_args()
    try:
        receipt = run_pipeline(
            Path(args.input),
            Path(args.output_dir),
            args.as_of,
            Path(args.receipt) if args.receipt else None,
            Path(args.candidate_ledger) if args.candidate_ledger else None,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"BLOCKED: {exc}", file=os.sys.stderr)
        return 2
    print(json.dumps(receipt, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
