# Emerging Keyword Radar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a real, domain-starting Emerging Keyword Radar to `emerging-keyword-monitor` while preserving the existing temporal classifier, router, provenance, Semrush relay-only boundary, and fail-closed lifecycle.

**Architecture:** Keep browser acquisition in the existing Google collector and keep deterministic analysis in small Python modules. `radar_discovery.py` performs Rising-only BFS over normalized related-query evidence; `birth_history.py` analyzes only one long comparable series; `run_emerging_radar.py` coordinates collector CLIs, validation, classification, routing, and `.seo-run` persistence. Existing `aggregate_signals.py`, `classify_emergence.py`, and `route_candidates.py` receive additive fields and guards only.

**Tech Stack:** Python 3 standard library, Playwright sync API for existing live browser collection, JSON/CSV artifacts, pytest, existing stage validator and evidence-binding receipt system.

**Spec:** `docs/superpowers/specs/2026-08-30-emerging-keyword-radar-design.md`

## Global Constraints

- `unknown != 0`; missing data remains missing and malformed data is invalid.
- Google evidence is collected from a real logged-out isolated Google browser context; no Google account, cookie copying, CAPTCHA bypass, proxy rotation, or provider fallback.
- New/current Semrush data remains authenticated same-origin relay-only at `https://sem.3ue.com/`; no official API, API keys, units, Ahrefs, or alternative provider.
- Google Trends 5y, 12m, 90d, 30d, and 7d indexes are separate comparable series and are never concatenated or compared arithmetically across timeframes.
- Google `Breakout` is preserved as `google_rising_label` and never directly becomes canonical `signal_type=breakout` or `status=breakout`.
- Only Trends `relation_type=rising` is a recursive BFS edge by default; Autocomplete and Semrush Ideas are supplemental evidence. The live runner accepts repeatable `--semrush-request` paths only for current authenticated Ideas descriptors captured from the existing relay context; unmatched anchors remain optional and relay/schema failures block.
- Existing signal types, states, routes, selection thresholds, `root-library.csv`, and downstream selection ownership remain unchanged.
- No PostgreSQL, Supabase, OAuth, workflow framework, proxy farm, or other Skill refactor is introduced.

---

### Task 1: Related/Rising parser and collector evidence contract

**Files:**
- Modify: `runtime/collectors/google_live_collector.py`
- Modify: `runtime/evidence_binding.py`
- Modify: `runtime/stage_validator.py`
- Modify: `runtime/stage_contracts.json`
- Test: `tests/test_emerging_radar_related.py`

**Interfaces:**
- Produces `parse_trends_related(payload) -> list[dict]` with `query`, `relation_type`, `rank`, `rising_value`, `google_rising_label`, and `is_google_breakout`.
- Produces `trends_related(context, anchor, country, timeframe, evidence_dir) -> dict` with raw payload/screenshot references and the normalized related rows.
- Adds stage `trends_related` and evidence type `google_trends_related` without changing existing `finalist_trend` behavior.

- [ ] **Step 1: Write the failing parser and contract tests**

```python
def test_related_parser_keeps_top_separate_from_rising_and_preserves_breakout():
    rows = google.parse_trends_related({"default": {"rankedList": [
        {"rankedKeyword": [{"query": "wedding dress", "value": 100}]},
        {"rankedKeyword": [
            {"query": "micro wedding", "value": "Breakout"},
            {"query": "wedding content creator", "value": 650},
        ]},
    ]}})
    assert rows[0]["relation_type"] == "top"
    assert rows[1]["relation_type"] == "rising"
    assert rows[1]["google_rising_label"] == "Breakout"
    assert rows[1]["is_google_breakout"] is True

def test_related_parser_skips_malformed_rows_and_rejects_missing_payload():
    rows = google.parse_trends_related({"default": {"rankedList": [
        {"rankedKeyword": [{"query": "valid rising", "value": 20}, {"value": 40}]},
    ]}})
    assert [row["query"] for row in rows] == ["valid rising"]
    with pytest.raises(RuntimeError, match="related"):
        google.parse_trends_related({})

def test_trends_related_stage_requires_real_payload_fields():
    errors = validator.validate_stage("trends_related", {
        "anchor": "wedding", "related_queries": [], "country": "US",
        "timeframe": "today 12-m", "observed_at": "2026-08-30T00:00:00Z",
        "source": "Google Trends", "source_url": "https://trends.google.com/trends/explore",
        "raw_evidence_ref": "related.json", "screenshot_ref": "related.png",
    }, contracts)
    assert errors == []
```

