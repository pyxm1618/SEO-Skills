import hashlib
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "runtime" / "stage_validator.py"
EXPORTER = ROOT / "skills" / "seo-keyword-discovery" / "scripts" / "export_to_sheet.py"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def handoff():
    return {
        "batch_id": "batch-sheet-gate",
        "required_seed_count": 1,
        "autocomplete_pass_count": 1,
        "status": "PASS",
        "coverage_status": "PASS",
        "coverage_receipt_ref": "coverage.receipt.json",
        "keywords": [
            {
                "candidate_id": "candidate-1",
                "keyword": "perfume finder by notes",
                "source": "google_serp_expansions",
                "source_seed": "perfume finder",
                "evidence_receipt_ref": "expansion.receipt.json",
            }
        ],
    }


def write_receipt(tmp_path, payload, **overrides):
    exporter = load(EXPORTER, "sheet_gate_exporter")
    receipt = {
        "schema": "seo-discovery-sheet-delivery/v1",
        "status": "PASS",
        "batch_id": payload["batch_id"],
        "worksheet": "keyword_discovery",
        "sheet_id": "sheet-123",
        "record_count": len(payload["keywords"]),
        "verified_count": len(payload["keywords"]),
        "handoff_binding_sha256": exporter.handoff_binding_sha256(payload),
        "exporter_source_sha256": hashlib.sha256(EXPORTER.read_bytes()).hexdigest(),
    }
    receipt.update(overrides)
    path = tmp_path / "sheet-delivery.receipt.json"
    path.write_text(json.dumps(receipt), encoding="utf-8")
    payload["sheet_delivery_receipt_ref"] = str(path)
    return path


def test_valid_sheet_delivery_receipt_is_accepted(tmp_path):
    validator = load(VALIDATOR, "sheet_gate_valid")
    payload = handoff()
    write_receipt(tmp_path, payload)
    assert validator._verify_sheet_delivery_receipt_for_handoff(payload) == []


def test_missing_sheet_delivery_receipt_is_blocked():
    validator = load(VALIDATOR, "sheet_gate_missing")
    errors = validator._verify_sheet_delivery_receipt_for_handoff(handoff())
    assert any("sheet_delivery_receipt_ref" in error for error in errors)


def test_sheet_receipt_is_bound_to_exact_handoff_keywords(tmp_path):
    validator = load(VALIDATOR, "sheet_gate_binding")
    payload = handoff()
    write_receipt(tmp_path, payload)
    payload["keywords"][0]["keyword"] = "tampered keyword"
    errors = validator._verify_sheet_delivery_receipt_for_handoff(payload)
    assert any("binding" in error for error in errors)


def test_sheet_receipt_requires_exact_readback_count(tmp_path):
    validator = load(VALIDATOR, "sheet_gate_count")
    payload = handoff()
    write_receipt(tmp_path, payload, verified_count=0)
    errors = validator._verify_sheet_delivery_receipt_for_handoff(payload)
    assert any("verified_count" in error or "record_count" in error for error in errors)


def test_sheet_receipt_is_bound_to_current_exporter_source(tmp_path):
    validator = load(VALIDATOR, "sheet_gate_source")
    payload = handoff()
    write_receipt(tmp_path, payload, exporter_source_sha256="0" * 64)
    errors = validator._verify_sheet_delivery_receipt_for_handoff(payload)
    assert any("exporter" in error for error in errors)
