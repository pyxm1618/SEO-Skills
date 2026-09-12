# Source and Ingestion Policy

## Supported ingestion model

The monitor may ingest normalized historical/current evidence from Google Trends, Semrush evidence, competitor page-set diffs, or other demand-source feeds. Input compatibility is not a claim that a source is automatically collected.

This policy does not change temporal thresholds or classifier meaning.

## Live Google browser contract

Live Google collection follows `runtime/BROWSER_RUNTIME_CONTRACT.md` and the dedicated Trends collector for Trends Related/Timeline.

For every Trends request:

- response evidence must be bound to the current keyword, market, timeframe, and expected request/endpoint;
- observing some other successful `widgetdata` response is insufficient;
- raw response evidence is persisted before required screenshot capture;
- screenshot capture is bounded and may be retried at most once after the initial attempt;
- valid raw data plus failed required screenshot is `data_acquired + pending_evidence`, not verified production evidence;
- a verified source response that genuinely contains no timeline data is `valid_no_data` and must not be conflated with transport failure or `payload_not_observed`.

CAPTCHA, unusual traffic, verification challenges, or unresolved browser blockers produce `NEEDS_HUMAN`. Stop dependent work immediately and preserve the browser/blocker state. Do not switch to headless or direct HTTP merely to bypass the challenge.

Repeated systemic collection failures trigger the configured circuit breaker. Remaining work is recorded as `not_attempted / collection_circuit_open` rather than continuing a known-broken batch.

## Domain admission before temporal interpretation

Source acquisition does not by itself make a term relevant to the monitored domain.

Every candidate from Rising, Autocomplete, Semrush supplemental discovery, or carry-forward passes the same domain-relation gate:

- `in_scope`
- `out_of_scope`
- `unknown`

Generic token overlap is not sufficient for `in_scope`. Ambiguous candidates remain traceable as `unknown` and do not enter formal classification/delivery.

## New/current Semrush acquisition

Whenever the monitor needs a **new/current** Semrush observation, the allowed transport is the current authenticated same-origin session at `https://sem.3ue.com/` through the existing relay collector.

The Radar accepts repeatable `--semrush-request PATH` descriptors captured for exact seeds. Descriptors are not rewritten. Unmatched anchors remain without Semrush supplemental evidence rather than falling back to another provider.

Do not silently substitute the official Semrush API, Ahrefs, another provider, or an AI estimate.

## No embedded authentication

Never commit cookies, API tokens, passwords, Google/Semrush credentials, relay credentials, session IDs, or private connector secrets. Live collectors attach only to already-authorized browser/session infrastructure allowed by the repository runtime contract.

## Provenance

Every admissible observation should answer:

`source | source_type | source_url | observed_at | market/country | time_window | signal_unit | evidence_ref`

Missing provenance remains incomplete. It is never repaired through inference.

Evidence acquisition state and evidence verification state are separate. A payload can exist while verification is still pending.

## Source independence

`source_count` counts unique source identities, not rows and not multiple windows from the same provider.

Cross-source evidence may raise confidence, but there is no fixed `N-of-M signals = build` rule.

## Google evidence artifact identity

Google evidence filenames use collision-safe deterministic identity components. Readable slugs are convenience only and are not authoritative identity keys.

## Google Trends caution

Google Trends values are relative indexes normalized independently for each timeframe. `5y`, `12m`, `90d`, `30d`, and `7d` are separate comparable series. Never concatenate or arithmetically compare indexes across those windows.

Historical zero does not prove zero absolute searches. The first non-zero point does not prove absolute keyword birth.

Google Related/Rising `Breakout` is source metadata only (`google_rising_label`). It does not directly set the monitor's canonical breakout classification.

## Semrush and Selection metric caution

Missing Semrush Volume/KD/CPC is data absence or lag. It is neither negative evidence nor proof that a keyword is new.

Emerging does not fabricate Selection-owned commercial metrics. Missing Selection fields remain unknown until the Selection process obtains real compatible evidence.
