from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def write(rel, text):
    (ROOT / rel).write_text(text, encoding="utf-8")


def replace_once(rel, old, new):
    text = read(rel)
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{rel}: expected exactly one replacement target, found {count}: {old[:80]!r}")
    write(rel, text.replace(old, new, 1))


def replace_between(rel, start, end, replacement):
    text = read(rel)
    i = text.find(start)
    if i < 0:
        raise RuntimeError(f"{rel}: start marker missing: {start!r}")
    j = text.find(end, i + len(start))
    if j < 0:
        raise RuntimeError(f"{rel}: end marker missing: {end!r}")
    if text.find(start, i + len(start)) >= 0:
        raise RuntimeError(f"{rel}: start marker is not unique: {start!r}")
    write(rel, text[:i] + replacement + text[j:])


# R1: bind to the real Google Trends widget request structure without weakening keyword/market/window checks.
rel = "runtime/collectors/google_trends_collector.py"
replace_once(
    rel,
    "import argparse\nimport json\nimport os\nimport sys\nfrom pathlib import Path\nfrom typing import Any\n",
    "import argparse\nimport calendar\nimport json\nimport os\nimport re\nimport sys\nfrom datetime import datetime\nfrom pathlib import Path\nfrom typing import Any\n",
)
replace_between(
    rel,
    "def _timeline_request_matches(",
    "def trends_response_matches_request(",
    '''def _geo_country(value: Any) -> str:\n    if isinstance(value, dict):\n        value = value.get("country") or value.get("countryCode")\n    return str(value or "").strip().upper()\n\n\ndef _keyword_values(container: Any) -> set[str]:\n    if not isinstance(container, dict):\n        return set()\n    restriction = container.get("complexKeywordsRestriction")\n    rows = restriction.get("keyword") if isinstance(restriction, dict) else None\n    values: set[str] = set()\n    for row in rows if isinstance(rows, list) else []:\n        if isinstance(row, dict):\n            value = row.get("value") or row.get("keyword")\n        else:\n            value = row\n        if value not in (None, ""):\n            values.add(_canonical(value))\n    legacy = container.get("keyword")\n    if legacy not in (None, ""):\n        values.add(_canonical(legacy))\n    return values\n\n\ndef _subtract_months(value: datetime, months: int) -> datetime:\n    total = value.year * 12 + value.month - 1 - months\n    year, month0 = divmod(total, 12)\n    month = month0 + 1\n    day = min(value.day, calendar.monthrange(year, month)[1])\n    return value.replace(year=year, month=month, day=day)\n\n\ndef _timeframe_matches(actual: Any, requested: str) -> bool:\n    if _canonical(actual) == _canonical(requested):\n        return True\n    match = re.fullmatch(r"(?:today|now)\\s+(\\d+)-(d|m|y)", _canonical(requested))\n    range_match = re.fullmatch(r"(\\d{4}-\\d{2}-\\d{2})\\s+(\\d{4}-\\d{2}-\\d{2})", str(actual or "").strip())\n    if not match or not range_match:\n        return False\n    start = datetime.fromisoformat(range_match.group(1))\n    end = datetime.fromisoformat(range_match.group(2))\n    count = int(match.group(1))\n    unit = match.group(2)\n    if unit == "d":\n        return abs((end - start).days - count) <= 1\n    if unit == "m":\n        expected_start = _subtract_months(end, count)\n    else:\n        try:\n            expected_start = end.replace(year=end.year - count)\n        except ValueError:\n            expected_start = end.replace(year=end.year - count, day=28)\n    return abs((start - expected_start).days) <= 1\n\n\ndef _timeline_request_matches(payload: dict[str, Any], keyword: str, market: str, timeframe: str) -> bool:\n    items = payload.get("comparisonItem")\n    if not isinstance(items, list):\n        return False\n    payload_time = payload.get("time")\n    if payload_time not in (None, "") and not _timeframe_matches(payload_time, timeframe):\n        return False\n    for item in items:\n        if not isinstance(item, dict):\n            continue\n        item_time = item.get("time") if item.get("time") not in (None, "") else payload_time\n        if _canonical(keyword) not in _keyword_values(item):\n            continue\n        if _geo_country(item.get("geo")) != _geo_country(market):\n            continue\n        if item_time in (None, "") or not _timeframe_matches(item_time, timeframe):\n            continue\n        return True\n    return False\n\n\ndef _related_request_matches(payload: dict[str, Any], keyword: str, market: str, timeframe: str) -> bool:\n    restriction = payload.get("restriction")\n    if not isinstance(restriction, dict):\n        return False\n    time_values = [restriction.get("originalTimeRangeForExploreUrl"), restriction.get("time")]\n    return (\n        _geo_country(restriction.get("geo")) == _geo_country(market)\n        and any(_timeframe_matches(value, timeframe) for value in time_values if value not in (None, ""))\n        and _canonical(keyword) in _keyword_values(restriction)\n    )\n\n\n''',
)

