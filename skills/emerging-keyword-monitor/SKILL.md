---
name: emerging-keyword-monitor
description: Use when discovering or monitoring newly forming search demand, breakout queries, or new search expressions over time, including distinguishing net-new demand from breakout growth and routing confirmed emerging signals downstream.
---

# Emerging Keyword Monitor

Detect and maintain evidence for search demand that is newly observed, accelerating, or changing expression. This skill answers **what demand is forming or changing now**; it does not make final SEO opportunity decisions.

## Boundaries

Use this skill for temporal demand discovery and monitoring. It may consume `root_id` references from `keyword-root-library`, but it must never copy or mutate `root-library.csv`.

It may hand confirmed emerging candidates to `seo-keyword-selection`, but it must never emit `do_candidate`, `observe`, or `principle_eliminate` as final SEO decisions and must not modify that skill's thresholds.

Read before execution:

- `references/data-contracts.md` — observation/candidate fields and unknown semantics.
- `references/source-policy.md` — ingestion and provenance rules.
- `references/classification-rules.md` — net-new, breakout, variant, noise, and metric boundaries.
- `references/state-machine.md` — explainable states and transitions.
- `references/routing-rules.md` — downstream handoff rules.
- `references/thresholds.json` — v1 temporal-shape thresholds only.

## Production start and attested pipeline

Start the Emerging run before collecting observations:

```bash
export SEO_RUN_MANIFEST=.seo-run/active.json
python3 runtime/start_seo_run.py --route emerging
```

Run the four stages through the repository runner with one fixed `as_of`:

```bash
python3 runtime/emerging_pipeline.py \
  --input observations.json --as-of 2026-08-29T23:59:59Z \
  --output-dir .seo-run/emerging/20260829T235959Z
```

The runner writes validated, aggregated, classified, and routed outputs plus
an `seo-emerging-pipeline/v1` receipt. Record its path as
`emerging_pipeline_receipt_ref` and the receipt's `outputs.routed.path` as
`route_handoff_ref` in the same manifest. The Hook checks current source
hashes and deterministically replays all four stages. A real `no_handoff`,
`watch`, or `insufficient_evidence` result stays that way; never hand-write a
`selection_handoff` to force downstream work.

The standalone router accepts a confirmed `emerging`/`breakout` state only
when the input is a valid, error-free structured output from
`classify_emergence.py`; it does not promote a hand-written status.

## Evidence Discipline

`unknown != 0`. Missing values remain unknown; malformed values are invalid. Never invent Volume, KD, CPC, `intitle`, SERP facts, timestamps, first-seen dates, trend values, or growth.

`first_observed_at` means the first observation in the current evidence system. It is not an absolute keyword birth date. Google Trends zero is a relative signal, not proof of zero real searches.

Never add signals with different units or incomparable source contexts. Trends indexes, search volume, mentions, and other units remain separate series. Different timeframe indexes in Google Trends are also normalized independently: `5y`, `12m`, `90d`, `30d`, and `7d` are separate comparable series and must never be compared arithmetically or concatenated. Use the long series for history/birth inference, the medium series for shape, and recent series for persistence/acceleration.

Google Related/Rising `Breakout` is an observed Google label only (`google_rising_label=Breakout`). It never directly sets this skill's canonical `signal_type` or `status`; canonical `breakout` requires the existing classifier's baseline, growth, persistence, and freshness evidence. Google collection must use a genuinely isolated logged-out context; if that cannot be established, fail closed rather than copying or deleting cookies or using a temporary account.

If a real data source is unavailable, say so and leave the relevant field `unknown`. Do not replace a missing search-demand time series with supply-side page counts, product launches, article frequency, or general web mentions and then call the result confirmed search growth.

## Workflow

Validate observations:

```bash
python scripts/validate_observations.py --input observations.json --format json
```

Aggregate only comparable time series:

```bash
python scripts/aggregate_signals.py --input observations.json --format json
```

Classify temporal evidence:

```bash
python scripts/classify_emergence.py --input candidates.json --format json
```

Route without making final SEO decisions:

```bash
python scripts/route_candidates.py --input classified.json --format json
```

For a domain-level radar, start with a domain/anchor pool and use Trends Rising as the recursive edge. Autocomplete and Semrush Ideas may be supplemental evidence but are not recursive BFS edges by default. Persist radar records and handoffs under `.seo-run/`; the monitor still does not invoke selection decisions.

The live radar CLI may receive repeatable `--semrush-request PATH` options. Each path must be a current authenticated same-origin Semrush Ideas request descriptor for its captured seed; unmatched anchors remain without Semrush supplemental evidence, and any attempted relay/schema failure is a blocker. The CLI never constructs a Semrush endpoint or falls back to an API/provider.

Before a live run is considered complete, the runner writes the final summary, validates it against the `emerging_radar_run` contract, and registers `stages.emerging_radar_run.validation_receipt_ref`. A `PASS` summary must have no blockers; a blocked summary must retain a structured blocker.

When running interactively without normalized files, apply the same contracts conceptually. Do not loosen the state machine or routing rules just because evidence was gathered conversationally or from web research.

Optionally mirror the persisted database into a Google Sheet:

