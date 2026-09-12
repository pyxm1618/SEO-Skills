from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(rel, old, new):
    path = ROOT / rel
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{rel}: expected one target, found {count}: {old[:100]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


# Canonical standalone execution still needs a signed ledger. When the caller did
# not supply one, materialize the canonical classified identity set as an internal
# ledger and bind its hash into the receipt. External runner ledgers remain authoritative.
replace_once(
    "runtime/emerging_pipeline.py",
    '''    if candidate_ledger is None:\n        candidate_ledger = [\n            {"candidate_id": _candidate_id(row), "keyword": row.get("keyword"), "final_disposition": "classified"}\n            for row in classified_rows\n        ]\n        delivery_ids = None\n    else:\n''',
    '''    if candidate_ledger is None:\n        candidate_ledger = [\n            {\n                "candidate_id": _candidate_id(row),\n                "keyword": row.get("keyword"),\n                "domain_relation": "in_scope",\n                "acquisition_status": "data_acquired",\n                "verification_status": "verified",\n                "delivery_eligible": True,\n                "final_disposition": "classified",\n            }\n            for row in classified_rows\n        ]\n        internal_ledger_path = output_dir / "candidate-ledger.json"\n        if internal_ledger_path.exists():\n            raise FileExistsError(f"Emerging pipeline output already exists: {internal_ledger_path}")\n        internal_ledger_path.write_text(\n            json.dumps(candidate_ledger, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8"\n        )\n        ledger_ref = {"path": str(internal_ledger_path.resolve()), "sha256": _sha256(internal_ledger_path)}\n        delivery_ids = [_candidate_id(row) for row in candidate_ledger]\n        delivery_ids = [value for value in delivery_ids if value is not None]\n    else:\n''',
)

# Existing exporter unit fixtures represent valid production input. Make the new
# fail-closed prerequisites explicit rather than weakening production code.
replace_once(
    "skills/emerging-keyword-monitor/tests/test_export_to_sheet.py",
    '    payload = {"schema_version": 1, "records": records}\n',
    '    payload = {"schema_version": 1, "run_status": "PASS", "records": records}\n',
)
replace_once(
    "skills/emerging-keyword-monitor/tests/test_export_to_sheet.py",
    '        "signal_type": "net_new",\n',
    '        "signal_type": "net_new",\n        "delivery_eligible": True,\n',
)
replace_once(
    "skills/emerging-keyword-monitor/tests/test_export_to_sheet.py",
    '            database([{"domain": "wedding", "keyword": "  "}], market="US", language="en"),\n',
    '            database([{"domain": "wedding", "keyword": "  ", "delivery_eligible": True}], market="US", language="en"),\n',
)

# Evidence fixtures must name the dedicated Trends collector that now owns issuance.
replace_once(
    "tests/test_observed_evidence_binding.py",
    '        "collector": "google_live_collector",\n        "collector_source_sha256": hashlib.sha256((ROOT / "runtime" / "collectors" / "google_live_collector.py").read_bytes()).hexdigest(),\n        "evidence_type": "google_trends",\n',
    '        "collector": "google_trends_collector",\n        "collector_source_sha256": hashlib.sha256((ROOT / "runtime" / "collectors" / "google_trends_collector.py").read_bytes()).hexdigest(),\n        "evidence_type": "google_trends",\n',
)

# A legacy carry-forward row with no parent/domain evidence may no longer prove
# itself in-scope. Update the old regression to assert the new fail-closed contract.
replace_once(
    "tests/test_review_r1_r6_regressions.py",
    "def test_r3_radar_carries_watching_database_records_into_next_timeline_run():\n",
    "def test_r3_radar_carry_forward_without_domain_evidence_stays_pending_review():\n",
)
replace_once(
    "tests/test_review_r1_r6_regressions.py",
    '''    assert calls == [("legacy topic", "today 3-m")]\n    assert result["candidate_counts"]["classified"] == 1\n    assert result["candidates"][0]["previous_status"] == "watch"\n''',
    '''    assert calls == []\n    row = next(item for item in result["candidate_ledger"] if item["keyword"] == "legacy topic")\n    assert row["domain_relation"] == "unknown"\n    assert row["acquisition_status"] == "not_applicable"\n    assert row["final_disposition"] == "pending_domain_review"\n    assert row["previous_status"] == "watch"\n''',
)

print("PR39 follow-up transforms applied")
