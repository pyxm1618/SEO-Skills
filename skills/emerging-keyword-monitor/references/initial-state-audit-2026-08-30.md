# Emerging Keyword Monitor 初始现状审计

## Source and baseline

- Base branch: `codex/seo-a-plus-scope-correction`
- Remote source: `origin/codex/seo-a-plus-scope-correction`
- Source SHA: `8b3a226327fe160ddec19a51ac47ba309897ff32`
- Repair branch: `codex/seo-emerging-radar-repair`
- Baseline command: `python3 -m pytest -q`
- Baseline result: `203 passed in 4.81s`
- Audit scope: `emerging-keyword-monitor` and its Google/Semrush runtime boundaries only

## Gap confirmation

1. **No domain-level active discovery.** `google_live_collector.py` accepts only the existing `autocomplete`, `intitle`, `serp`, and `trends` modes; the `trends` mode requires a concrete `--keyword` and there is no domain/anchor-pool or discovery pipeline.
2. **No Related/Rising acquisition.** The current Trends listener accepts only `/trends/api/widgetdata` payloads containing `default.timelineData` and emits timeline points. There is no parser or evidence contract for Related Queries, Rising, Breakout, or Related Topics.
3. **No controlled recursive expansion.** The repository has no radar traversal script, visited set, depth limit, per-anchor limit, or global candidate cap.
4. **`estimated_birth_window` is not computed.** Aggregation always emits `"estimated_birth_window": None`; `first_observed_at` is computed separately from the earliest available observation/carried timestamp.
5. **History is limited to short windows.** Aggregation exposes 7-day, 30-day, 90-day, and 12-month windows; it does not collect or analyze a verified long-history window of approximately five years.
6. **No independent demand-history type.** The current classifier can prevent `net_new` when available 12-month history is positive, but there is no `demand_history_type` or deterministic resurgent/preexisting inference.
7. **Google account isolation is absent.** Google `connect()` returns `browser.contexts[0]` directly, with no new isolated context, cookie/session inspection, or Google-auth rejection. Semrush likewise uses `browser.contexts[0]` for its authenticated relay page, so the two roles are not separated by collector code.
8. **Throttling is not a radar policy.** Existing fixed waits occur only inside autocomplete and Trends timeline capture; there is no configurable delay/jitter/concurrency policy for multi-query traversal.
9. **No Emerging Keyword Database or CSV export.** Existing scripts emit JSON/CSV to stdout and write collector evidence, but there is no run-level persistence/update script, incremental previous-state merge, or `.seo-run` database artifact.
10. **Stage contracts do not cover the new live stages.** `runtime/stage_contracts.json` has autocomplete, Semrush Ideas, handoff, Exact, intitle, SERP, and finalist timeline contracts, but no Trends Related, expanded timeline, or Emerging Radar run contract.

## Correct capabilities to preserve

- Unknown values remain missing; validation rejects malformed values and does not convert them to zero.
- Google live collection is browser/CDP-only and fails closed on CAPTCHA/unusual traffic.
- Current Semrush acquisition is restricted to the authenticated same-origin `https://sem.3ue.com/` relay; no official API or provider fallback is present.
- Provenance binding, comparable-series isolation, current signal enums/states, routing boundaries, and the prohibition on mutating `root-library.csv` remain in force.
- This audit does not modify `seo-keyword-selection` thresholds, `root-library.csv`, provider policy, or workflow-engine scope.

## Audit conclusion

The requested Emerging Keyword Radar capability is not present on the source branch. The repair can be implemented as additive, test-first units around the existing collectors/aggregator/classifier/router, with the existing fail-closed and provenance contracts retained. No live Google or Semrush acceptance was attempted during this audit.
