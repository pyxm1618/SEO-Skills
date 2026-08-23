# Root Library Taxonomy

This file defines the schema, lifecycle, evidence semantics, and validation rules for `root-library.csv`.

## Contents

- Core definition
- Lifecycle status
- Evidence levels
- Scope
- Root types
- Demand categories
- Primary intents
- CSV fields
- Deduplication
- Promotion and deprecation

## Core definition

A **keyword root** is a reusable demand family capable of generating multiple natural search queries. A root may be a functional suffix (`calculator`), a query pattern (`best time to visit`), a resource form (`worksheet`), or a domain-specific demand family (`dream meaning`). It is not limited to one-word tool suffixes.

Presence in this library means only that the root is worth retaining as a demand-discovery asset. It does **not** mean any keyword or product opportunity has passed Volume, KD, CPC, KGR, trend, or SERP validation.

## Lifecycle status

| status | meaning |
|---|---|
| `candidate` | Retained hypothesis or sourced candidate. Do not treat as routine reusable demand evidence yet. |
| `active` | Accepted reusable root with at least L1 provenance and natural-query examples. It may be used for exploration but is not real-demand verified. |
| `verified` | Root backed by L2/L3 real keyword, SERP, site-keyword, repeated-domain, or monetization evidence. |
| `deprecated` | Retained for history but should not be proposed unless explicitly requested. |

**Hard rule:** `verified` requires `L2` or `L3`. A published root list alone can support `active/L1`, never `verified`.

## Evidence levels

| level | meaning |
|---|---|
| `L0` | AI/analyst hypothesis or undocumented internal curation only. |
| `L1` | Traceable published root source or documented recurring-demand research. Provenance is real, but demand has not yet been verified with real keyword/SERP/site data. |
| `L2` | Recurring demand observed in real keyword-tool data, real SERP evidence, or an actual site's organic-keyword/page set. |
| `L3` | Repeated evidence across multiple independent domains/sites and/or credible monetization evidence. |

Every `L1+` row must have an `evidence_ref`. `L2/L3` rows must also state the observed evidence in `validation_basis`. Unknown evidence remains unknown; do not promote by inference.

## Scope

- `universal`: transfers naturally across multiple unrelated domains.
- `domain`: meaningful mainly inside one or more named domains.

A `domain` root must not use `applicable_domains=all`.

## Root types

`root_type` is a controlled enum. Add a new type only by updating both this taxonomy and the deterministic validator.

- `functional_suffix` — calculator, generator, checker, finder, editor.
- `informational_pattern` — meaning, definition, explained, signs.
- `question_pattern` — what is, what does, why, how to.
- `comparison_pattern` — vs, comparison, alternatives.
- `decision_pattern` — best, worth it, best time to visit.
- `planning_pattern` — checklist, itinerary, timeline.
- `resource_format` — worksheet, printable, pdf, flashcards.
- `resource_pattern` — database, directory, download, guide-like resource demand.
- `local_pattern` — near me / local discovery patterns.
- `time_pattern` — today, tonight, this weekend, timing patterns.
- `domain_topic` — mortgage, bitcoin halving, family tree.
- `domain_pattern` — dream about, dog age calculator, travel itinerary.
- `topic_or_modality` — image, audio, anime; usually candidate until demand evidence exists.
- `calculation_pattern` — estimate/calculation structures that are not simply suffixes.
- `commercial_pattern` — cost, price, salary, fee/rate structures.
- `content_pattern` — recurring content-form demand structures.
- `discovery_pattern` — find/discover/browse structures.
- `identity_pattern` — name, identity, origin, personal-type structures.
- `interactive_pattern` — quiz/game/interactive experience structures.
- `knowledge_pattern` — formula/chart/reference knowledge structures.
- `learning_pattern` — practice, tutorial, study structures.
- `query_modifier` — free, online, best-like modifiers when retained as roots.
- `relationship_pattern` — compatibility, relationship-question structures.
- `route_pattern` — origin/destination or route demand structures.
- `technology_modifier` — AI or technology-specific query modifiers.
- `candidate_pattern` — sourced pattern not yet classified strongly enough for a narrower type.

Do not create a new type when an existing type fits.

## Demand categories

`demand_category` is a controlled user-job enum:

`access`, `analyze`, `build`, `calculate`, `check`, `compare`, `content`, `convert`, `create`, `decide`, `discover`, `estimate`, `evaluate`, `find`, `generate`, `identify`, `interpret`, `learn`, `location`, `lookup`, `manage`, `measure`, `navigate`, `organize`, `other`, `plan`, `predict`, `price`, `relationship`, `replace`, `resource`, `simulate`, `technology`, `time`, `track`, `transfer`, `transform`, `understand`, `visualize`.

If a new category is truly necessary, update both this taxonomy and the validator in the same change.

## Primary intents

Allowed values:

- `tool`
- `informational`
- `commercial`
- `resource`
- `interactive`
- `mixed`

These are broad root-level intent labels, not substitutes for keyword-level SERP intent validation.

## CSV fields

- `root_id`: stable slug identifier; unique; must equal the deterministic slug of `root`.
- `root`: lowercase canonical root; unique.
- `canonical_pattern`: reusable query form, using `x`/`y` where useful; unique in the library.
- `aliases`: semicolon-separated non-canonical variants. An alias must not also exist as another canonical root.
- `scope`: `universal` or `domain`.
- `root_type`: controlled structural type above.
- `demand_category`: controlled user-job category above.
- `primary_intent`: controlled root-level intent above.
- `applicable_domains`: semicolon-separated domains or `all` for universal roots.
- `example_keywords`: semicolon-separated natural examples. They demonstrate form only and are not metric claims.
- `status`: lifecycle state.
- `evidence_level`: `L0`–`L3`.
- `validation_basis`: concise statement of what the evidence actually establishes.
- `evidence_ref`: durable URL or in-skill reference supporting `L1+` evidence.
- `source_name`: human-readable provenance label.
- `source_url`: public source URLs when applicable; multiple URLs separated by ` | `.
- `added_at`: ISO date.
- `last_verified_at`: ISO date for `verified`; blank otherwise unless an explicit re-verification occurred.
- `notes`: caveats and lifecycle notes.

## Deduplication

Before adding a root:

1. Normalize lowercase, whitespace, punctuation, and obvious morphology.
2. Search `root`, `aliases`, and `canonical_pattern`.
3. Prefer aliases when morphology differs but demand is materially the same.
4. Do not store a term as both an alias and a separate canonical root.
5. Keep separate roots only when they behave as materially different search patterns.
6. Do not reuse an identical `canonical_pattern` for two roots; refine the narrower pattern instead.

## Promotion rules

### Candidate → Active

Requires all of:

1. `L1+` traceable provenance;
2. a coherent repeatable demand pattern;
3. at least one natural example query (preferably two or more);
4. no brand/navigation dependence that dominates the root.

### Active/Candidate → Verified

Requires `L2+` real evidence showing a recurring family, not merely a single invented combination. Suitable evidence includes:

1. multiple real keyword-tool queries matching the pattern;
2. real SERP evidence showing repeated demand;
3. competitor organic-keyword evidence showing multiple traffic pages under the root;
4. repeated independent-domain/site reuse;
5. credible monetization evidence tied to the demand family.

Published root-list membership alone never satisfies this promotion.

## Deprecation

Deprecate, do not silently delete, when a root is consistently ambiguous, mostly brand/navigation demand, duplicates another canonical root, or repeatedly produces irrelevant expansions. Preserve the reason in `notes`.
