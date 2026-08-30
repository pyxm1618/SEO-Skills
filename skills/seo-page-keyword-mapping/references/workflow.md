# Workflow

Resume from the earliest unfinished stage. Do not redo verified work merely because a batch starts midstream. Mapping starts only after a selection-confirmed opportunity exists and the page universe is known.

## Stage 1 — Scope Contract

Define the mapping universe before page-scoped keyword evidence work:

- `page_id`, planned URL, entity/category name, aliases;
- target language(s), script(s), market(s), and business geography;
- parent/hub pages and any already-proposed child pages;
- available metric/SERP sources.

No page inventory means this is not yet a page-mapping task.

## Stage 2 — Page-scoped keyword evidence / normalization / ownership expansion

Use the confirmed opportunity plus known page/entity aliases and, when useful, multiple markets to normalize page-scoped query evidence and expand plausible ownership candidates. Preserve `source_seed`, source database, timestamp, and raw row.

This stage is **not** the owner of generic domain/root/Seed discovery. New reusable demand discovery routes through `seo-keyword-discovery`/`keyword-root-library`, not back into mapping.

**Rule:** `source_seed` is provenance only; it never establishes page ownership. Cross-page line queries, hubs/lists, brands, and semantic drift must not be assigned merely because they appeared under one seed.

## Stage 3 — Ownership Classification + Core Compression + SERP Fast Check

Compress the page-scoped pool into:

- `core` — plausible page-identity query;
- `intent` — same entity plus a task/modifier that can live in the cluster;
- `non_target` — brand/navigation, another entity, hub/list, semantic drift, or rejected query.

A modifier can be promoted to `core` when it disambiguates the entity and observed SERP results confirm the target entity intent.

Every final Core Candidate gets a **SERP Fast Check**: inspect enough live result titles/page types to confirm entity intent. Do not infer this from KD, Volume, or wording alone.

## Stage 4 — Real Metrics

Acquire observed metrics only: query demand, market demand, KD, CPC/bids if available, and SERP facts. `unknown` stays unknown; it is not zero.

If a new/current Semrush acquisition is needed, it may use only the authenticated same-origin `sem.3ue.com` project collector. Metric provenance must identify source, market/language scope, date, and method. Do not combine incompatible scopes silently.

## Stage 5 — Demand Modeling

Keep three concepts separate:

1. **Core Keyword Demand** — observed demand for the selected Primary query in the target scope.
2. **Cluster Observed Demand** — sum of deduplicated, ownership-confirmed, observed query strings assigned to the same page and compatible metric scope.
3. **Demand Scope Aggregation** — explicit market/language/script aggregation rules used to produce the target-scope metric.

Cluster Observed Demand is a comparison signal, not a traffic prediction.

## Stage 6 — Mapping + Cannibalization

Select Primary from ownership-confirmed, SERP-fast-confirmed Core Candidates. Preserve Secondary Core queries and Intent rows on the same page when they share ownership.

Use SERP Deep Review when candidates are close, intent is ambiguous, a hub/entity boundary is unclear, language contamination is suspected, or an independent child URL is proposed.

Cannibalization checks are limited to the current mapping universe: entity pages, relevant parent/hub pages, and proposed child pages. Check exact ownership collisions, high-overlap page pairs, and parent-child splits with overlapping SERPs.

## Stage 7 — Architecture

Classify owned queries as:

- Primary;
- Secondary Core;
- Content Module;
- Independent URL Candidate;
- Reject / unresolved.

Prefer a content module when parent/child SERPs overlap strongly. Raise an independent URL candidate only when observed evidence supports distinct user task, independent content, and meaningful demand. Do not use a universal Volume or KD threshold across industries.
