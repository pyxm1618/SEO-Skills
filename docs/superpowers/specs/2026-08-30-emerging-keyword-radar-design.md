# Emerging Keyword Radar Design

**Goal:** Extend `emerging-keyword-monitor` from a supplied-keyword trend checker into a domain-level, evidence-backed Emerging Keyword Radar without changing SEO selection policy or root-library ownership.

## Scope and invariants

The change is additive around the existing Google collector, comparable-series aggregator, temporal classifier, and router. It keeps `unknown` distinct from zero, preserves collector-bound provenance, retains the existing signal types/states/routes, keeps current Semrush acquisition on the authenticated same-origin `https://sem.3ue.com/` relay, and never emits final SEO decisions or mutates `root-library.csv`.

Google Trends index values remain relative 0–100 values. A Google source label such as `Breakout` is stored as `google_rising_label` and is never copied into the monitor's canonical `signal_type=breakout` or `status=breakout`; those remain classifier results based on a comparable temporal series.

## Components and boundaries

- `runtime/collectors/google_live_collector.py` remains the only live Google evidence writer. It gains a `trends_related` mode and a parameterized `trends_timeline` mode while retaining the `trends` compatibility wrapper. Each mode records structured raw response evidence and a screenshot.
- A Google connection uses either an explicitly separate `SEO_GOOGLE_CDP_URL` browser or a newly created clean context from the general CDP browser. It must contain no Google authentication cookies. If a truly separate context/profile cannot be created safely, collection is `BLOCKED`; no cookie copying, temporary Google account, CAPTCHA bypass, proxy rotation, or provider fallback is allowed. Semrush continues to use its own authenticated relay context.
- `radar_discovery.py` contains pure anchor-pool and breadth-first traversal logic. Root-library rows are read-only bootstrap hints. Initial anchors may come from the domain, explicit user anchors, active/verified relevant roots, and candidate roots marked unverified. Only `relation_type=rising` Trends rows enqueue the next BFS layer by default. Autocomplete and Semrush Ideas are supplemental evidence and never recursive edges unless an explicit policy flag is supplied.
- `birth_history.py` contains deterministic long-series analysis. It consumes one actual long-history series at a time and never concatenates 5y, 12m, 90d, 30d, or 7d normalized indexes. It produces `estimated_birth_window`, `birth_window_start`, `birth_window_end`, `birth_source_resolution`, `birth_confidence`, `birth_reason`, `birth_evidence_series`, and `demand_history_type`.
- `update_emerging_database.py` maintains a JSON database and CSV export under `.seo-run/`. It preserves the earliest `first_observed_at`, prior status/evidence, and current unknowns without manufacturing values. It writes route/handoff records but does not invoke selection logic.
- `run_emerging_radar.py` is a thin orchestration CLI. Live collector calls are made through the collector CLI so collector receipts remain direct-CLI-bound. It accepts current Semrush Ideas descriptors as optional supplemental inputs, records stage payloads/validation results/blockers/candidate counts/output references, and validates/registers the final `emerging_radar_run` summary before returning.

## Workflow

```text
domain + explicit anchors + read-only root bootstrap
        |
        v
initial anchor pool (depth 0)
        |
        v
Google Trends Related/Rising -- serial, throttled, isolated context
        |
        +--> preserve Top/Rising/Breakout raw facts and provenance
        v
dedupe + domain relation gate + brand/navigation stop reasons
        |
        v
Rising-only BFS (default depth 2, per-anchor limit 10, global cap 200)
        |
        +--> optional Autocomplete/Semrush supplemental evidence (descriptor-bound)
        v
independent Google timeline series: 5y | 12m | 90d (actual resolution retained)
        |
        +--> validate observations and comparable-series identity
        +--> birth/history analysis on 5y only
        +--> existing classifier on one selected recent comparable series
        v
existing states and routes
        |
        v
JSON database + CSV + raw evidence + screenshots + selection handoffs
```

Each timeframe has its own `time_window`, `signal_unit`, source URL, raw evidence reference, observed timestamp, and resolution. Growth and persistence are calculated only within one series key. The long series is used for historical presence and history type; the medium series is retained for shape; recent series are used for current persistence/acceleration.

## Birth and demand-history rules

The `birth` section in `thresholds.json` supplies minimum actual observations, minimum sustained positive observations, low-baseline and lift requirements, quiet-period requirements, and follow-up requirements. The algorithm uses observed points only:

1. Reject birth inference as `unknown` when the long series lacks enough actual observations or only contains an isolated spike.
2. Detect a formation window only after multiple valid observations are positive, materially above the preceding low/noise baseline, and followed by the configured persistence evidence. The output is month/bucket precision derived from the actual source resolution, never a fabricated day.
3. If the available series begins with sustained positive demand and has no prehistory, mark `demand_history_type=preexisting` and `birth_reason=before_available_history`; do not use the first bucket as a birthday.
4. If an earlier positive formation is followed by a sufficiently long observed quiet period and a later persistent rise, mark `resurgent`. The old history blocks `net_new`; the current canonical signal may still be `breakout` only when the existing classifier independently proves breakout conditions.
5. If a persistent formation is found without earlier positive history, mark `newly_observed`. Otherwise use `unknown` and preserve the evidence/reason.

`first_observed_at` remains the earliest timestamp known to this evidence system, including carried incremental state. It is never used as a substitute for the birth window.

## Failure and evidence policy

Missing or malformed payloads, absent source evidence, CAPTCHA/unusual traffic, unsafe browser isolation, stale relay captures, and stage-contract violations are explicit blockers. A blocked acquisition cannot be silently replaced by Bing, third-party suggestions, AI-generated candidates, or estimated metrics. A valid Trends response with no Rising rows is a successful observation with zero expansion edges, not a fabricated candidate.

New stage contracts cover Related/Rising, parameterized timeline, and the Radar run summary. Collector-bound production validation uses the existing receipt/hash mechanism, extended only with the new Google Related evidence type.

## Verification

Tests cover Related/Top/Rising/Breakout parsing, malformed/missing payloads, timeframe isolation, Google Breakout semantic separation, BFS visited/depth/cap and Rising-only recursion, domain drift stops, birth cases A–E, context isolation, CAPTCHA fail-closed behavior, persistence merge, stage contracts, and routing regressions. Completion additionally requires the repository test suite, `compileall`, and one real browser Radar E2E; an external Google blocker may be reported only with raw/screenshot evidence and a non-PASS stage status.
