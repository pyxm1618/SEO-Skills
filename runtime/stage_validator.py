#!/usr/bin/env python3
"""Production-stage contract validator with collector-evidence binding."""

import argparse
import hashlib
import importlib.util
import json
import math
import sys
from pathlib import Path
from urllib.parse import urlparse

NOT_APPLICABLE = "not_applicable"
UNKNOWN = "unknown"
ROOT = Path(__file__).resolve().parent
BINDING_PATH = ROOT / "evidence_binding.py"
COVERAGE_PATH = ROOT / "discovery_coverage.py"
PRODUCTION_BINDINGS = {
    "discovery_autocomplete": "google_autocomplete",
    "discovery_semrush_ideas": "semrush_ideas",
    "discovery_semrush_competitor_organic": "semrush_competitor_organic",
    "stage6_exact": "semrush_exact",
    "intitle_observation": "google_intitle",
    "serp_review": "google_serp",
    "finalist_trend": "google_trends",
}


def _binding():
    spec = importlib.util.spec_from_file_location("seo_evidence_binding", BINDING_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _coverage():
    spec = importlib.util.spec_from_file_location("seo_discovery_coverage_validator", COVERAGE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def value_state(value):
    if value is None:
        return "missing"
    if isinstance(value, str):
        text = value.strip()
        if text == "":
            return "missing"
        lowered = text.lower()
        if lowered == NOT_APPLICABLE:
            return "not_applicable"
        if lowered == UNKNOWN:
            return "unknown"
    if isinstance(value, float) and not math.isfinite(value):
        return "invalid"
    return "value"


def _host(value):
    text = str(value or "").strip()
    if not text:
        return ""
    parsed = urlparse(text if "://" in text else f"https://{text}")
    return (parsed.hostname or "").lower()


def _condition_matches(payload, condition):
    field = condition.get("field")
    if field is None:
        return False
    value = payload.get(field)
    if "equals" in condition and value != condition["equals"]:
        return False
    if "gte" in condition:
        try:
            if float(value) < float(condition["gte"]):
                return False
        except (TypeError, ValueError):
            return False
    if "lte" in condition:
        try:
            if float(value) > float(condition["lte"]):
                return False
        except (TypeError, ValueError):
            return False
    return True


def _parse_number(value):
    if isinstance(value, bool):
        return None
    try:
        text = str(value).strip().replace(",", "") if not isinstance(value, (int, float)) else value
        number = float(text)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _validate_number_range(field, value, rule):
    if value_state(value) != "value":
        return []
    number = _parse_number(value)
    if number is None:
        return [f"{field}:not_numeric"]
    errors = []
    if rule.get("integer") and not number.is_integer():
        errors.append(f"{field}:must_be_integer")
    if "min" in rule and number < float(rule["min"]):
        errors.append(f"{field}:below_min_{rule['min']}")
    if "max" in rule and number > float(rule["max"]):
        errors.append(f"{field}:above_max_{rule['max']}")
    return errors


def _validate_production_binding(stage, payload):
    if stage == "finalist_trend" and payload.get("is_finalist") is not True:
        return []
    binding = _binding()
    try:
        if stage == "kgr_intitle":
            binding.verify_kgr_payload(payload)
        else:
            evidence_type = PRODUCTION_BINDINGS.get(stage)
            if evidence_type:
                binding.verify_payload(payload, evidence_type)
    except Exception as exc:
        return [f"evidence:{exc}"]
    return []


def validate_stage(stage, payload, contracts, production=False):
    if stage not in contracts:
        return [f"stage:unknown:{stage}"]
    if not isinstance(payload, dict):
        return ["payload:must_be_object"]

    spec = contracts[stage]
    errors = []

    for field in spec.get("required", []):
        state = value_state(payload.get(field))
        if state == "missing":
            errors.append(f"{field}:required")
        elif state == "invalid":
            errors.append(f"{field}:invalid")
        elif state == "unknown":
            errors.append(f"{field}:unknown_not_allowed")
        elif state == "not_applicable":
            errors.append(f"{field}:not_applicable_not_allowed")

    for field, expected in spec.get("equals", {}).items():
        if value_state(payload.get(field)) == "value" and payload.get(field) != expected:
            errors.append(f"{field}:must_equal:{expected}")

    for field, expected_host in spec.get("host_equals", {}).items():
        if value_state(payload.get(field)) == "value" and _host(payload.get(field)) != expected_host.lower():
            errors.append(f"{field}:wrong_source_host:{_host(payload.get(field)) or 'missing'}")

    for field, minimum in spec.get("list_min", {}).items():
        value = payload.get(field)
        if value_state(value) == "value" and (not isinstance(value, list) or len(value) < minimum):
            errors.append(f"{field}:requires_at_least_{minimum}_items")

    for field, length in spec.get("list_length", {}).items():
        value = payload.get(field)
        if value_state(value) == "value" and (not isinstance(value, list) or len(value) != length):
            errors.append(f"{field}:requires_exactly_{length}_items")

    for field, rule in spec.get("number_range", {}).items():
        errors.extend(_validate_number_range(field, payload.get(field), rule))

    for left, right in spec.get("equal_fields", []):
        if value_state(payload.get(left)) == "value" and value_state(payload.get(right)) == "value":
            if payload.get(left) != payload.get(right):
                errors.append(f"{left}:{right}:must_match")

    for field, required_item_fields in spec.get("items_required", {}).items():
        items = payload.get(field)
        if isinstance(items, list):
            for index, item in enumerate(items):
                if not isinstance(item, dict):
                    errors.append(f"{field}[{index}]:must_be_object")
                    continue
                for item_field in required_item_fields:
                    if value_state(item.get(item_field)) != "value":
                        errors.append(f"{field}[{index}].{item_field}:required")

    for rule in spec.get("conditional_required", []):
        if _condition_matches(payload, rule.get("when", {})):
            for field in rule.get("fields", []):
                if value_state(payload.get(field)) != "value":
                    errors.append(f"{field}:conditionally_required")

    for rule in spec.get("conditional_equals", []):
        if _condition_matches(payload, rule.get("when", {})):
            field = rule.get("field")
            expected = rule.get("equals")
            if payload.get(field) != expected:
                errors.append(f"{field}:must_equal:{expected}")

    if stage == "discovery_coverage" and not errors:
        errors.extend(_coverage().validate_coverage(payload, production=production))

    if production and not errors:
        errors.extend(_validate_production_binding(stage, payload))
    return errors


def validate_payload(stage, data, contracts, production=False):
    if stage == "discovery_coverage" and isinstance(data, dict):
        data = _coverage().enrich_coverage(data)
    # Semrush Ideas is a stage-level envelope whose own contract requires the
    # top-level seed/rows/observed_at/source fields. Its rows are evidence data,
    # not independent stage payloads. Other list-shaped inputs remain batches.
    if stage == "discovery_semrush_ideas" and isinstance(data, dict):
        rows = [data]
    elif isinstance(data, list):
        rows = data
    elif isinstance(data, dict) and isinstance(data.get("rows"), list):
        rows = data["rows"]
    else:
        rows = [data]

    complete = []
    blocked = []
    for row in rows:
        errors = validate_stage(stage, row, contracts, production=production)
        if errors:
            blocked.append({"row": row, "errors": errors})
        else:
            complete.append(row)
    return complete, blocked


def batch_status(complete, blocked):
    if complete and not blocked:
        return "PASS"
    if complete and blocked:
        return "PARTIAL"
    return "BLOCKED"


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _write_validation_receipt(report_path, report, candidate_id=None):
    """Bind a PASS report to this validator source and its exact report bytes."""
    report_path = Path(report_path)
    receipt_path = report_path.with_suffix(".receipt.json")
    report["validation_receipt_ref"] = str(receipt_path)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    receipt = {
        "schema": "seo-stage-validation/v1",
        "stage": report["stage"],
        "status": report["status"],
        "candidate_id": candidate_id,
        "validator_source_sha256": _sha256(Path(__file__).resolve()),
        "report_ref": str(report_path),
        "report_sha256": _sha256(report_path),
    }
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return receipt_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--contracts", default=str(Path(__file__).with_name("stage_contracts.json")))
    parser.add_argument("--stage", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--report")
    parser.add_argument("--production", action="store_true", help="require collector-bound evidence for observed stages")
    parser.add_argument("--candidate-id")
    args = parser.parse_args()

    if args.production and not args.report:
        print("BLOCKED: --production requires --report so a validation receipt can be issued", file=sys.stderr)
        return 2

    contracts = json.loads(Path(args.contracts).read_text(encoding="utf-8"))
    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    complete, blocked = validate_payload(args.stage, data, contracts, production=args.production)
    report = {
        "stage": args.stage,
        "status": batch_status(complete, blocked),
        "production": bool(args.production),
        "candidate_id": args.candidate_id,
        "complete_count": len(complete),
        "blocked_count": len(blocked),
        "complete": complete,
        "blocked": blocked,
    }

    receipt_error = None
    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        if args.production and not blocked:
            try:
                _write_validation_receipt(report_path, report, args.candidate_id)
            except Exception as exc:
                receipt_error = str(exc)
                if not report_path.is_file():
                    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        else:
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if receipt_error:
        print(f"BLOCKED: {receipt_error}", file=sys.stderr)
        return 2
    if blocked:
        for item in blocked:
            print(" | ".join(item["errors"]), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