- [ ] **Step 2: Run the focused tests and verify the expected RED failure**

Run: `python3 -m pytest -q tests/test_emerging_radar_related.py`

Expected: collection fails because `parse_trends_related`, `trends_related`, and the `trends_related` contract do not exist.

- [ ] **Step 3: Implement the smallest parser, live mode, binding replay, and contracts**

Use `default.rankedList`; map list position or an explicit group title to `top`/`rising`; skip rows without a non-empty query; parse numeric values only when finite and non-negative; preserve the exact non-numeric Google label in `google_rising_label`. A valid payload with no Rising rows returns an empty candidate edge list. Capture only `trends.google.com` related-search response payloads, save raw JSON and screenshot, and bind the output through `google_trends_related`.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run: `python3 -m pytest -q tests/test_emerging_radar_related.py tests/test_a_plus_confirmed_gaps.py::test_trends_parser_extracts_observed_temporal_series`

Expected: PASS with the existing timeline parser unchanged.

- [ ] **Step 5: Commit the contract boundary**

```bash
git add runtime/collectors/google_live_collector.py runtime/evidence_binding.py runtime/stage_validator.py runtime/stage_contracts.json tests/test_emerging_radar_related.py
git commit -m "feat: add collector-bound Google Trends related evidence"
```

### Task 2: Parameterized timeline, browser isolation, and throttling

**Files:**
- Modify: `runtime/collectors/google_live_collector.py`
- Modify: `runtime/evidence_binding.py`
- Test: `tests/test_emerging_radar_google_safety.py`

**Interfaces:**
- Produces `trends_timeline(context, keyword, market, timeframe, evidence_dir) -> dict` with `requested_timeframe`, `actual_resolution`, `series`, raw evidence, and screenshot.
- Retains `trends(context, keyword, market, evidence_dir)` as a compatibility wrapper for `today 12-m`.
- Produces `connect()` using `SEO_GOOGLE_CDP_URL` when provided, otherwise a newly created clean context from the general CDP browser; unsafe context creation fails closed.
- Produces a serial `Throttle(min_delay_seconds, jitter_seconds, sleeper, random_source)` used by the runner.

- [ ] **Step 1: Write the failing tests**

