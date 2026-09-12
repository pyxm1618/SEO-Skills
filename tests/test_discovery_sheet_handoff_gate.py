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


def handoff(keywords=None):
    return {
        "batch_id": "batch-sheet-gate",
        "market": "US",
        "language": "en",
        "required_seed_count": 1,
        "autocomplete_pass_count": 1,
        "status": "PASS",
        "coverage_status": "PASS",
        "coverage_receipt_ref": "coverage.receipt.json",
        "keywords": keywords
        or [
            {
                "candidate_id": "candidate-1",
                "keyword": "perfume finder by notes",
                "source": "google_serp_expansions",
                "source_seed": "perfume finder",
                "evidence_receipt_ref": "expansion.receipt.json",
            }
        ],
    }


def duplicate_keyword_handoff():
    return handoff(
        keywords=[
            {
                "candidate_id": "candidate-1",
                "keyword": "AI Logo Generator",
                "source": "google_autocomplete",
                "source_seed": "ai logo",
                "evidence_receipt_ref": "autocomplete.receipt.json",
            },
            {
                "candidate_id": "candidate-2",
                "keyword": " ai   logo generator ",
                "source": "semrush_ideas",
                "source_seed": "logo generator",
                "evidence_receipt_ref": "semrush.receipt.json",
            },
        ]
    )


def candidate_bindings(payload):
    exporter = load(EXPORTER, "sheet_gate_exporter_bindings")
    return exporter.build_candidate_bindings(payload)


def write_receipt(tmp_path, payload, **overrides):
    exporter = load(EXPORTER, "sheet_gate_exporter")
    bindings = candidate_bindings(payload)
    stable_count = len({item["stable_key"] for item in bindings})
    receipt = {
        "schema": "seo-discovery-sheet-delivery/v2",
        "status": "PASS",
        "batch_id": payload["batch_id"],
        "worksheet": "关键词库",
        "sheet_id": "sheet-123",
        "candidate_count": len(payload["keywords"]),
        "verified_candidate_count": len(payload["keywords"]),
        "stable_row_count": stable_count,
        "verified_stable_row_count": stable_count,
        "candidate_bindings": bindings,
        "handoff_binding_sha256": exporter.handoff_binding_sha256(payload),
        "exporter_source_sha256": hashlib.sha256(EXPORTER.read_bytes()).hexdigest(),
    }
    receipt.update(overrides)
    path = tmp_path / "sheet-delivery.receipt.json"
    path.write_text(json.dumps(receipt), encoding="utf-8")
    payload["sheet_delivery_receipt_ref"] = str(path)
    return path


def test_valid_v2_sheet_delivery_receipt_is_accepted(tmp_path):
    validator = load(VALIDATOR, "sheet_gate_valid_v2")
    payload = handoff()
    write_receipt(tmp_path, payload)
    assert validator._verify_sheet_delivery_receipt_for_handoff(payload) == []


def test_v2_receipt_accepts_multiple_candidates_bound_to_one_stable_row(tmp_path):
    validator = load(VALIDATOR, "sheet_gate_many_to_one_v2")
    payload = duplicate_keyword_handoff()
    write_receipt(tmp_path, payload)
    assert validator._verify_sheet_delivery_receipt_for_handoff(payload) == []


def test_missing_sheet_delivery_receipt_is_blocked():
    validator = load(VALIDATOR, "sheet_gate_missing_v2")
    errors = validator._verify_sheet_delivery_receipt_for_handoff(handoff())
    assert any("sheet_delivery_receipt_ref" in error for error in errors)


def test_sheet_receipt_is_bound_to_exact_handoff_keywords(tmp_path):
    validator = load(VALIDATOR, "sheet_gate_binding_v2")
    payload = handoff()
    write_receipt(tmp_path, payload)
    payload["keywords"][0]["keyword"] = "tampered keyword"
    errors = validator._verify_sheet_delivery_receipt_for_handoff(payload)
    assert any("binding" in error for error in errors)


def test_sheet_receipt_requires_exact_candidate_count(tmp_path):
    validator = load(VALIDATOR, "sheet_gate_candidate_count_v2")
    payload = handoff()
    write_receipt(tmp_path, payload, verified_candidate_count=0)
    errors = validator._verify_sheet_delivery_receipt_for_handoff(payload)
    assert any("candidate_count" in error or "verified_candidate_count" in error for error in errors)


def test_sheet_receipt_requires_exact_stable_row_count(tmp_path):
    validator = load(VALIDATOR, "sheet_gate_stable_count_v2")
    payload = duplicate_keyword_handoff()
    write_receipt(tmp_path, payload, stable_row_count=2)
    errors = validator._verify_sheet_delivery_receipt_for_handoff(payload)
    assert any("stable_row_count" in error for error in errors)


def test_sheet_receipt_requires_complete_candidate_bindings(tmp_path):
    validator = load(VALIDATOR, "sheet_gate_candidate_bindings_v2")
    payload = duplicate_keyword_handoff()
    write_receipt(tmp_path, payload, candidate_bindings=candidate_bindings(payload)[:1])
    errors = validator._verify_sheet_delivery_receipt_for_handoff(payload)
    assert any("candidate_bindings" in error for error in errors)


def test_sheet_receipt_candidate_binding_provenance_must_match_handoff(tmp_path):
    validator = load(VALIDATOR, "sheet_gate_provenance_v2")
    payload = duplicate_keyword_handoff()
    bindings = candidate_bindings(payload)
    bindings[0]["evidence_receipt_ref"] = "wrong.receipt.json"
    write_receipt(tmp_path, payload, candidate_bindings=bindings)
    errors = validator._verify_sheet_delivery_receipt_for_handoff(payload)
    assert any("candidate_bindings" in error or "provenance" in error for error in errors)


def test_sheet_receipt_is_bound_to_current_exporter_source(tmp_path):
    validator = load(VALIDATOR, "sheet_gate_source_v2")
    payload = handoff()
    write_receipt(tmp_path, payload, exporter_source_sha256="0" * 64)
    errors = validator._verify_sheet_delivery_receipt_for_handoff(payload)
    assert any("exporter" in error for error in errors)
