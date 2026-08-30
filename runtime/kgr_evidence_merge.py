#!/usr/bin/env python3
"""Deterministically join verified Stage 6 volume with Google intitle evidence.

This module only prepares KGR inputs. It does not calculate KGR or alter the
existing evaluator's business rules.
"""

import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONTRACTS_PATH = ROOT / "stage_contracts.json"
VALIDATOR_PATH = ROOT / "stage_validator.py"
BINDING_PATH = ROOT / "evidence_binding.py"


def _load_validator():
    spec = importlib.util.spec_from_file_location("seo_stage_validator_for_kgr", VALIDATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_binding():
    spec = importlib.util.spec_from_file_location("seo_evidence_binding_for_kgr", BINDING_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _norm_keyword(value):
    return " ".join(str(value or "").split()).casefold()


def _norm_market(value):
    text = str(value or "").strip().casefold()
    return {"united states": "us", "usa": "us", "us": "us"}.get(text, text)


def _fail_if_invalid(stage, row, contracts, label):
    validator = _load_validator()
    errors = validator.validate_stage(stage, row, contracts)
    if errors:
        raise ValueError(f"{label} evidence failed {stage}: {' | '.join(errors)}")


def merge_exact_and_intitle(exact, intitle, contracts=None, verify_evidence=False):
    contracts = contracts or json.loads(CONTRACTS_PATH.read_text(encoding="utf-8"))
    if not isinstance(exact, dict) or not isinstance(intitle, dict):
        raise ValueError("exact and intitle evidence must be JSON objects")

    _fail_if_invalid("stage6_exact", exact, contracts, "exact")
    _fail_if_invalid("intitle_observation", intitle, contracts, "intitle")
    if verify_evidence:
        binding = _load_binding()
        binding.verify_payload(exact, "semrush_exact")
        binding.verify_payload(intitle, "google_intitle")

    if _norm_keyword(exact.get("keyword")) != _norm_keyword(intitle.get("keyword")):
        raise ValueError("keyword identity mismatch between exact and intitle evidence")
    exact_market = _norm_market(exact.get("metric_database"))
    intitle_market = _norm_market(intitle.get("market"))
    if exact_market != intitle_market:
        raise ValueError(
            f"market/database mismatch between exact ({exact_market}) and intitle ({intitle_market}) evidence"
        )

    merged = dict(exact)
    merged.update(
        {
            "intitle_results": intitle["intitle_results"],
            "exact_observed_at": exact["observed_at"],
            "exact_provenance_ref": exact["provenance_ref"],
            "exact_evidence_receipt_ref": exact.get("evidence_receipt_ref"),
            "intitle_source": intitle["source"],
            "market": intitle["market"],
            "intitle_observed_at": intitle["observed_at"],
            "intitle_provenance_ref": intitle["evidence_ref"],
            "intitle_evidence_receipt_ref": intitle.get("evidence_receipt_ref"),
        }
    )
    _fail_if_invalid("kgr_intitle", merged, contracts, "merged KGR input")
    if verify_evidence:
        _load_binding().verify_kgr_payload(merged)
    return merged


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--exact", required=True, help="verified Stage 6 exact evidence JSON")
    parser.add_argument("--intitle", required=True, help="verified Google intitle observation JSON")
    parser.add_argument("--output", required=True)
    parser.add_argument("--contracts", default=str(CONTRACTS_PATH))
    args = parser.parse_args()

    try:
        exact = json.loads(Path(args.exact).read_text(encoding="utf-8"))
        intitle = json.loads(Path(args.intitle).read_text(encoding="utf-8"))
        contracts = json.loads(Path(args.contracts).read_text(encoding="utf-8"))
        merged = merge_exact_and_intitle(exact, intitle, contracts, verify_evidence=True)
        text = json.dumps(merged, ensure_ascii=False, indent=2)
        Path(args.output).write_text(text + "\n", encoding="utf-8")
        print(text)
        return 0
    except Exception as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