# R2: the dedicated collector must be the registered production issuer and source path.
rel = "runtime/evidence_binding.py"
replace_once(rel, '"google_trends": ROOT / "collectors" / "google_live_collector.py",', '"google_trends": ROOT / "collectors" / "google_trends_collector.py",')
replace_once(rel, '"google_trends_related": ROOT / "collectors" / "google_live_collector.py",', '"google_trends_related": ROOT / "collectors" / "google_trends_collector.py",')
replace_once(rel, '"google_trends": "google_live_collector",', '"google_trends": "google_trends_collector",')
replace_once(rel, '"google_trends_related": "google_live_collector",', '"google_trends_related": "google_trends_collector",')

# R4/R8: preserve historical domain evidence and workflow controls in carry-forward rows.
rel = "skills/emerging-keyword-monitor/scripts/update_emerging_database.py"
replace_once(rel, '        if record.get("monitoring_state") == "paused_review":\n            continue\n', '')
replace_once(
    rel,
    '                "next_review_at": record.get("next_review_at"),\n',
    '                "next_review_at": record.get("next_review_at"),\n'
    '                "monitoring_state": record.get("monitoring_state"),\n'
    '                "parent_anchor": record.get("parent_anchor"),\n'
    '                "domain_relation": record.get("domain_relation"),\n'
    '                "domain_relation_reason": record.get("domain_relation_reason"),\n'
    '                "root_relation": record.get("root_relation"),\n'
    '                "root_candidate_hypothesis": record.get("root_candidate_hypothesis"),\n',
)