```python
def test_timeline_preserves_requested_timeframe_and_infers_actual_resolution(monkeypatch):
    result = google.trends_timeline(fake_context, "wedding", "US", "today 5-y", ".")
    assert result["requested_timeframe"] == "today 5-y"
    assert result["actual_resolution"] == "weekly"
    assert result["google_trends_series"] == result["series"]

def test_google_connection_requires_clean_context_without_auth_cookies(monkeypatch):
    pw, browser, context = google.connect()
    assert context is browser.created_context
    assert browser.created_context.cookies_seen == []
    assert context is not semrush_context

def test_google_connection_blocks_when_clean_context_cannot_be_created(monkeypatch):
    monkeypatch.setattr(fake_browser, "new_context", None)
    with pytest.raises(RuntimeError, match="isolated|profile"):
        google.connect()

def test_throttle_is_serial_and_uses_configured_delay(monkeypatch):
    sleeps = []
    throttle = google.Throttle(1.0, 0.0, sleeps.append, lambda: 0.0)
    throttle.wait()
    throttle.wait()
    assert sleeps == [1.0]
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `python3 -m pytest -q tests/test_emerging_radar_google_safety.py`

Expected: FAIL because the new timeline fields, isolation helper, and throttle do not exist.

- [ ] **Step 3: Implement parameterized timeline and safety boundaries**

Refactor the existing timeline capture into a parameterized function without changing its parser output. Infer resolution only from actual timestamp deltas or explicit payload metadata; never fill missing dates or combine requested windows. Use a dedicated CDP endpoint when configured; otherwise call `browser.new_context()` and reject unsafe/unavailable creation rather than deleting or copying cookies. Check cookie records for known Google authentication names and reject them. Keep CAPTCHA/unusual traffic errors as `RuntimeError` blockers.

- [ ] **Step 4: Run focused and legacy collector tests GREEN**

Run: `python3 -m pytest -q tests/test_emerging_radar_google_safety.py tests/test_live_acceptance_p1_repairs.py tests/test_observed_evidence_binding.py`

Expected: PASS with old `trends` and receipt replay behavior intact.

- [ ] **Step 5: Commit the collector safety changes**

```bash
git add runtime/collectors/google_live_collector.py runtime/evidence_binding.py tests/test_emerging_radar_google_safety.py
git commit -m "feat: isolate Google timeline collection and preserve timeframe context"
```

### Task 3: Domain anchor pool and Rising-only BFS

**Files:**
- Create: `skills/emerging-keyword-monitor/scripts/radar_discovery.py`
- Test: `skills/emerging-keyword-monitor/tests/test_radar_discovery.py`

**Interfaces:**
- `canonical_keyword(value) -> str` normalizes dedupe identity.
- `build_anchor_pool(domain, explicit_anchors, root_rows) -> list[dict]` creates depth-0 anchors and marks candidate roots as unverified bootstrap hints.
- `discover_rising_bfs(domain, anchors, related_fetcher, relation_gate=None, max_depth=2, per_anchor_limit=10, max_candidates=200) -> dict` returns `anchors`, `visited`, `candidates`, `stops`, and `blockers`.
- A candidate preserves `parent_anchor`, `discovery_depth`, `discovery_source`, `google_rising_label`, `source_url`, `raw_evidence_ref`, `domain_relation`, and `domain_relation_reason`.

- [ ] **Step 1: Write the failing BFS and semantic-gate tests**

```python
def test_rising_bfs_dedupes_and_obeys_parent_depth_and_cap():
    graph = {
        "a": rising("b", "c"), "b": rising("d"),
        "c": rising("a", "e"), "d": [], "e": [],
    }
    result = discover_rising_bfs("domain", [{"keyword": "a", "discovery_depth": 0}], graph.__getitem__, max_depth=2, max_candidates=4)
    assert [row["keyword"] for row in result["candidates"]] == ["b", "c", "d", "e"]
    assert next(row for row in result["candidates"] if row["keyword"] == "d")["parent_anchor"] == "b"
    assert "a" in result["visited"]
    assert len(result["candidates"]) == 4

def test_bfs_only_rising_rows_enqueue_and_top_rows_remain_context():
    result = discover_rising_bfs("wedding", [{"keyword": "wedding", "discovery_depth": 0}], lambda _: [
        {"query": "top wedding", "relation_type": "top", "rank": 1},
        {"query": "rising wedding", "relation_type": "rising", "rank": 1},
    ])
    assert [row["keyword"] for row in result["candidates"]] == ["rising wedding"]

def test_out_of_domain_candidate_is_preserved_but_not_recursed():
    calls = []
    result = discover_rising_bfs("wedding", [{"keyword": "wedding", "discovery_depth": 0}], lambda keyword: (calls.append(keyword) or rising("celebrity news")), relation_gate=lambda *_: ("out_of_scope", "not a wedding search task"))
    assert result["candidates"][0]["domain_relation"] == "out_of_scope"
    assert calls == ["wedding"]
    assert result["stops"][0]["reason"] == "domain_relation_out_of_scope"
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `python3 -m pytest -q skills/emerging-keyword-monitor/tests/test_radar_discovery.py`

