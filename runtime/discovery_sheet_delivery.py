#!/usr/bin/env python3
"""Verification for Google Sheet delivery bound to a Discovery handoff."""

import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXPORTER_PATH = ROOT.parent / "skills" / "seo-keyword-discovery" / "scripts" / "export_to_sheet.py"
EXPECTED_SCHEMA = "seo-discovery-sheet-delivery/v1"
EXPECTED_WORKSHEET = "keyword_discovery"


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _exporter():
    spec = importlib.util.spec_from_file_location("seo_discovery_sheet_exporter_verifier", EXPORTER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_handoff(payload):
    if not isinstance(payload, dict):
        return ["sheet_delivery:handoff_must_be_object"]
    receipt_ref = str(payload.get("sheet_delivery_receipt_ref") or "").strip()
    if not receipt_ref:
        return ["sheet_delivery_receipt_ref:required_for_production_handoff"]
    receipt_path = Path(receipt_ref)
    if not receipt_path.is_file():
        return ["sheet_delivery_receipt:file_missing"]
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"sheet_delivery_receipt:invalid_json:{exc}"]
    if not isinstance(receipt, dict):
        return ["sheet_delivery_receipt:must_be_object"]

    errors = []
    if receipt.get("schema") != EXPECTED_SCHEMA:
        errors.append("sheet_delivery_receipt:schema_mismatch")
    if receipt.get("status") != "PASS":
        errors.append("sheet_delivery_receipt:status_must_be_PASS")
    if str(receipt.get("batch_id") or "").strip() != str(payload.get("batch_id") or "").strip():
        errors.append("sheet_delivery_receipt:batch_id_mismatch")
    if str(receipt.get("worksheet") or "").strip() != EXPECTED_WORKSHEET:
        errors.append("sheet_delivery_receipt:worksheet_mismatch")
    if not str(receipt.get("sheet_id") or "").strip():
        errors.append("sheet_delivery_receipt:sheet_id_required")

    keywords = payload.get("keywords")
    expected_count = len(keywords) if isinstance(keywords, list) else None
    if expected_count is None:
        errors.append("sheet_delivery_receipt:handoff_keywords_must_be_list")
    else:
        if receipt.get("record_count") != expected_count:
            errors.append("sheet_delivery_receipt:record_count_mismatch")
        if receipt.get("verified_count") != expected_count:
            errors.append("sheet_delivery_receipt:verified_count_mismatch")
        if receipt.get("record_count") != receipt.get("verified_count"):
            errors.append("sheet_delivery_receipt:record_count_verified_count_mismatch")

    try:
        exporter = _exporter()
        expected_binding = exporter.handoff_binding_sha256(payload)
    except Exception as exc:
        errors.append(f"sheet_delivery_receipt:binding_verifier_failed:{exc}")
        expected_binding = None
    if expected_binding is not None and receipt.get("handoff_binding_sha256") != expected_binding:
        errors.append("sheet_delivery_receipt:handoff_binding_mismatch")

    try:
        current_exporter_hash = _sha256(EXPORTER_PATH)
    except OSError as exc:
        errors.append(f"sheet_delivery_receipt:exporter_source_unreadable:{exc}")
        current_exporter_hash = None
    if current_exporter_hash is not None and receipt.get("exporter_source_sha256") != current_exporter_hash:
        errors.append("sheet_delivery_receipt:exporter_source_mismatch")
    return errors
