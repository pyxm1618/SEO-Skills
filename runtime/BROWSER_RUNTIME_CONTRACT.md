# Live Browser Runtime Contract

This is the shared runtime contract for every Skill that uses `runtime/collectors/google_live_collector.py` or the persistent Chrome/CDP launchers. It documents the browser behavior implemented by PR #37; it does not change SEO acquisition, classification, thresholds, routing, KGR, KDRoi, or evidence semantics.

## Browser topology

Live collection uses dedicated persistent **headful** Chrome instances, not the user's normal browser profile.

- `SEO_GOOGLE_CDP_URL` points to the dedicated logged-out Google profile, normally started with `python3 runtime/start_live_browser.py --google` on port 9224.
- `SEO_BROWSER_CDP_URL` points to the separate general/Semrush browser profile.
- On macOS the launcher uses background activation (`open -g`) so starting the dedicated Chrome must not steal the user's foreground application or switch Spaces.
- The browser remains a real visible/headful browser. Background means “do not activate it automatically”, not “make it inaccessible”. The user may switch to it manually at any time.
- Do not silently replace this production path with headless mode. A headless variant requires separate evidence-quality validation before it can become a production default.

## Google worker page lifecycle

The Google collector reuses one persistent **worker page** in the dedicated context instead of creating a new tab for every request.

- Autocomplete, PAA/Related, intitle, SERP, Trends Related, and Trends Timeline navigate the worker page for each acquisition.
- Normal operation must not produce tab growth proportional to keyword count.
- `check_page_leak_guard` fails with `BLOCKED: browser_page_leak` when page count exceeds the runtime safety limit; a batch must not continue opening pages after that condition.
- Trends collectors register a temporary `response` listener only for the current request and remove it in `finally`, including ordinary error and human-intervention paths. A previous keyword's listener must not observe later requests.
- A page created only because the context had no page may be cleaned up according to the collector lifecycle; the persistent dedicated worker remains available for subsequent subprocess calls.

## Human takeover: NEEDS_HUMAN

CAPTCHA, Google unusual-traffic pages, verification challenges, and an **existing unresolved blocker** are control-flow conditions, not ordinary “skip this keyword” errors.

- The collector emits structured `NEEDS_HUMAN` information and exits with **exit code 3**.
- `run_emerging_radar.py` treats the same signal as a top-level control exception. Related discovery, supplemental acquisition, and timeline collection must re-raise it rather than converting it to an ordinary blocker and continuing the batch.
- The blocker page and dedicated Chrome process are preserved. Do not close the problem tab, kill the browser, or clear the profile merely to make the run continue.
- If any unresolved blocker page already exists in the Google context, do not create a fresh page to bypass it. Return `NEEDS_HUMAN` for the existing page.
- Do not call `bring_to_front`, activate Chrome, switch macOS Spaces, or otherwise force the browser into the foreground. Tell the user that manual intervention is required; the user switches to the dedicated Chrome themselves, completes the challenge, then retries/continues the workflow.

## Fail-closed evidence behavior

Google page inspection must **fail closed**. If the collector cannot confirm the expected origin, body/DOM, payload, or other required evidence, it reports `BLOCKED` or `NEEDS_HUMAN` as appropriate; it does not interpret an unreadable page as a successful empty result.

The dedicated Google profile remains logged out. Google authentication cookies block collection. A persistent profile may retain non-authentication cookies and prior human verification state; do not copy the user's normal Google profile or clear cookies on every run.

There is no hosted WebSearch, Bing, generic search API, or **HTTP fallback** that can satisfy formal Google evidence. Do not replace Playwright/CDP collection with direct HTTP scraping to avoid browser lifecycle rules.

## Operational rule for Skills

`seo-keyword-discovery`, `emerging-keyword-monitor`, and `seo-keyword-selection` all consume this same runtime contract whenever they request live Google evidence. Their own `SKILL.md` files define which evidence is required and what downstream decision is allowed; this file defines only how the shared browser runtime is operated and how browser blockers are handled.
