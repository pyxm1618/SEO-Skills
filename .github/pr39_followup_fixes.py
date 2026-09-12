from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(rel, old, new):
    path = ROOT / rel
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{rel}: expected one target, found {count}: {old[:100]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


# google_trends_collector is also imported by evidence_binding via a direct file
# location, where Python does not automatically add runtime/collectors to sys.path.
# Make the sibling reuse explicit so the registered issuer is loadable from both
# CLI and validator call paths.
replace_once(
    "runtime/collectors/google_trends_collector.py",
    "from urllib.parse import parse_qs, quote_plus, unquote, urlparse\n\nimport google_live_collector as base\n",
    "from urllib.parse import parse_qs, quote_plus, unquote, urlparse\n\nCOLLECTOR_DIR = Path(__file__).resolve().parent\nif str(COLLECTOR_DIR) not in sys.path:\n    sys.path.insert(0, str(COLLECTOR_DIR))\n\nimport google_live_collector as base\n",
)

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

# Keep the canonical Skill and data contracts synchronized with the executable
# boundary conditions fixed in this change.
replace_once(
    "skills/emerging-keyword-monitor/SKILL.md",
    "`max_total_candidates` is the hard run-scope cap. It covers current discovery, recursive expansion, supplemental candidates, carry-forward records, and overflow bookkeeping. Retry budgets are separate and explicitly bounded.\n",
    "`max_total_candidates` is the hard **collection-admission** cap across current discovery, recursive expansion, supplemental candidates, and carry-forward records. Candidates beyond the cap remain in the ledger as `not_attempted / batch_candidate_limit`, but they must not execute collector requests or become delivery-eligible. Overflow bookkeeping never expands the collection budget. Retry budgets are separate and explicitly bounded.\n",
)
replace_once(
    "skills/emerging-keyword-monitor/SKILL.md",
    "The same domain gate applies to Rising discovery, supplemental sources, and carry-forward records. Carry-forward is never a bypass around current domain qualification.\n",
    "The same domain gate applies to Rising discovery, supplemental sources, and carry-forward records. Carry-forward is never a bypass around current domain qualification. Preserve the historical `parent_anchor`/domain evidence used for qualification; a carried keyword may never use itself as substitute parent evidence. If that evidence is absent, keep the relation `unknown` for review rather than self-proving `in_scope`.\n",
)
replace_once(
    "skills/emerging-keyword-monitor/SKILL.md",
    "- a verified response with no timeline data is `valid_no_data`, distinct from `payload_not_observed` and browser/transport failure.\n",
    "- only a response whose required evidence is fully verified may become `valid_no_data / verified_no_data`; a screenshot or other required-evidence failure remains `pending_evidence` and blocks production classification/delivery instead of being promoted to verified no-data;\n- a verified response with no timeline data is `valid_no_data`, distinct from `payload_not_observed` and browser/transport failure.\n",
)
replace_once(
    "skills/emerging-keyword-monitor/SKILL.md",
    "The established receipt schema remains `seo-emerging-pipeline/v1`; candidate-ledger and reconciliation fields are backward-compatible additions. When a candidate ledger is supplied, the receipt attests the complete identity sets for all candidates in scope, candidates actually classified, candidates routed, and candidates eligible for delivery.\n",
    "The established receipt schema remains `seo-emerging-pipeline/v1`; candidate-ledger and reconciliation fields are backward-compatible additions. The receipt binds the candidate-ledger path/hash and the complete identity sets for candidates in scope, candidates actually classified, candidates routed, and candidates eligible for delivery. Canonical replay and the Hook must consume that same ledger-qualified set and recompute reconciliation; an explicit empty `delivery_ids=[]` remains empty and must never fall back to all classified candidates.\n",
)
replace_once(
    "skills/emerging-keyword-monitor/SKILL.md",
    "A current acquisition failure cannot erase or downgrade a prior confirmed status/evidence. Failed acquisition retries are bounded; after the retry budget they move to paused review, not automatically to `noise`, `out_of_scope`, or deletion. Domain `not_applicable`/review states are not counted as browser acquisition failures.\n",
    "A current acquisition failure cannot erase or downgrade a prior confirmed status/evidence. Failed acquisition retries are bounded; after the retry budget they move to paused review, not automatically to `noise`, `out_of_scope`, or deletion. `next_review_at` and `paused_review` are enforced at the single request-admission boundary for carry-forward and rediscovered candidates alike; rediscovery does not silently reset the retry clock or reactivate a paused record. Domain `not_applicable`/review states are not counted as browser acquisition failures.\n",
)
replace_once(
    "skills/emerging-keyword-monitor/SKILL.md",
    "- `BLOCKED` run => **zero production Sheet reads/writes**.\n- Delivery list is not the monitoring database. Only explicit `delivery_eligible=true` records from the current run may be delivered when eligibility metadata is present.\n",
    "- Production Sheet mutation is fail-closed: only an explicit `run_status=PASS` may proceed. `BLOCKED`, missing, or unknown run status => **zero production Sheet reads/writes**. Historical/legacy databases may be inspected in dry-run mode only.\n- Delivery list is not the monitoring database. Production delivery requires an explicit `delivery_eligible` decision on every record, and only records with `delivery_eligible=true` may be delivered; missing eligibility never falls back to full-database delivery.\n",
)

replace_once(
    "skills/emerging-keyword-monitor/references/data-contracts.md",
    "The receipt records all four identity sets plus an identity digest. A mismatch is a run error.\n",
    "The receipt records all four identity sets plus an identity digest and binds the candidate-ledger path/hash. Canonical replay and the Hook consume that same ledger-qualified set and recompute reconciliation. An explicit empty delivery set remains empty. Any mismatch is a run error.\n",
)
replace_once(
    "skills/emerging-keyword-monitor/references/data-contracts.md",
    "The same gate applies to Rising discovery, supplemental discovery, and carry-forward.\n",
    "The same gate applies to Rising discovery, supplemental discovery, and carry-forward. Carry-forward preserves its original `parent_anchor`/domain evidence; missing evidence remains `unknown` and the keyword itself is never substituted as parent proof.\n",
)
replace_once(
    "skills/emerging-keyword-monitor/references/data-contracts.md",
    "A current acquisition failure must not overwrite a prior confirmed `status` or confirmed evidence. Repeated acquisition failure leads to bounded retry/review behavior, not automatic `noise`, `out_of_scope`, or deletion.\n",
    "A current acquisition failure must not overwrite a prior confirmed `status` or confirmed evidence. Repeated acquisition failure leads to bounded retry/review behavior, not automatic `noise`, `out_of_scope`, or deletion. Future `next_review_at` and `paused_review` are request-admission gates for both carry-forward and current rediscovery; neither state is bypassed merely because a source rediscovers the keyword.\n",
)
replace_once(
    "skills/emerging-keyword-monitor/references/data-contracts.md",
    "A `BLOCKED` run performs zero production Sheet reads/writes.\n\nMonitoring database membership is not delivery eligibility. When run-level eligibility metadata is present, only records with explicit `delivery_eligible=true` may be delivered.\n",
    "Production Sheet delivery is fail-closed: only explicit `run_status=PASS` is eligible. `BLOCKED`, missing, or unknown run status performs zero production Sheet reads/writes; legacy databases are dry-run inspection only.\n\nMonitoring database membership is not delivery eligibility. Production delivery requires explicit `delivery_eligible` on every record and delivers only records with `delivery_eligible=true`; missing eligibility never falls back to all records.\n",
)
replace_once(
    "skills/emerging-keyword-monitor/references/state-machine.md",
    "- cannot bypass current batch/retry limits;\n- retains prior confirmed state when current evidence acquisition fails.\n",
    "- cannot bypass current batch/retry limits, `next_review_at`, or `paused_review`;\n- preserves the historical parent/domain evidence used for re-qualification and never substitutes the keyword itself as parent proof;\n- remains `unknown` for review when that domain evidence is missing;\n- retains prior confirmed state when current evidence acquisition fails.\n",
)

print("PR39 follow-up transforms applied")