Expected: FAIL because the radar module and traversal API are absent.

- [ ] **Step 3: Implement the pure anchor pool and BFS**

Use a queue and a visited set keyed by `canonical_keyword`. Count only unique candidate keywords toward the global cap. Preserve every discovered row, including out-of-scope or brand/navigation rows, with an analysis stop reason; only in-scope Rising rows are enqueued. Record fetch exceptions as blockers and stop that branch; never substitute another source. Keep Top rows in the anchor-level evidence context but do not turn them into Emerging candidates.

- [ ] **Step 4: Run focused tests GREEN**

Run: `python3 -m pytest -q skills/emerging-keyword-monitor/tests/test_radar_discovery.py`

Expected: PASS with no browser dependency.

- [ ] **Step 5: Commit the deterministic traversal**

```bash
git add skills/emerging-keyword-monitor/scripts/radar_discovery.py skills/emerging-keyword-monitor/tests/test_radar_discovery.py
git commit -m "feat: add Rising-only emerging radar traversal"
```

### Task 4: Long-history birth inference and demand-history classification

**Files:**
- Create: `skills/emerging-keyword-monitor/scripts/birth_history.py`
- Modify: `skills/emerging-keyword-monitor/scripts/aggregate_signals.py`
- Modify: `skills/emerging-keyword-monitor/scripts/classify_emergence.py`
- Modify: `skills/emerging-keyword-monitor/references/thresholds.json`
- Modify: `skills/emerging-keyword-monitor/references/data-contracts.md`
- Modify: `skills/emerging-keyword-monitor/references/classification-rules.md`
- Test: `skills/emerging-keyword-monitor/tests/test_birth_history.py`

**Interfaces:**
- `infer_demand_history(points, thresholds, source_resolution) -> dict` consumes one actual long-history series and returns `demand_history_type`, birth fields, historical presence, and evidence points.
- `aggregate_signals.py` keeps every timeframe in its own series key and carries long-history analysis fields without cross-series arithmetic.
- `classify_emergence.py` blocks `net_new` when `demand_history_type` is `preexisting` or `resurgent`; it does not map Google Breakout labels to canonical classifier results.

- [ ] **Step 1: Write failing birth/history cases A–E and timeframe isolation tests**

