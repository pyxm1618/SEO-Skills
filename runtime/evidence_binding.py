#!/usr/bin/env python3
"""Bind observed SEO rows to collector-written evidence artifacts.

This is an execution-integrity receipt, not an adversarial signature. Its job is
to stop normal workflow code from treating hand-written provenance strings as
verified observations.
"""

import hashlib
import json
from pathlib import Path

SCHEMA = "seo-observed-evidence/v1"
EXPECTED_COLLECTORS = {
    "semrush_ideas": "semrush_relay_collector",
    "semrush_exact": "semrush_relay_collector",
    "google_autocomplete": "google_live_collector",
    "google_intitle": "google_live_collector",
    "google_serp": "google_live_collector",
    "google_trends": "google_live_collector",
}


class EvidenceIntegrityError(ValueError):
    pass


def sha256_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _json_write(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_observed_output(output_path, payload, collector, evidence_type, artifacts):
    if evidence_type not in EXPECTED_COLLECTORS:
        raise EvidenceIntegrityError(f"unsupported evidence type: {evidence_type}")
    if collector != EXPECTED_COLLECTORS[evidence_type]:
        raise EvidenceIntegrityError(f"wrong collector for {evidence_type}: {collector}")

    output_path = Path(output_path)
    receipt_path = output_path.with_suffix(".receipt.json")
    bound = dict(payload)
    bound["evidence_receipt_ref"] = str(receipt_path)
    _json_write(output_path, bound)

    artifact_records = []
    for artifact in artifacts:
        if isinstance(artifact, dict):
            artifact_path = Path(artifact["path"])
            role = str(artifact.get("role") or "evidence")
        else:
            artifact_path = Path(artifact)
            role = "evidence"
        if not artifact_path.exists():
            raise EvidenceIntegrityError(f"evidence artifact missing: {artifact_path}")
        artifact_records.append({
            "role": role,
            "path": str(artifact_path),
            "sha256": sha256_file(artifact_path),
        })
    if not artifact_records:
        raise EvidenceIntegrityError("at least one evidence artifact is required")

    receipt = {
        "schema": SCHEMA,
        "collector": collector,
        "evidence_type": evidence_type,
        "normalized_ref": str(output_path),
        "normalized_sha256": sha256_file(output_path),
        "artifacts": artifact_records,
    }
    _json_write(receipt_path, receipt)
    return bound


def verify_receipt_ref(receipt_ref, expected_type):
    if expected_type not in EXPECTED_COLLECTORS:
        raise EvidenceIntegrityError(f"unsupported evidence type: {expected_type}")
    ref = str(receipt_ref or "").strip()
    if not ref:
        raise EvidenceIntegrityError("evidence receipt is required")
    receipt_path = Path(ref)
    if not receipt_path.is_file():
        raise EvidenceIntegrityError(f"evidence receipt missing: {receipt_path}")
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceIntegrityError(f"evidence receipt invalid: {exc}") from exc
    if receipt.get("schema") != SCHEMA:
        raise EvidenceIntegrityError("evidence receipt schema mismatch")
    if receipt.get("evidence_type") != expected_type:
        raise EvidenceIntegrityError("evidence receipt type mismatch")
    if receipt.get("collector") != EXPECTED_COLLECTORS[expected_type]:
        raise EvidenceIntegrityError("evidence receipt collector mismatch")

    normalized_ref = Path(str(receipt.get("normalized_ref") or ""))
    if not normalized_ref.is_file():
        raise EvidenceIntegrityError("receipt normalized evidence file missing")
    if sha256_file(normalized_ref) != receipt.get("normalized_sha256"):
        raise EvidenceIntegrityError("normalized evidence hash mismatch")
    try:
        normalized = json.loads(normalized_ref.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceIntegrityError(f"normalized evidence invalid: {exc}") from exc
    if normalized.get("evidence_receipt_ref") != str(receipt_path):
        raise EvidenceIntegrityError("normalized evidence is not bound to this receipt")

    artifacts = receipt.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise EvidenceIntegrityError("evidence receipt artifacts missing")
    for item in artifacts:
        if not isinstance(item, dict) or not item.get("path") or not item.get("sha256"):
            raise EvidenceIntegrityError("evidence receipt artifact record invalid")
        artifact_path = Path(str(item["path"]))
        if not artifact_path.is_file():
            raise EvidenceIntegrityError(f"evidence artifact missing: {artifact_path}")
        if sha256_file(artifact_path) != item["sha256"]:
            raise EvidenceIntegrityError(f"evidence artifact hash mismatch: {artifact_path}")
    return normalized


def verify_payload(payload, expected_type):
    if not isinstance(payload, dict):
        raise EvidenceIntegrityError("observed payload must be an object")
    normalized = verify_receipt_ref(payload.get("evidence_receipt_ref"), expected_type)
    if normalized != payload:
        raise EvidenceIntegrityError("observed payload differs from collector-bound normalized evidence")
    return normalized


def _norm_keyword(value):
    return " ".join(str(value or "").split()).casefold()


def _norm_market(value):
    text = str(value or "").strip().casefold()
    return {"united states": "us", "usa": "us", "us": "us"}.get(text, text)


def _num(value):
    try:
        number = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def verify_kgr_payload(payload):
    if not isinstance(payload, dict):
        raise EvidenceIntegrityError("KGR payload must be an object")
    exact = verify_receipt_ref(payload.get("exact_evidence_receipt_ref") or payload.get("evidence_receipt_ref"), "semrush_exact")
    intitle = verify_receipt_ref(payload.get("intitle_evidence_receipt_ref"), "google_intitle")
    if _norm_keyword(exact.get("keyword")) != _norm_keyword(payload.get("keyword")):
        raise EvidenceIntegrityError("KGR exact keyword differs from collector evidence")
    if _norm_keyword(intitle.get("keyword")) != _norm_keyword(payload.get("keyword")):
        raise EvidenceIntegrityError("KGR intitle keyword differs from collector evidence")
    if _num(exact.get("volume")) != _num(payload.get("volume")):
        raise EvidenceIntegrityError("KGR volume differs from exact collector evidence")
    if _num(intitle.get("intitle_results")) != _num(payload.get("intitle_results")):
        raise EvidenceIntegrityError("KGR intitle count differs from Google collector evidence")
    if _norm_market(exact.get("metric_database")) != _norm_market(payload.get("metric_database")):
        raise EvidenceIntegrityError("KGR exact market differs from collector evidence")
    if _norm_market(intitle.get("market")) != _norm_market(payload.get("market")):
        raise EvidenceIntegrityError("KGR intitle market differs from collector evidence")
    if str(exact.get("observed_at") or "") != str(payload.get("exact_observed_at") or ""):
        raise EvidenceIntegrityError("KGR exact timestamp differs from collector evidence")
    if str(intitle.get("observed_at") or "") != str(payload.get("intitle_observed_at") or ""):
        raise EvidenceIntegrityError("KGR intitle timestamp differs from collector evidence")
    if str(exact.get("provenance_ref") or "") != str(payload.get("exact_provenance_ref") or ""):
        raise EvidenceIntegrityError("KGR exact provenance differs from collector evidence")
    if str(intitle.get("evidence_ref") or "") != str(payload.get("intitle_provenance_ref") or ""):
        raise EvidenceIntegrityError("KGR intitle provenance differs from collector evidence")
    return True
