#!/usr/bin/env python3
"""Bind observed SEO rows to evidence emitted by the real project collectors.

The production trust target is execution integrity for normal agent workflows:
collector identity, current source artifacts, hashes, and deterministic semantic
replay must all agree. This module intentionally does not claim cryptographic
separation from a malicious local principal that can rewrite repository files.
"""

import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
from urllib.parse import urlparse

SCHEMA = "seo-observed-evidence/v2"
ROOT = Path(__file__).resolve().parent
COLLECTOR_FILES = {
    "semrush_ideas": ROOT / "collectors" / "semrush_relay_collector.py",
    "semrush_exact": ROOT / "collectors" / "semrush_relay_collector.py",
    "google_autocomplete": ROOT / "collectors" / "google_live_collector.py",
    "google_intitle": ROOT / "collectors" / "google_live_collector.py",
    "google_serp": ROOT / "collectors" / "google_live_collector.py",
    "google_trends": ROOT / "collectors" / "google_live_collector.py",
    "google_trends_related": ROOT / "collectors" / "google_live_collector.py",
}
EXPECTED_COLLECTORS = {
    "semrush_ideas": "semrush_relay_collector",
    "semrush_exact": "semrush_relay_collector",
    "google_autocomplete": "google_live_collector",
    "google_intitle": "google_live_collector",
    "google_serp": "google_live_collector",
    "google_trends": "google_live_collector",
    "google_trends_related": "google_live_collector",
}
REQUIRED_ARTIFACT_ROLES = {
    "semrush_ideas": {"relay_raw_response", "current_network_capture"},
    "semrush_exact": {"relay_raw_response", "current_network_capture"},
    "google_autocomplete": {"screenshot", "structured_observation"},
    "google_intitle": {"screenshot", "structured_observation"},
    "google_serp": {"screenshot", "structured_observation"},
    "google_trends": {"temporal_payload", "screenshot"},
    "google_trends_related": {"related_payload", "screenshot"},
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


def _json_read(path, label):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceIntegrityError(f"{label} is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise EvidenceIntegrityError(f"{label} must be a JSON object")
    return value


def _load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _expected_collector_path(evidence_type):
    path = COLLECTOR_FILES.get(evidence_type)
    if path is None:
        raise EvidenceIntegrityError(f"unsupported evidence type: {evidence_type}")
    return path.resolve()


def _assert_real_collector_caller(evidence_type):
    """Keep ordinary agents on the project collector CLI instead of helper minting."""
    expected = _expected_collector_path(evidence_type)
    frame = inspect.currentframe()
    caller = frame.f_back.f_back if frame and frame.f_back else None
    caller_path = Path(caller.f_code.co_filename).resolve() if caller is not None else None
    caller_module = str(caller.f_globals.get("__name__") or "") if caller is not None else ""
    if caller_path != expected or caller_module != "__main__":
        raise EvidenceIntegrityError(
            f"production evidence receipts may only be written by direct CLI execution of {expected.name}; "
            f"caller={caller_path} module={caller_module or 'unknown'}"
        )
    return expected


def _same_path(left, right):
    try:
        return Path(str(left)).resolve() == Path(str(right)).resolve()
    except (TypeError, ValueError):
        return False


def _artifact_records(artifacts, evidence_type):
    records = []
    roles = []
    for artifact in artifacts:
        if not isinstance(artifact, dict) or not artifact.get("path") or not artifact.get("role"):
            raise EvidenceIntegrityError("collector evidence artifacts must declare path and role")
        artifact_path = Path(str(artifact["path"]))
        role = str(artifact["role"])
        if not artifact_path.is_file():
            raise EvidenceIntegrityError(f"evidence artifact missing: {artifact_path}")
        if role in roles:
            raise EvidenceIntegrityError(f"duplicate evidence artifact role: {role}")
        roles.append(role)
        records.append({"role": role, "path": str(artifact_path), "sha256": sha256_file(artifact_path)})
    required = REQUIRED_ARTIFACT_ROLES[evidence_type]
    actual = set(roles)
    if actual != required:
        raise EvidenceIntegrityError(
            f"collector artifact roles mismatch for {evidence_type}: required={sorted(required)} actual={sorted(actual)}"
        )
    return records


def _roles_to_paths(records, evidence_type):
    required = REQUIRED_ARTIFACT_ROLES[evidence_type]
    role_map = {}
    for item in records:
        if not isinstance(item, dict) or not item.get("path") or not item.get("sha256") or not item.get("role"):
            raise EvidenceIntegrityError("evidence receipt artifact record invalid")
        role = str(item["role"])
        if role in role_map:
            raise EvidenceIntegrityError(f"duplicate evidence artifact role: {role}")
        path = Path(str(item["path"]))
        if not path.is_file():
            raise EvidenceIntegrityError(f"evidence artifact missing: {path}")
        if sha256_file(path) != item["sha256"]:
            raise EvidenceIntegrityError(f"evidence artifact hash mismatch: {path}")
        role_map[role] = path
    if set(role_map) != required:
        raise EvidenceIntegrityError(
            f"collector artifact roles mismatch for {evidence_type}: required={sorted(required)} actual={sorted(role_map)}"
        )
    return role_map


def _host(value):
    text = str(value or "").strip()
    if not text:
        return ""
    parsed = urlparse(text if "://" in text else f"https://{text}")
    return (parsed.hostname or "").lower()


def _assert_png(path):
    if Path(path).read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
        raise EvidenceIntegrityError(f"Google screenshot artifact is not a PNG: {path}")


def _without_receipt(payload):
    value = dict(payload)
    value.pop("evidence_receipt_ref", None)
    return value


def _verify_semrush_semantics(evidence_type, normalized, role_paths):
    raw_path = role_paths["relay_raw_response"]
    capture_path = role_paths["current_network_capture"]
    raw = _json_read(raw_path, "Semrush raw relay evidence")
    mode = "ideas" if evidence_type == "semrush_ideas" else "exact"
    required = [
        "observed_at", "relay_origin", "request_method", "request_path", "capture_observed_at",
        "capture_evidence_ref", "mode", "metric_database", "response",
    ]
    missing = [field for field in required if raw.get(field) in (None, "")]
    if missing:
        raise EvidenceIntegrityError(f"Semrush raw evidence missing fields: {', '.join(missing)}")
    if raw.get("mode") != mode:
        raise EvidenceIntegrityError("Semrush raw evidence mode mismatch")
    if _host(raw.get("relay_origin")) != "sem.3ue.com":
        raise EvidenceIntegrityError("Semrush raw evidence relay origin mismatch")
    if not _same_path(raw.get("capture_evidence_ref"), capture_path):
        raise EvidenceIntegrityError("Semrush raw evidence is not bound to the receipt network capture")
    identity_field = "seed" if mode == "ideas" else "keyword"
    if raw.get(identity_field) in (None, ""):
        raise EvidenceIntegrityError(f"Semrush raw evidence missing {identity_field}")
    descriptor = {
        "path": raw["request_path"],
        "method": raw["request_method"],
        "body": {},
        "capture_observed_at": raw["capture_observed_at"],
        "capture_evidence_ref": raw["capture_evidence_ref"],
        "mode": mode,
        "metric_database": raw["metric_database"],
        identity_field: raw[identity_field],
    }
    collector = _load_module(_expected_collector_path(evidence_type), f"evidence_replay_{mode}")
    try:
        replayed = collector._normalize(raw["response"], descriptor, str(raw["observed_at"]), str(raw_path))
    except Exception as exc:
        raise EvidenceIntegrityError(f"Semrush raw evidence cannot be deterministically normalized: {exc}") from exc
    if replayed != _without_receipt(normalized):
        raise EvidenceIntegrityError("Semrush normalized evidence differs from deterministic raw-response replay")


def _verify_google_semantics(evidence_type, normalized, role_paths):
    screenshot_path = role_paths["screenshot"]
    _assert_png(screenshot_path)
    if evidence_type == "google_trends_related":
        raw_path = role_paths["related_payload"]
        raw = _json_read(raw_path, "Google Trends related evidence")
        if _host(raw.get("source_url")) != "trends.google.com":
            raise EvidenceIntegrityError("Google Trends related source URL mismatch")
        collector = _load_module(_expected_collector_path(evidence_type), "evidence_replay_google_trends_related")
        try:
            replayed_rows = collector.parse_trends_related(raw.get("payload"))
        except Exception as exc:
            raise EvidenceIntegrityError(f"Google Trends related payload cannot be replayed: {exc}") from exc
        if replayed_rows != raw.get("related_queries") or replayed_rows != normalized.get("related_queries"):
            raise EvidenceIntegrityError("Google Trends related rows differ from payload replay")
        checks = {
            "anchor": raw.get("anchor"),
            "country": raw.get("country"),
            "timeframe": raw.get("timeframe"),
            "observed_at": raw.get("observed_at"),
            "source_url": raw.get("source_url"),
        }
        for field, expected in checks.items():
            if normalized.get(field) != expected:
                raise EvidenceIntegrityError(f"Google Trends related {field} differs from temporal evidence")
        if normalized.get("source") != "Google Trends" or normalized.get("source_type") != "google_trends_related":
            raise EvidenceIntegrityError("Google Trends related source label mismatch")
        if not _same_path(normalized.get("raw_evidence_ref"), raw_path):
            raise EvidenceIntegrityError("Google Trends related evidence ref mismatch")
        if not _same_path(normalized.get("screenshot_ref"), screenshot_path):
            raise EvidenceIntegrityError("Google Trends related screenshot ref mismatch")
        return
    if evidence_type == "google_trends":
        raw_path = role_paths["temporal_payload"]
        raw = _json_read(raw_path, "Google Trends temporal evidence")
        if _host(raw.get("source_url")) != "trends.google.com":
            raise EvidenceIntegrityError("Google Trends source URL mismatch")
        collector = _load_module(_expected_collector_path(evidence_type), "evidence_replay_google_trends")
        try:
            replayed_series = collector.parse_trends_timeline(raw.get("payload"))
        except Exception as exc:
            raise EvidenceIntegrityError(f"Google Trends temporal payload cannot be replayed: {exc}") from exc
        if replayed_series != raw.get("series") or replayed_series != normalized.get("google_trends_series"):
            raise EvidenceIntegrityError("Google Trends normalized series differs from temporal payload replay")
        checks = {
            "keyword": raw.get("keyword"),
            "google_trends_market": raw.get("market"),
            "google_trends_observed_at": raw.get("observed_at"),
        }
        for field, expected in checks.items():
            if normalized.get(field) != expected:
                raise EvidenceIntegrityError(f"Google Trends normalized {field} differs from temporal evidence")
        if normalized.get("google_trends_source") != "Google Trends":
            raise EvidenceIntegrityError("Google Trends source label mismatch")
        if not _same_path(normalized.get("google_trends_evidence_ref"), raw_path):
            raise EvidenceIntegrityError("Google Trends evidence ref mismatch")
        if not _same_path(normalized.get("google_trends_screenshot_ref"), screenshot_path):
            raise EvidenceIntegrityError("Google Trends screenshot ref mismatch")
        return

    observation_path = role_paths["structured_observation"]
    observation = _json_read(observation_path, "Google structured observation")
    if _host(observation.get("page_url")) not in {"google.com", "www.google.com"}:
        raise EvidenceIntegrityError("Google structured observation page URL mismatch")
    if not _same_path(normalized.get("evidence_ref"), screenshot_path):
        raise EvidenceIntegrityError("Google screenshot ref mismatch")
    if not _same_path(normalized.get("observation_ref"), observation_path):
        raise EvidenceIntegrityError("Google structured observation ref mismatch")

    if evidence_type == "google_autocomplete":
        fields = ["seed", "suggestions", "country", "language", "observed_at"]
        if normalized.get("source") != "google_autocomplete":
            raise EvidenceIntegrityError("Google autocomplete source mismatch")
    elif evidence_type == "google_intitle":
        fields = ["intitle_results", "market", "observed_at"]
        expected_query = f'intitle:"{normalized.get("keyword")}"'
        if observation.get("query") != expected_query:
            raise EvidenceIntegrityError("Google intitle query differs from normalized keyword")
        if normalized.get("source") != "Google":
            raise EvidenceIntegrityError("Google intitle source mismatch")
    elif evidence_type == "google_serp":
        fields = ["keyword", "market", "observed_at", "results"]
        if normalized.get("source") != "Google":
            raise EvidenceIntegrityError("Google SERP source mismatch")
    else:
        raise EvidenceIntegrityError(f"unsupported Google evidence type: {evidence_type}")
    for field in fields:
        if normalized.get(field) != observation.get(field):
            raise EvidenceIntegrityError(f"Google normalized {field} differs from structured observation")


def _verify_collector_semantics(evidence_type, normalized, role_paths):
    if evidence_type.startswith("semrush_"):
        _verify_semrush_semantics(evidence_type, normalized, role_paths)
    else:
        _verify_google_semantics(evidence_type, normalized, role_paths)


def write_observed_output(output_path, payload, collector, evidence_type, artifacts):
    if evidence_type not in EXPECTED_COLLECTORS:
        raise EvidenceIntegrityError(f"unsupported evidence type: {evidence_type}")
    if collector != EXPECTED_COLLECTORS[evidence_type]:
        raise EvidenceIntegrityError(f"wrong collector for {evidence_type}: {collector}")
    collector_path = _assert_real_collector_caller(evidence_type)

    output_path = Path(output_path)
    receipt_path = output_path.with_suffix(".receipt.json")
    bound = dict(payload)
    bound["evidence_receipt_ref"] = str(receipt_path)
    _json_write(output_path, bound)

    artifact_records = _artifact_records(artifacts, evidence_type)
    role_paths = {item["role"]: Path(item["path"]) for item in artifact_records}
    _verify_collector_semantics(evidence_type, bound, role_paths)

    receipt = {
        "schema": SCHEMA,
        "collector": collector,
        "collector_source_sha256": sha256_file(collector_path),
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
    receipt = _json_read(receipt_path, "evidence receipt")
    if receipt.get("schema") != SCHEMA:
        raise EvidenceIntegrityError("evidence receipt schema mismatch")
    if receipt.get("evidence_type") != expected_type:
        raise EvidenceIntegrityError("evidence receipt type mismatch")
    if receipt.get("collector") != EXPECTED_COLLECTORS[expected_type]:
        raise EvidenceIntegrityError("evidence receipt collector mismatch")
    collector_path = _expected_collector_path(expected_type)
    if receipt.get("collector_source_sha256") != sha256_file(collector_path):
        raise EvidenceIntegrityError("evidence receipt collector source hash mismatch")

    normalized_ref = Path(str(receipt.get("normalized_ref") or ""))
    if not normalized_ref.is_file():
        raise EvidenceIntegrityError("receipt normalized evidence file missing")
    if sha256_file(normalized_ref) != receipt.get("normalized_sha256"):
        raise EvidenceIntegrityError("normalized evidence hash mismatch")
    normalized = _json_read(normalized_ref, "normalized evidence")
    if normalized.get("evidence_receipt_ref") != str(receipt_path):
        raise EvidenceIntegrityError("normalized evidence is not bound to this receipt")

    artifacts = receipt.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise EvidenceIntegrityError("evidence receipt artifacts missing")
    role_paths = _roles_to_paths(artifacts, expected_type)
    _verify_collector_semantics(expected_type, normalized, role_paths)
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
    exact = verify_receipt_ref(
        payload.get("exact_evidence_receipt_ref") or payload.get("evidence_receipt_ref"), "semrush_exact"
    )
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