```python
def test_low_baseline_followed_by_persistent_rise_is_newly_observed():
    result = infer_demand_history(points([0, 0, 1, 0, 2, 12, 20, 24, 22]), thresholds, "weekly")
    assert result["demand_history_type"] == "newly_observed"
    assert result["estimated_birth_window"] == "2025-06 ~ 2025-07"
    assert result["birth_confidence"] in {"medium", "high"}

def test_longstanding_positive_series_is_preexisting_without_fake_birth_date():
    result = infer_demand_history(points([25, 30, 28, 32, 31, 35]), thresholds, "monthly")
    assert result["demand_history_type"] == "preexisting"
    assert result["estimated_birth_window"] is None
    assert result["birth_reason"] == "before_available_history"

def test_quiet_period_after_old_demand_is_resurgent_and_not_net_new():
    result = infer_demand_history(points([20, 22, 24, 0, 0, 0, 0, 15, 20, 25]), thresholds, "weekly")
    assert result["demand_history_type"] == "resurgent"
    assert result["resurgence_window"] == "2025-06 ~ 2025-07"

def test_single_spike_does_not_get_high_confidence_birth():
    result = infer_demand_history(points([0, 0, 40, 0, 0]), thresholds, "weekly")
    assert result["demand_history_type"] == "unknown"
    assert result["birth_confidence"] != "high"

def test_timeframes_are_not_combined_for_growth():
    rows = timeline_rows("wedding", "5y", [10, 20]) + timeline_rows("wedding", "90d", [80, 90])
    candidate = aggregate(rows, as_of)
    assert len(candidate["candidates"][0]["source_evidence"]) == 2
    assert candidate["candidates"][0]["aggregation_policy"] == "no_cross_series_addition"
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `python3 -m pytest -q skills/emerging-keyword-monitor/tests/test_birth_history.py`

Expected: FAIL because birth inference and demand-history fields do not exist.

- [ ] **Step 3: Implement the deterministic birth algorithm and classifier guard**

Add an independent `birth` threshold section without changing existing selection or temporal thresholds. Use actual observed points only; require preceding baseline observations, multiple above-baseline formation points, and follow-up persistence. Format windows to month or source bucket precision. Mark a series beginning with sustained positive demand as `preexisting`/`before_available_history`; detect `resurgent` only with earlier positive observations, observed quiet observations, and a later persistent rise. Keep insufficient or isolated cases `unknown`. Add `demand_history_type` to candidate schema and ensure resurgent/preexisting history prevents `net_new` while allowing the existing breakout rule to decide independently.

- [ ] **Step 4: Run focused and existing temporal tests GREEN**

Run: `python3 -m pytest -q skills/emerging-keyword-monitor/tests/test_birth_history.py skills/emerging-keyword-monitor/tests/test_persistence_window_selection.py skills/emerging-keyword-monitor/tests/test_time_window_replay.py skills/emerging-keyword-monitor/tests/test_emerging_monitor.py`

Expected: PASS; all existing state-machine and comparable-series tests remain green.

- [ ] **Step 5: Commit long-history analysis**

```bash
git add skills/emerging-keyword-monitor/scripts/birth_history.py skills/emerging-keyword-monitor/scripts/aggregate_signals.py skills/emerging-keyword-monitor/scripts/classify_emergence.py skills/emerging-keyword-monitor/references/thresholds.json skills/emerging-keyword-monitor/references/data-contracts.md skills/emerging-keyword-monitor/references/classification-rules.md skills/emerging-keyword-monitor/tests/test_birth_history.py
git commit -m "feat: infer emerging demand history from long trends"
```

### Task 5: Persistent database, CSV export, route handoff, and thin runner

**Files:**
- Create: `skills/emerging-keyword-monitor/scripts/update_emerging_database.py`
- Create: `skills/emerging-keyword-monitor/scripts/run_emerging_radar.py`
- Modify: `skills/emerging-keyword-monitor/scripts/route_candidates.py`
- Modify: `skills/emerging-keyword-monitor/references/routing-rules.md`
- Test: `skills/emerging-keyword-monitor/tests/test_emerging_database.py`

**Interfaces:**
- `merge_database(existing, classified_candidates, routes, discovered_at) -> dict` keys records by `(domain, canonical keyword)`, preserves earliest `first_observed_at`, and stores prior status/evidence history.
- `write_database(database, database_path, csv_path) -> None` writes `.seo-run/emerging-keywords.json` and importable CSV with unknowns blank/null rather than zero.
- `run_emerging_radar.py` accepts `--domain`, repeatable `--anchor`, `--country`, `--max-depth`, `--per-anchor-limit`, `--max-candidates`, repeatable `--semrush-request`, and output paths; live collector calls execute as direct collector CLIs so evidence receipts remain valid.
- Router handoffs retain discovery/history fields and continue to emit only canonical existing routes; confirmed existing-root candidates retain complete `selection_handoff`.

- [ ] **Step 1: Write failing persistence and routing tests**

```python
def test_database_merge_preserves_first_seen_and_previous_state():
    existing = {"schema_version": 1, "records": [{
        "domain": "wedding", "keyword": "micro wedding",
        "first_observed_at": "2026-08-01", "status": "watch",
        "source_evidence": ["old.json"],
    }]}
    merged = merge_database(existing, [{
        "domain": "wedding", "keyword": "micro wedding",
        "first_observed_at": "2026-08-20", "status": "emerging",
        "source_evidence": ["new.json"], "volume": None,
    }], [], "2026-08-30T00:00:00Z")
    record = merged["records"][0]
    assert record["first_observed_at"] == "2026-08-01"
    assert record["previous_status"] == "watch"
    assert record["status"] == "emerging"
    assert record["volume"] is None