# R3/R4/R7/R8: one request-admission boundary controls batch limits, domain evidence, evidence readiness and historical workflow state.
rel = "skills/emerging-keyword-monitor/scripts/run_emerging_radar.py"
replace_between(
    rel,
    "def _requalify_carry_forward(",
    "def _merge_candidate_pool(",
    '''def _requalify_carry_forward(\n    domain: str,\n    carried: dict[str, Any],\n    relation_gate: Callable[[str, str, str], Any] | None,\n) -> dict[str, Any]:\n    keyword = " ".join(str(carried.get("keyword") or "").split())\n    parent = " ".join(str(carried.get("parent_anchor") or "").split())\n    if parent:\n        relation, reason = _relation(relation_gate, domain, keyword, parent)\n    else:\n        prior_relation = str(carried.get("domain_relation") or "").strip()\n        prior_reason = str(carried.get("domain_relation_reason") or "").strip()\n        if prior_relation in {"in_scope", "out_of_scope", "unknown"} and prior_reason:\n            relation, reason = prior_relation, prior_reason\n        else:\n            relation = "unknown"\n            reason = "carry-forward record lacks parent_anchor/domain evidence; manual review required"\n    return {\n        "domain": domain,\n        **carried,\n        "keyword": keyword,\n        "parent_anchor": parent or carried.get("parent_anchor"),\n        "domain_relation": relation,\n        "domain_relation_reason": reason,\n        "discovery_source": "carry_forward",\n        "carry_forward": True,\n    }\n\n\n''',
)
replace_between(
    rel,
    "def _timeline_points(",
    "def _point_time(",
    '''def _parse_workflow_time(value: Any) -> datetime | None:\n    text = str(value or "").strip()\n    if not text:\n        return None\n    if text.endswith("Z"):\n        text = text[:-1] + "+00:00"\n    try:\n        parsed = datetime.fromisoformat(text)\n    except ValueError:\n        return None\n    if parsed.tzinfo is None:\n        parsed = parsed.replace(tzinfo=timezone.utc)\n    return parsed.astimezone(timezone.utc)\n\n\ndef _apply_collection_admission(\n    ledger: list[dict[str, Any]], database: dict[str, Any], as_of: datetime\n) -> None:\n    records = database.get("records") if isinstance(database, dict) else []\n    history: dict[tuple[str, str], dict[str, Any]] = {}\n    for record in records if isinstance(records, list) else []:\n        if not isinstance(record, dict):\n            continue\n        key = (canonical_keyword(record.get("domain")), canonical_keyword(record.get("keyword")))\n        if key[1]:\n            history[key] = record\n    now_value = as_of if as_of.tzinfo is not None else as_of.replace(tzinfo=timezone.utc)\n    now_value = now_value.astimezone(timezone.utc)\n    for row in ledger:\n        if row.get("domain_relation") != "in_scope" or row.get("acquisition_status") != "not_started":\n            continue\n        prior = history.get((canonical_keyword(row.get("domain")), canonical_keyword(row.get("keyword"))))\n        if not prior:\n            continue\n        monitoring_state = str(prior.get("monitoring_state") or "").strip()\n        next_review = _parse_workflow_time(prior.get("next_review_at"))\n        row["monitoring_state"] = monitoring_state or row.get("monitoring_state")\n        row["next_review_at"] = prior.get("next_review_at")\n        if monitoring_state == "paused_review":\n            row.update(\n                acquisition_status="not_attempted",\n                acquisition_reason="paused_review",\n                verification_status="not_run",\n                delivery_eligible=False,\n                final_disposition="paused_review",\n            )\n        elif next_review is not None and next_review > now_value:\n            row.update(\n                acquisition_status="not_attempted",\n                acquisition_reason="review_not_due",\n                verification_status="not_run",\n                delivery_eligible=False,\n                final_disposition="retry_scheduled",\n            )\n\n\ndef _timeline_points(payload: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:\n    context = payload if isinstance(payload, dict) else {}\n    series = context.get("series") or context.get("google_trends_series") if isinstance(context, dict) else None\n    if not isinstance(series, list):\n        if isinstance(payload, list):\n            series = payload\n            context = {}\n        else:\n            raise ValueError("timeline payload must contain a series list")\n    points: list[dict[str, Any]] = []\n    for index, point in enumerate(series):\n        if not isinstance(point, dict) or point.get("time") in (None, "") or "value" not in point:\n            raise ValueError(f"timeline point {index} is incomplete")\n        points.append(point)\n    if len(points) < 2:\n        raise ValueError("timeline payload requires at least two observed points")\n    return points, context\n\n\n''',
)
replace_once(
    rel,
    '    for row in ledger:\n        if row.get("domain_relation") != "in_scope":\n            continue\n        all_windows_verified = True\n',
    '    for row in ledger:\n        if row.get("domain_relation") != "in_scope" or row.get("acquisition_status") != "not_started":\n            continue\n        all_windows_verified = True\n',
)
replace_once(
    rel,
    '                    acquisition = str(context.get("acquisition_status") or "data_acquired")\n                    verification = str(context.get("verification_status") or "verified")\n                    if acquisition == "valid_no_data":\n',
    '                    acquisition = str(context.get("acquisition_status") or "data_acquired")\n                    verification = str(context.get("verification_status") or "verified")\n                    if verification != "verified":\n                        reason = context.get("failure_type") or context.get("failure_reason") or "pending_evidence"\n                        raise RuntimeError(str(reason))\n                    if acquisition == "valid_no_data":\n',
)
replace_once(
    rel,
    '                    if verification != "verified" or context.get("delivery_eligible") is False:\n',
    '                    if context.get("delivery_eligible") is False:\n',
)
replace_once(
    rel,
    '        ledger.append(row)\n\n    observations: list[dict[str, Any]] = []\n',
    '        ledger.append(row)\n\n    run_as_of = as_of or datetime.now(timezone.utc)\n    _apply_collection_admission(ledger, database_source, run_as_of)\n    observations: list[dict[str, Any]] = []\n',
)
replace_once(
    rel,
    '    aggregate_result, classified, routes = _classify_and_route(domain, ledger, observations, as_of or datetime.now(timezone.utc))\n',
    '    aggregate_result, classified, routes = _classify_and_route(domain, ledger, observations, run_as_of)\n',
)