```bash
python scripts/export_to_sheet.py --database .seo-run/emerging-keywords.json --dry-run
python scripts/export_to_sheet.py --database .seo-run/emerging-keywords.json \
  --sheet-id SHEET_ID --credentials ~/.config/seo-sheets/service-account.json
```

`--dry-run` prints the rows and needs no dependency or credential. A real export needs `gspread` and a Google service-account key whose `client_email` has Editor access on the target sheet; `~` in either path is expanded. Rows are upserted by `(domain, keyword)`, so re-running updates in place instead of appending duplicates.

The Sheet is an export layer, never a data source. The authoritative outputs remain the local JSON/CSV, the export takes part in no stage contract, evidence receipt, or pipeline source hash, and a failed export leaves run validity untouched. `unknown` is exported as `unknown` and is never rendered as an empty cell or `0`. Google's own `Breakout`/rising label is exported in its own source column and is never merged into the classifier's `signal_type` or `status`.

## Canonical Runtime Contract

Use canonical enums exactly in structured output. Do not invent aliases such as `candidate`, `strong candidate`, `reject`, `possible emerging`, or mixed labels such as `typo / modifier shift` in canonical fields.

`signal_type` must be exactly one of `net_new`, `breakout`, `emerging_variant`, or `unknown`.

`demand_history_type` must be exactly one of `newly_observed`, `preexisting`, `resurgent`, or `unknown`. A birth window is an evidence-backed bucket/month range from one long comparable series, not an absolute keyword birthday. A series whose first available buckets already contain sustained demand is `preexisting` with `birth_reason=before_available_history`; an isolated spike remains `unknown`.

`variant_subtype` must be exactly one of `new_expression`, `typo`, `modifier_shift`, or `unknown`.

`status` must be exactly one of `new_signal`, `watch`, `emerging`, `breakout`, `mature`, `noise`, or `insufficient_evidence`.

`route` must be exactly one of `selection_handoff`, `root_candidate_handoff`, `new_root_watchlist`, `monitor_only`, or `no_handoff`.

Human-readable commentary may describe strength or hypotheses, but it must not replace or redefine these canonical fields.

## Confirmed Classification vs Hypothesis

A hypothesis is not a confirmed classification.

If a query looks like it may be accelerating because product launches, new pages, community discussion, or category formation are increasing, but comparable temporal search-demand evidence is missing, record a hypothesis such as `possible_breakout` in commentary/evidence and keep `signal_type=unknown` unless another signal type is actually evidenced.

If comparable historical baseline plus persistent recent growth is not available, the skill must not emit `signal_type=breakout`.

If the evidence required by `classification-rules.md` is not established, the skill must not emit `status=emerging` or `status=breakout` merely because the term looks promising, commercially interesting, fresh, widely discussed, or under-supplied.

Use `new_signal`, `watch`, or `insufficient_evidence` according to the evidence actually available. In particular, supply-side freshness alone cannot confirm temporal search-demand growth.

`emerging_variant` requires both a semantic relationship to an existing expression and real temporal evidence for the new expression. A plausible wording shift without temporal evidence remains `signal_type=unknown` with a variant hypothesis in commentary.

## Types and States

Signal types: `net_new`, `breakout`, `emerging_variant`. Variant subtypes: `new_expression`, `typo`, `modifier_shift`.

States: `new_signal`, `watch`, `emerging`, `breakout`, `mature`, `noise`, `insufficient_evidence`.

Every classification returns a reason, evidence used, remaining unknown fields, confidence, and explicit state-change metadata when a previous state is supplied. Anchor events may strengthen interpretation but are never mandatory.

## Routing Discipline

Only `status in {emerging, breakout}` may produce `selection_handoff`, and only when the candidate maps to an existing valid root as required by `routing-rules.md`.

`new_signal` and `watch` must remain `monitor_only` when an existing root is known. They are not sent to `seo-keyword-selection` just because further keyword research would be useful.

`root_candidate_handoff` requires both confirmed `status in {emerging, breakout}` and a reviewable `root_candidate_hypothesis`. Otherwise retain the item in `new_root_watchlist`.

`mature`, `noise`, and `insufficient_evidence` produce `no_handoff` unless the routing rules explicitly preserve an unresolved root watch case.

Do not recommend a downstream route in prose that contradicts the canonical `route` field.

## Interactive Output

For an interactive scan, prefer a compact table or structured records. For every candidate expose at least:

`keyword | signal_type | variant_subtype | status | first_observed_at | growth_rate | persistence | source_count | volume | kd | cpc | intitle_results | metric_status | metric_compatibility_status | kgr_compatibility_status | kgr | root_relation | route`

Use `unknown` when a field is not supported by real evidence. Do not omit an unknown field merely to make the candidate look more complete.

After the records, separate candidates into confirmed `emerging`/`breakout`, `watch`, and `insufficient_evidence`. Do not create a separate informal bucket named `candidate`.

## Data Sources

v1 supports clean CSV/JSON ingestion contracts for Google Trends exports, Semrush trend/keyword exports, competitor sitemap diffs, demand-source feeds, manual exports, API responses, or external connectors. These contracts do **not** claim that any third-party source is being scraped or monitored automatically.