def test_runner_does_not_make_autocomplete_or_semrush_edges_recursive():
    result = run_pipeline(fake_related, fake_autocomplete, fake_semrush, domain="wedding")
    assert result["recursive_edge_policy"] == "google_trends_rising_only"

def test_existing_root_confirmed_candidate_keeps_selection_handoff():
    route = route_candidate({"keyword": "micro wedding", "root_id": "root-wedding", "root_relation": "existing_root", "status": "emerging", "signal_type": "breakout"})
    assert route["route"] == "selection_handoff"
    assert "do_candidate" not in json.dumps(route)
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `python3 -m pytest -q skills/emerging-keyword-monitor/tests/test_emerging_database.py`

Expected: FAIL because persistence and runner APIs are absent and router does not carry new fields.

- [ ] **Step 3: Implement persistence and orchestration**

Persist current records plus explicit previous-state fields and history; do not treat absent current values as zero. The runner builds the read-only anchor pool, invokes serial throttled Related/Rising collection, optionally records Autocomplete/Semrush supplemental evidence without using it as a recursive edge, collects independent `today 5-y`, `today 12-m`, and `today 90-d` timelines, validates each payload against its stage contract, analyzes the long series, classifies using a recent comparable series, routes, and writes report/database/CSV/handoff artifacts. Before returning, it validates and registers the final `emerging_radar_run` summary; a collector or contract blocker is recorded as `BLOCKED` and never reported as PASS.

- [ ] **Step 4: Run focused persistence/routing tests GREEN**

Run: `python3 -m pytest -q skills/emerging-keyword-monitor/tests/test_emerging_database.py skills/emerging-keyword-monitor/tests/test_emerging_monitor.py`

Expected: PASS with all canonical routes unchanged.

- [ ] **Step 5: Commit persistence and pipeline**

```bash
git add skills/emerging-keyword-monitor/scripts/update_emerging_database.py skills/emerging-keyword-monitor/scripts/run_emerging_radar.py skills/emerging-keyword-monitor/scripts/route_candidates.py skills/emerging-keyword-monitor/references/routing-rules.md skills/emerging-keyword-monitor/tests/test_emerging_database.py
git commit -m "feat: persist emerging radar records and handoffs"
```

### Task 6: Skill documentation, hook integration, and contract regression coverage

**Files:**
- Modify: `skills/emerging-keyword-monitor/SKILL.md`
- Modify: `skills/emerging-keyword-monitor/references/state-machine.md`
- Modify: `skills/emerging-keyword-monitor/references/source-policy.md`
- Modify: `runtime/codex_stage_hook.py`
- Modify: `runtime/TRUST_BOUNDARY.md`
- Test: `skills/emerging-keyword-monitor/tests/test_radar_contracts.py`

- [ ] **Step 1: Write failing contract/documentation/hook tests**