# R5: production Sheet delivery is fail-closed for missing run status or missing explicit eligibility.
rel = "skills/emerging-keyword-monitor/scripts/export_to_sheet.py"
replace_once(
    rel,
    '    return str(context.get("status") or database.get("run_status") or "PASS").strip().upper()\n',
    '    value = context.get("status") or database.get("run_status")\n    return str(value).strip().upper() if value not in (None, "") else "UNKNOWN"\n',
)
replace_between(
    rel,
    "def select_delivery_records(",
    "def _sheet_rows(",
    '''def select_delivery_records(\n    database: dict[str, Any],\n    run_context: dict[str, Any] | None = None,\n    *,\n    allow_blocked_dry_run: bool = False,\n) -> dict[str, Any]:\n    """Resolve the Sheet delivery set and review set without touching a client.\n\n    Production delivery is fail-closed: a run must explicitly be PASS and every\n    database record must carry a delivery_eligible decision. Historical files\n    can still be inspected with allow_blocked_dry_run=True, but that mode cannot\n    authorize a production mutation.\n    """\n    records = _records(database)\n    status = _run_status(database, run_context)\n    if status != "PASS" and not allow_blocked_dry_run:\n        raise RuntimeError(f"run status {status} is not eligible for production Sheet mutation")\n\n    has_explicit_eligibility = all("delivery_eligible" in record for record in records)\n    if not has_explicit_eligibility and not allow_blocked_dry_run:\n        raise RuntimeError("production Sheet mutation requires explicit delivery_eligible on every record")\n    if has_explicit_eligibility:\n        delivery_records = [record for record in records if record.get("delivery_eligible") is True]\n        review_records = [record for record in records if record.get("delivery_eligible") is not True]\n    else:\n        delivery_records = list(records)\n        review_records = []\n\n    manifest = database.get("delivery_manifest")\n    if isinstance(manifest, dict) and "delivery_ids" in manifest:\n        expected = {str(value) for value in manifest.get("delivery_ids") or []}\n        actual_ids = [_candidate_id(record) for record in delivery_records]\n        if any(value is None for value in actual_ids):\n            raise ValueError("delivery manifest requires candidate_id on every delivery record")\n        actual = {str(value) for value in actual_ids if value is not None}\n        if actual != expected:\n            raise ValueError(\n                "delivery manifest identity mismatch: "\n                f"expected={sorted(expected)} actual={sorted(actual)}"\n            )\n        if len(actual_ids) != len(actual):\n            raise ValueError("delivery manifest contains duplicate candidate identities")\n\n    return {\n        "run_status": status,\n        "blocked": status != "PASS",\n        "delivery_records": delivery_records,\n        "review_records": review_records,\n        "delivery_count": len(delivery_records),\n        "review_count": len(review_records),\n        "legacy_delivery_fallback": not has_explicit_eligibility,\n    }\n\n\n''',
)

