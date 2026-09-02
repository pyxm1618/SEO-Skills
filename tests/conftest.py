"""Repository test fixtures.

The large legacy Discovery coverage suite predates mandatory Google SERP
expansion checks and mandatory Sheet delivery. Keep those regression tests
running unchanged while upgrading only their shared success fixtures to the new
contract. New expansion tests do not use this adapter, so missing expansion
checks still fail closed there and in production.
"""

import hashlib
import importlib.util
import json
from pathlib import Path
from urllib.parse import quote_plus

import pytest


ROOT = Path(__file__).resolve().parents[1]
EXPORTER = ROOT / "skills" / "seo-keyword-discovery" / "scripts" / "export_to_sheet.py"


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _norm(value):
    return " ".join(str(value or "").split()).casefold()


def _png_bytes():
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
        b"\x00\x00\x00\x0aIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )


def _write_zero_expansion_receipt(module, tmp_path, seed, name):
    """Create collector-shaped zero-result evidence for production test replay."""
    safe = "-".join(str(name).split())
    screenshot = tmp_path / f"{safe}.png"
    screenshot.write_bytes(_png_bytes())
    observed_at = "2026-09-02T10:00:00+00:00"
    observation = tmp_path / f"{safe}.observation.json"
    observation.write_text(
        json.dumps(
            {
                "page_url": f"https://www.google.com/search?q={quote_plus(seed)}",
                "seed": seed,
                "people_also_ask": [],
                "related_searches": [],
                "expansion_count": 0,
                "result_status": "not_present",
                "market": "US",
                "language": "en",
                "observed_at": observed_at,
            }
        ),
        encoding="utf-8",
    )
    normalized = tmp_path / f"{safe}.json"
    receipt = tmp_path / f"{safe}.receipt.json"
    normalized.write_text(
        json.dumps(
            {
                "seed": seed,
                "people_also_ask": [],
                "related_searches": [],
                "expansion_count": 0,
                "result_status": "not_present",
                "market": "US",
                "language": "en",
                "observed_at": observed_at,
                "source": "google_serp_expansions",
                "evidence_ref": str(screenshot),
                "observation_ref": str(observation),
                "evidence_receipt_ref": str(receipt),
            }
        ),
        encoding="utf-8",
    )
    receipt.write_text(
        json.dumps(
            {
                "schema": "seo-observed-evidence/v2",
                "collector": "google_live_collector",
                "collector_source_sha256": hashlib.sha256(module.GOOGLE_COLLECTOR.read_bytes()).hexdigest(),
                "evidence_type": "google_serp_expansions",
                "normalized_ref": str(normalized),
                "normalized_sha256": hashlib.sha256(normalized.read_bytes()).hexdigest(),
                "artifacts": [
                    {
                        "role": "screenshot",
                        "path": str(screenshot),
                        "sha256": hashlib.sha256(screenshot.read_bytes()).hexdigest(),
                    },
                    {
                        "role": "structured_observation",
                        "path": str(observation),
                        "sha256": hashlib.sha256(observation.read_bytes()).hexdigest(),
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return receipt


def _ensure_manifest_expansions(module, tmp_path, manifest):
    receipts = manifest.get("source_receipts")
    if not isinstance(receipts, list):
        return
    inventory = manifest.get("candidate_inventory")
    row_ledger = inventory.get("row_ledger") if isinstance(inventory, dict) else None
    seeds = manifest.get("seed_plan", {}).get("seeds", [])
    for index, seed in enumerate(seeds):
        existing = next(
            (
                record
                for record in receipts
                if isinstance(record, dict)
                and record.get("evidence_type") == "google_serp_expansions"
                and _norm(record.get("seed")) == _norm(seed)
            ),
            None,
        )
        if existing is not None:
            continue
        receipt = _write_zero_expansion_receipt(
            module, tmp_path, seed, f"root-expansion-{index}-{seed}"
        )
        receipts.append(
            {
                "evidence_type": "google_serp_expansions",
                "seed": seed,
                "evidence_receipt_ref": str(receipt),
            }
        )
        if isinstance(row_ledger, list):
            row_ledger.append({"evidence_receipt_ref": str(receipt), "rows": []})


def _upgrade_coverage_ledger(module, ledger, base_path):
    base_path = Path(base_path)
    upstream = ledger.get("upstream_input") if isinstance(ledger, dict) else None
    receipts = upstream.get("source_receipts") if isinstance(upstream, dict) else []
    root_refs = {
        _norm(record.get("seed")): str(record.get("evidence_receipt_ref"))
        for record in receipts
        if isinstance(record, dict) and record.get("evidence_type") == "google_serp_expansions"
    }

    for seed_record in ledger.get("required_seeds", []):
        if not isinstance(seed_record, dict):
            continue
        seed = seed_record.get("seed")
        ref = root_refs.get(_norm(seed))
        if ref:
            seed_record["expansions"] = {"status": "PASS", "evidence_receipt_ref": ref}

    branch_ledger = ledger.get("branch_row_ledger")
    if not isinstance(branch_ledger, list):
        branch_ledger = []
        ledger["branch_row_ledger"] = branch_ledger
    for index, branch in enumerate(ledger.get("required_branch_seeds", [])):
        if not isinstance(branch, dict):
            continue
        seed = str(branch.get("branch_seed") or "")
        if not seed:
            continue
        current = branch.get("expansions") if isinstance(branch.get("expansions"), dict) else None
        current_ref = str(current.get("evidence_receipt_ref") or "") if current else ""
        if current and current.get("status") == "PASS" and current_ref and Path(current_ref).is_file():
            receipt = Path(current_ref)
        else:
            receipt = _write_zero_expansion_receipt(
                module, base_path, seed, f"branch-expansion-{index}-{seed}"
            )
            branch["expansions"] = {"status": "PASS", "evidence_receipt_ref": str(receipt)}
        if not any(
            isinstance(record, dict) and record.get("evidence_receipt_ref") == str(receipt)
            for record in branch_ledger
        ):
            branch_ledger.append({"evidence_receipt_ref": str(receipt), "rows": []})
    return ledger


def _upgrade_coverage_input(module, input_path):
    path = Path(input_path)
    ledger = json.loads(path.read_text(encoding="utf-8"))
    _upgrade_coverage_ledger(module, ledger, path.parent)
    path.write_text(json.dumps(ledger), encoding="utf-8")


def _decorate_handoff_with_sheet_receipt(input_path):
    path = Path(input_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("sheet_delivery_receipt_ref"):
        return
    exporter = _load(EXPORTER, "legacy_coverage_sheet_fixture_exporter")
    keywords = payload.get("keywords")
    count = len(keywords) if isinstance(keywords, list) else 0
    receipt_path = path.with_name(path.stem + ".sheet-delivery.receipt.json")
    receipt_path.write_text(
        json.dumps(
            {
                "schema": "seo-discovery-sheet-delivery/v1",
                "status": "PASS",
                "batch_id": payload.get("batch_id"),
                "worksheet": "keyword_discovery",
                "sheet_id": "test-sheet",
                "record_count": count,
                "verified_count": count,
                "handoff_binding_sha256": exporter.handoff_binding_sha256(payload),
                "exporter_source_sha256": hashlib.sha256(EXPORTER.read_bytes()).hexdigest(),
                "verified_at": "2026-09-02T10:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    payload["sheet_delivery_receipt_ref"] = str(receipt_path)
    path.write_text(json.dumps(payload), encoding="utf-8")


@pytest.fixture(autouse=True)
def _upgrade_legacy_discovery_coverage_fixtures(request, monkeypatch):
    """Adapt only the pre-v2 Discovery coverage regression module."""
    module = request.module
    module_path = Path(getattr(module, "__file__", ""))
    if module_path.name != "test_discovery_coverage.py":
        return

    original_required_seed = module._required_seed
    original_branch = module._branch
    original_full_ledger = module.full_ledger
    original_write_manifest = module._write_input_manifest_receipt
    original_run_stage = module._run_production_stage
    original_load_module = module.load_module

    def required_seed(seed, autocomplete="PASS", semrush="PASS"):
        item = original_required_seed(seed, autocomplete=autocomplete, semrush=semrush)
        item["expansions"] = module._source_status(
            "PASS", module._receipt_ref(seed, "google_serp_expansions")
        )
        return item

    def branch(
        branch_seed,
        candidate_id,
        parent_seed="wedding calculator",
        depth=1,
        autocomplete="PASS",
        semrush="PASS",
    ):
        item = original_branch(
            branch_seed,
            candidate_id,
            parent_seed=parent_seed,
            depth=depth,
            autocomplete=autocomplete,
            semrush=semrush,
        )
        item["expansions"] = module._source_status(
            "PASS", f"evidence/{candidate_id}-expansions.receipt.json"
        )
        return item

    monkeypatch.setattr(module, "_required_seed", required_seed)
    monkeypatch.setattr(module, "_branch", branch)

    def full_ledger():
        ledger = original_full_ledger()
        receipts = ledger.get("upstream_input", {}).get("source_receipts", [])
        for seed_record in ledger.get("required_seeds", []):
            seed = seed_record.get("seed")
            ref = module._receipt_ref(seed, "google_serp_expansions")
            if not any(
                isinstance(record, dict)
                and record.get("evidence_type") == "google_serp_expansions"
                and _norm(record.get("seed")) == _norm(seed)
                for record in receipts
            ):
                receipts.append(
                    {
                        "evidence_type": "google_serp_expansions",
                        "seed": seed,
                        "evidence_receipt_ref": ref,
                    }
                )
        return ledger

    monkeypatch.setattr(module, "full_ledger", full_ledger)

    def write_input_manifest_receipt(tmp_path, manifest):
        _ensure_manifest_expansions(module, tmp_path, manifest)
        return original_write_manifest(tmp_path, manifest)

    monkeypatch.setattr(module, "_write_input_manifest_receipt", write_input_manifest_receipt)

    def run_production_stage(stage, input_path, report_path):
        if stage == "discovery_coverage":
            _upgrade_coverage_input(module, input_path)
        elif stage == "discovery_handoff":
            _decorate_handoff_with_sheet_receipt(input_path)
        return original_run_stage(stage, input_path, report_path)

    monkeypatch.setattr(module, "_run_production_stage", run_production_stage)

    # One legacy branch regression invokes the production coverage validator
    # directly before writing its ledger to disk. Adapt that in-memory success
    # fixture with the same evidence used by the file-based production path.
    if request.node.name == "test_production_branch_keywords_reach_the_handoff":
        tmp_path = request.getfixturevalue("tmp_path")

        def load_module(name, path):
            loaded = original_load_module(name, path)
            if Path(path) == Path(module.COVERAGE):
                original_validate = loaded.validate_coverage

                def validate_coverage(ledger, production=False):
                    if production and isinstance(ledger, dict):
                        _upgrade_coverage_ledger(module, ledger, tmp_path)
                    return original_validate(ledger, production=production)

                loaded.validate_coverage = validate_coverage
            return loaded

        monkeypatch.setattr(module, "load_module", load_module)