```python
def test_contracts_cover_related_timeline_and_radar_run():
    contracts = json.loads(CONTRACTS.read_text())
    assert {"trends_related", "trends_timeline", "emerging_radar_run"} <= set(contracts)
    assert {"trends_related", "trends_timeline"} <= set(hook.CANONICAL_STAGES)

def test_skill_documents_timeframe_and_google_breakout_separation():
    text = SKILL.read_text()
    assert "different timeframe" in text.lower()
    assert "google_rising_label" in text
    assert "logged-out" in text or "logged out" in text
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `python3 -m pytest -q skills/emerging-keyword-monitor/tests/test_radar_contracts.py`

Expected: FAIL because the new contracts, hook stage names, and documentation are absent.

- [ ] **Step 3: Implement the documentation and hook additions**

Document discovery, temporal validation, birth inference, classification, and selection as separate questions; state that Trends indexes are relative and timeframe-local; describe logged-out Google isolation and blocker handling. Add only new canonical stages needed to validate the new evidence and Radar run; preserve all existing hook transitions and completion semantics.

- [ ] **Step 4: Run contract and full focused tests GREEN**

Run: `python3 -m pytest -q skills/emerging-keyword-monitor/tests/test_radar_contracts.py tests/test_codex_stage_hooks.py tests/test_execution_integrity.py tests/test_observed_evidence_binding.py`

Expected: PASS.

- [ ] **Step 5: Commit documentation and hook contract**

```bash
git add skills/emerging-keyword-monitor/SKILL.md skills/emerging-keyword-monitor/references/state-machine.md skills/emerging-keyword-monitor/references/source-policy.md runtime/codex_stage_hook.py runtime/TRUST_BOUNDARY.md skills/emerging-keyword-monitor/tests/test_radar_contracts.py
git commit -m "docs: bind emerging radar stages to safety contracts"
```

### Task 7: Full verification, real-browser E2E, report, and remote Draft PR

**Files:**
- Create: `.seo-run/emerging-radar-live-20260830/` runtime artifacts only; do not commit.
- Create: `docs/emerging-keyword-radar-implementation-report.md`

- [ ] **Step 1: Run targeted suite and compileall**

Run:

```bash
python3 -m pytest -q skills/emerging-keyword-monitor/tests tests/test_live_acceptance_p1_repairs.py tests/test_observed_evidence_binding.py tests/test_execution_integrity.py
python3 -m compileall -q runtime skills
```

Expected: zero failures and exit code 0; record exact counts.

- [ ] **Step 2: Run the complete repository suite**

Run: `python3 -m pytest -q`

Expected: all baseline tests plus new tests pass; record exact count and duration.

- [ ] **Step 3: Run real Google Radar E2E**

Use a normal test domain such as `wedding` with a clean Google browser context. Confirm the context is logged out, run Related/Rising, preserve raw/screenshot evidence, collect independent 5y/12m/90d timelines for the configured candidate limit, validate stages, write the JSON database and CSV, and record actual candidate/status/route counts. If Google returns CAPTCHA/unusual traffic, stop as `BLOCKED` with raw/screenshot evidence and do not fabricate candidates or PASS.

- [ ] **Step 4: Run Semrush acceptance only if the run requests new/current Semrush metrics**

Use the existing current authenticated `sem.3ue.com` relay capture and collector. If unavailable or stale, record `BLOCKED`; do not use an official API or fallback provider.

- [ ] **Step 5: Write and verify the implementation report**

Include source/base/repair/final SHA, initial audit, changed and untouched files, workflow diagram, birth logic, Google safety, exact test results, live evidence and blockers, output artifact paths, limitations, P0/P1/P2 risk assessment, and exactly one final verdict: `PASS`, `PASS WITH ACCEPTED ENVIRONMENT BLOCKER`, or `NOT READY`.

- [ ] **Step 6: Push and create the requested Draft PR without merging**

```bash
git status --short
git push -u origin codex/seo-emerging-radar-repair
gh pr create --draft --base codex/seo-a-plus-scope-correction --head codex/seo-emerging-radar-repair --title "feat: add domain-level emerging keyword radar" --body-file docs/emerging-keyword-radar-implementation-report.md
```

Verify the remote PR base/head and final SHA through the forge output. Do not merge, deploy, force-push, or delete the repair worktree.

## Final checklist

- [ ] Every new production function has a test that was observed failing before implementation.
- [ ] Every timeframe remains a separate comparable series with its own provenance and resolution.
- [ ] Google Breakout labels remain observed source facts only.
- [ ] BFS recursion is Rising-only by default and has visited/depth/per-anchor/global caps.
- [ ] Birth cases A–E and resurgent/preexisting guards are covered.
- [ ] Google and Semrush contexts remain isolated and Semrush remains relay-only.
- [ ] Database/CSV/handoff artifacts preserve unknowns and prior state.
- [ ] Existing routing, hook, classifier, and full repository tests pass.
- [ ] Real E2E evidence is captured or an evidenced environment blocker is reported.
- [ ] Draft PR targets `codex/seo-a-plus-scope-correction`; no merge occurs.