# R6: canonical replay, receipt and Hook must consume the same ledger-qualified identity set.
rel = "runtime/emerging_pipeline.py"
replace_between(
    rel,
    "def replay_pipeline(",
    "def _candidate_id(",
    '''def _classification_eligible_ids(candidate_ledger: list[dict[str, Any]]) -> set[str]:\n    return {\n        candidate_id\n        for row in candidate_ledger\n        if row.get("domain_relation") == "in_scope"\n        and row.get("acquisition_status") == "data_acquired"\n        and row.get("verification_status") == "verified"\n        and (candidate_id := _candidate_id(row)) is not None\n    }\n\n\ndef replay_pipeline(\n    input_path: Path,\n    as_of: str | datetime,\n    candidate_ledger: list[dict[str, Any]] | None = None,\n) -> dict[str, dict[str, Any]]:\n    modules = _modules()\n    input_path = Path(input_path)\n    as_of_datetime = _as_of_datetime(as_of, modules["aggregate"])\n    raw_rows = modules["validate"].load_rows(input_path)\n    if candidate_ledger is not None:\n        eligible_ids = _classification_eligible_ids(candidate_ledger)\n        raw_rows = [row for row in raw_rows if _candidate_id(row) in eligible_ids]\n    validated_rows = modules["validate"].validate_rows(raw_rows, as_of_datetime)\n    canonical = classify_and_route_rows(raw_rows, as_of_datetime)\n    return {\n        "validated": {"rows": validated_rows},\n        "aggregated": canonical["aggregated"],\n        "classified": {"candidates": canonical["classified"]},\n        "routed": {"routes": canonical["routed"]},\n    }\n\n\n''',
)
replace_once(
    rel,
    '    delivery_set = set(str(value) for value in (delivery_ids or classified_ids))\n',
    '    delivery_source = classified_ids if delivery_ids is None else delivery_ids\n    delivery_set = set(str(value) for value in delivery_source)\n',
)
replace_between(
    rel,
    "def run_pipeline(",
    "def main(",
    '''def run_pipeline(\n    input_path: Path,\n    output_dir: Path,\n    as_of: str,\n    receipt_path: Path | None = None,\n    candidate_ledger_path: Path | None = None,\n) -> dict[str, Any]:\n    input_path = Path(input_path).expanduser().resolve()\n    if not input_path.is_file():\n        raise FileNotFoundError(f"Emerging observations input is missing: {input_path}")\n    output_dir = Path(output_dir).expanduser().resolve()\n    output_dir.mkdir(parents=True, exist_ok=True)\n    receipt_path = (Path(receipt_path).expanduser() if receipt_path else output_dir / "receipt.json").resolve()\n    output_paths = {name: output_dir / f"{name}.json" for name in ("validated", "aggregated", "classified", "routed")}\n    all_paths = [*output_paths.values(), receipt_path]\n    existing = [path for path in all_paths if path.exists()]\n    if existing:\n        raise FileExistsError(f"Emerging pipeline output already exists: {existing[0]}")\n\n    modules = _modules()\n    as_of_datetime = _as_of_datetime(as_of, modules["aggregate"])\n    ledger_ref = None\n    candidate_ledger = None\n    if candidate_ledger_path is not None:\n        ledger_path = Path(candidate_ledger_path).expanduser().resolve()\n        if not ledger_path.is_file():\n            raise FileNotFoundError(f"Emerging candidate ledger is missing: {ledger_path}")\n        candidate_ledger = _load_candidate_ledger(ledger_path)\n        ledger_ref = {"path": str(ledger_path), "sha256": _sha256(ledger_path)}\n\n    outputs = replay_pipeline(input_path, as_of_datetime, candidate_ledger)\n    for name, payload in outputs.items():\n        _write_json(output_paths[name], payload)\n\n    classified_rows = outputs["classified"]["candidates"]\n    routed_rows = outputs["routed"]["routes"]\n    if candidate_ledger is None:\n        candidate_ledger = [\n            {"candidate_id": _candidate_id(row), "keyword": row.get("keyword"), "final_disposition": "classified"}\n            for row in classified_rows\n        ]\n        delivery_ids = None\n    else:\n        delivery_ids = [\n            candidate_id\n            for row in candidate_ledger\n            if row.get("delivery_eligible") is True and (candidate_id := _candidate_id(row)) is not None\n        ]\n    reconciliation = reconcile_identity_sets(candidate_ledger, classified_rows, routed_rows, delivery_ids)\n\n    receipt = {\n        "schema": "seo-emerging-pipeline/v1",\n        "as_of": as_of_datetime.isoformat(),\n        "observation_input": {"path": str(input_path), "sha256": _sha256(input_path)},\n        "candidate_ledger": ledger_ref,\n        "reconciliation": reconciliation,\n        "pipeline": {"path": str(PIPELINE_SOURCE_PATH), "sha256": _sha256(PIPELINE_SOURCE_PATH)},\n        "scripts": {\n            name: {"path": str(path.resolve()), "sha256": _sha256(path)}\n            for name, path in SCRIPT_PATHS.items()\n        },\n        "thresholds": {"path": str(THRESHOLDS_PATH.resolve()), "sha256": _sha256(THRESHOLDS_PATH)},\n        "outputs": {\n            name: {"path": str(path.resolve()), "sha256": _sha256(path)}\n            for name, path in output_paths.items()\n        },\n        "route_handoff_ref": str(output_paths["routed"].resolve()),\n    }\n    _write_json(receipt_path, receipt)\n    return receipt\n\n\n''',
)

rel = "runtime/stage_hook.py"
replace_once(
    rel,
    '        if thresholds_path is None:\n            return False, reason\n\n        output_entries = receipt.get("outputs")\n',
    '        if thresholds_path is None:\n            return False, reason\n\n        ledger_path, reason = _verify_hashed_file(receipt.get("candidate_ledger"), "emerging candidate ledger")\n        if ledger_path is None:\n            return False, reason\n        candidate_ledger = pipeline._load_candidate_ledger(ledger_path)\n        delivery_ids = [pipeline._candidate_id(row) for row in candidate_ledger if row.get("delivery_eligible") is True]\n        delivery_ids = [value for value in delivery_ids if value is not None]\n\n        output_entries = receipt.get("outputs")\n',
)
replace_once(
    rel,
    '        replayed = pipeline.replay_pipeline(input_path, as_of)\n        for name in replayed:\n            if saved_outputs[name] != replayed[name]:\n                return False, f"emerging {name} output differs from deterministic replay"\n',
    '        replayed = pipeline.replay_pipeline(input_path, as_of, candidate_ledger)\n        for name in replayed:\n            if saved_outputs[name] != replayed[name]:\n                return False, f"emerging {name} output differs from deterministic replay"\n        reconciliation = pipeline.reconcile_identity_sets(\n            candidate_ledger,\n            saved_outputs["classified"].get("candidates") or [],\n            saved_outputs["routed"].get("routes") or [],\n            delivery_ids,\n        )\n        if receipt.get("reconciliation") != reconciliation:\n            return False, "emerging reconciliation differs from candidate ledger and routed outputs"\n',
)

print("PR39 source transforms applied")
