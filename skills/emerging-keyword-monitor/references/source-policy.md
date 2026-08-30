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

Google Trends values are relative indexes and are normalized independently for each timeframe. `5y`, `12m`, `90d`, `30d`, and `7d` are separate comparable series: never compare their index values arithmetically or concatenate them. Preserve each timeframe's source URL, requested timeframe, actual bucket resolution, and evidence reference. Historical zero does not prove zero absolute searches, and the first non-zero point does not prove an absolute keyword birth date.

Google collection must use a genuinely isolated logged-out browser context/profile that is separate from the user's authenticated Google context. If that isolation cannot be established, collection is blocked; cookies must not be copied, deleted, or replaced with a temporary Google account. Related/Rising `Breakout` is retained as `google_rising_label` only and is not the monitor's canonical breakout classification.

## Semrush caution

Missing Semrush Volume/KD is data absence or lag. It is neither a negative gate nor positive evidence that a keyword is new.
