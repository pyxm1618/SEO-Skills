#!/usr/bin/env python3
"""Run and attest the canonical four-step Emerging Monitor pipeline."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
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


def _as_of_datetime(value: str | datetime, aggregate: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return aggregate.end_of_day(value)


def parse_as_of(value: str) -> datetime:
    return _as_of_datetime(value, _modules()["aggregate"])


def replay_pipeline(input_path: Path, as_of: str | datetime) -> dict[str, dict[str, Any]]:
    modules = _modules()
    input_path = Path(input_path)
    as_of_datetime = _as_of_datetime(as_of, modules["aggregate"])
    raw_rows = modules["validate"].load_rows(input_path)
    validated_rows = modules["validate"].validate_rows(raw_rows, as_of_datetime)
    aggregated = modules["aggregate"].aggregate(raw_rows, as_of_datetime)
    thresholds = modules["classify"].load_thresholds()
    classified_rows = [
        modules["classify"].classify_candidate(candidate, thresholds)
        for candidate in aggregated["candidates"]
    ]
    routed_rows = [modules["route"].route_candidate(candidate) for candidate in classified_rows]
    return {
        "validated": {"rows": validated_rows},
        "aggregated": aggregated,
        "classified": {"candidates": classified_rows},
        "routed": {"routes": routed_rows},
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

    receipt = {
        "schema": "seo-emerging-pipeline/v1",
        "as_of": as_of_datetime.isoformat(),
        "observation_input": {"path": str(input_path), "sha256": _sha256(input_path)},
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
    args = parser.parse_args()
    try:
        receipt = run_pipeline(Path(args.input), Path(args.output_dir), args.as_of, Path(args.receipt) if args.receipt else None)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"BLOCKED: {exc}", file=os.sys.stderr)
        return 2
    print(json.dumps(receipt, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
