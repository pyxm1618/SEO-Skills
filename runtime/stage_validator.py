#!/usr/bin/env python3
"""Lightweight production-stage contract validator.

This validates evidence completeness and provenance before production-stage
transitions. It does not make SEO decisions and does not replace the existing
evaluator.
"""

import argparse
import json
import math
import sys
from pathlib import Path
from urllib.parse import urlparse


NOT_APPLICABLE = "not_applicable"
UNKNOWN = "unknown"


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


def validate_stage(stage, payload, contracts):
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
                state = value_state(payload.get(field))
                if state != "value":
                    errors.append(f"{field}:conditionally_required")

    for rule in spec.get("conditional_equals", []):
        if _condition_matches(payload, rule.get("when", {})):
            field = rule.get("field")
            expected = rule.get("equals")
            if payload.get(field) != expected:
                errors.append(f"{field}:must_equal:{expected}")

    return errors


def validate_payload(stage, data, contracts):
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict) and isinstance(data.get("rows"), list):
        rows = data["rows"]
    else:
        rows = [data]

    complete = []
    blocked = []
    for row in rows:
        errors = validate_stage(stage, row, contracts)
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--contracts", default=str(Path(__file__).with_name("stage_contracts.json")))
    parser.add_argument("--stage", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--report")
    args = parser.parse_args()

    contracts = json.loads(Path(args.contracts).read_text(encoding="utf-8"))
    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    complete, blocked = validate_payload(args.stage, data, contracts)
    report = {
        "stage": args.stage,
        "status": batch_status(complete, blocked),
        "complete_count": len(complete),
        "blocked_count": len(blocked),
        "complete": complete,
        "blocked": blocked,
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        Path(args.report).write_text(text + "\n", encoding="utf-8")
    print(text)
    if blocked:
        for item in blocked:
            print(" | ".join(item["errors"]), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
