# Source and Ingestion Policy

## Supported ingestion model

v1 is source-agnostic. It accepts normalized CSV/JSON produced by manual exports, API responses, environment-backed adapters, or external connectors.

Priority source families include:

1. Google Trends observations/exports;
2. Semrush trend or keyword exports;
3. competitor sitemap/page-set diffs;
4. demand-source feeds such as query, community, marketplace, or product-release feeds.

Support for an input contract is **not** a claim of live automated collection.

## No embedded authentication

Never commit cookies, API tokens, passwords, Google/Semrush credentials, relay credentials, session IDs, or private connector secrets. Authentication belongs in environment variables or external connector configuration that is not stored in this repository.

## Provenance

Every observation should answer: where did it come from, when was it observed, which market/country does it represent, what window does it cover, and what unit is the signal measured in?

Missing provenance is recorded as incomplete. It does not become verified through inference.

## Source independence

`source_count` counts unique source identities, not rows and not multiple series from the same source. Cross-source evidence may raise confidence, but the monitor does not use a fixed `N-of-M signals = build` rule.

## Google Trends caution

Google Trends values are relative indexes. A historical zero does not prove absolute search Volume was zero, and the first non-zero point does not prove an absolute keyword birth date.

## Semrush caution

Missing Semrush Volume/KD is data absence or lag. It is neither a negative gate nor positive evidence that a keyword is new.
