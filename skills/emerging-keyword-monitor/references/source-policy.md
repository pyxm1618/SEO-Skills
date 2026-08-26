# Source and Ingestion Policy

## Supported ingestion model

The monitor may ingest normalized historical/current evidence from Google Trends observations/exports, Semrush evidence, competitor page-set diffs, or other demand-source feeds. Input compatibility is not a claim that a source is automatically collected.

This source-policy change does **not** alter the emerging thresholds or state machine.

## New/current Semrush acquisition

Whenever the monitor needs a **new/current** Semrush observation, the only allowed transport is the current authenticated same-origin session at `https://sem.3ue.com/` through the project relay collector.

Do not fall back to an official Semrush API, API key/units, official connector, Ahrefs, another provider, or an AI estimate. Historical Semrush exports/evidence may still be evaluated for compatibility/freshness as existing evidence; they are not permission to create a different live acquisition path.

## No embedded authentication

Never commit cookies, API tokens, passwords, Google/Semrush credentials, relay credentials, session IDs, or private connector secrets. The live collector attaches only to an already-authorized browser session.

## Provenance

Every observation should answer where it came from, when it was observed, which market/country it represents, what window it covers, and what unit the signal uses. Missing provenance remains incomplete and is never repaired through inference.

## Source independence

`source_count` counts unique source identities, not rows and not multiple series from the same source. Cross-source evidence may raise confidence, but the monitor does not use a fixed `N-of-M signals = build` rule.

## Google Trends caution

Google Trends values are relative indexes. Historical zero does not prove zero absolute searches, and the first non-zero point does not prove an absolute keyword birth date.

## Semrush caution

Missing Semrush Volume/KD is data absence or lag. It is neither a negative gate nor positive evidence that a keyword is new.
