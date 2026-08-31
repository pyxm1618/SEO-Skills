# Data Contracts and Provenance

## Data-state rule

Every value is one of:

- **observed**: direct output from a real tool/source or manual observation;
- **calculated**: exact formula using observed inputs;
- **analysis**: interpretation/hypothesis;
- **unknown**: unavailable. Never coerce to `0`.

## Root handoff

Expected upstream fields when available:

`root | scope | demand_category | primary_intent | status | evidence_level | evidence_ref | why_relevant`

Only the root pool crosses the boundary. Never copy `root-library.csv` into this skill.

## Candidate keyword fields

Preserve as early as possible:

`keyword | domain | root | parent_seed | source | source_detail`

`source` may identify Google suggestions, Semrush ideas, competitor organic keywords, or AI expansion. AI-origin candidates must not be treated as observed-demand evidence until a real source confirms them.

## Metric fields

Normalized evaluator inputs:

- `volume`: monthly search volume; observed numeric or unknown.
- `difficulty` or `kd`: Semrush KD; observed numeric or unknown.
- `cpc`: observed numeric or unknown.
- `intitle_results`: manually observed Google `intitle:"keyword"` count or unknown.
- `serp_weak_points`: optional count of documented weak top-10 positions whose rank/URL match a candidate-bound, production-verified SERP receipt. Missing or unverified review remains unknown.
- `exclude_reason`: nonblank only for a documented manual exclusion such as brand navigation or semantic drift.

Optional pass-through fields include `intent`, `competition_level`, `trend`, `serp_notes`, `page_form`, and provenance fields.

## Calculated fields

The evaluator may add:

- `recall_pool`
- `exact_pool`
- `kd_band`
- `cpc_signal`
- `kgr`
- `kgr_signal`
- `serp_evidence_status`
- `kdroi`
- `mechanical_status`

These are calculations/classifications, never independent observations.

## SERP weak-point documentation

A weak point must be tied to an actual top-10 result and a reason. Valid examples can include:

- DR < 30 independent site when DR is actually observed;
- demonstrably new/low-authority site occupying the result;
- Reddit/Quora/forum/UGC result suggesting weak editorial supply;
- high-DR domain whose ranking inner page is demonstrably weak at page level;
- clear query-intent mismatch;
- materially weak tool/content experience;
- stale/outdated page where freshness matters.

An inner page is **not** weak merely because it is an inner page. Do not invent DR or page-level strength.

## `intitle` integrity

KGR numerator is the actually observed visible count from Google `intitle:"keyword"`. If exact observation is unavailable, use `unknown`. Never replace it with:

- Bing counts;
- unquoted/general Google result counts;
- API result-row counts;
- AI estimates;
- an inference from KD.

## Final table provenance

For serious finalists retain enough provenance to answer: “Where did this number/fact come from, and when was it observed?” File-level metadata is acceptable when every row comes from the same batch/source.

## Input validity and row status

Mechanical formulas must never run on impossible numeric inputs. Treat these as `invalid_row`, not as `unknown` and not as zero:

- `volume < 0`;
- KD outside `0..100`;
- `cpc < 0`;
- `intitle_results < 0` or non-integer;
- legacy `serp_weak_points` outside `0..10` or non-integer;
- NaN / Infinity / non-numeric values where a numeric value is supplied;
- blank keyword.

Missing values remain `unknown`; malformed values are invalid. Preserve `validation_errors` so the row can be repaired rather than silently discarded.

## Structured SERP weak evidence

`serp_weak_points` is a **calculated verified count**, not a trusted manual input. The evaluator derives it from `serp_weak_evidence` only after the active candidate's production `serp_review` receipt passes and each evidence item's rank/URL matches that receipt's real Top-10 row.

The entire SERP review is optional. Omitted evidence leaves `serp_weak_points=unknown` and a KD 40–50 candidate at `observe_serp`; it never creates a zero count, a production blocker, or an upgrade.

Each evidence item must contain:

`rank | url | weakness_type | observed_fact`

Rules:

- `rank` must be an integer from 1 to 10;
- `url`, `weakness_type`, and `observed_fact` must be nonblank;
- one rank can count at most once;
- `rank` and `url` must match the same result in the verified candidate-bound SERP receipt;
- malformed/partial evidence does not count;
- a legacy numeric `serp_weak_points` may be preserved as `reported_serp_weak_points` for audit, but never upgrades a KD 40–50 keyword by itself.

For CSV input, encode `serp_weak_evidence` as a JSON array string. For JSON input, it may be a native array.

## Metric provenance

Where available preserve:

`metric_source | metric_database | observed_at | metric_stage`

The evaluator emits `provenance_status=verified` only when all four are present; otherwise it emits `incomplete`. Provenance completeness does not itself prove the metric is authoritative for the current decision stage. For example, an Ideas-stage metric can be fully traceable but still require an Exact-stage refresh before final qualification.

Top-level JSON batch metadata may supply these fields to every row (`database` maps to `metric_database`; `generated_at` maps to `observed_at`).

## Duplicate handling

Normalize whitespace and case for duplicate detection. Preserve all rows because duplicate keywords may carry different source/provenance records, but emit:

- `duplicate_count`;
- `duplicate_warning`.

Do not silently deduplicate inside the evaluator. Downstream clustering/counting must account for duplicate warnings so duplicate rows do not inflate opportunity density.
