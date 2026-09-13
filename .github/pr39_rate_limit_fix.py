from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(rel, old, new):
    path = ROOT / rel
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{rel}: expected one target, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "runtime/collectors/google_trends_collector.py",
    '''    body = _body_text(page)\n    lowered = body.casefold()\n    if "unusual traffic" in lowered or "captcha" in lowered or "sorry/index" in str(getattr(page, "url", "")).casefold():\n''',
    '''    body = _body_text(page)\n    lowered = body.casefold()\n    if "too many requests" in lowered or lowered.lstrip().startswith("429.") or "error 429" in lowered:\n        raise RuntimeError("google_trends_rate_limited: HTTP 429 / Too Many Requests")\n    if "unusual traffic" in lowered or "captcha" in lowered or "sorry/index" in str(getattr(page, "url", "")).casefold():\n''',
)

replace_once(
    "skills/emerging-keyword-monitor/SKILL.md",
    '''CAPTCHA, unusual-traffic, verification challenges, or an unresolved browser blocker produce `NEEDS_HUMAN` and exit code 3. `NEEDS_HUMAN` is top-level control flow: stop dependent collection immediately, preserve the blocker/browser state, and require human resolution. Do not switch to headless or direct HTTP to bypass it.\n\nSystemic failures use a bounded circuit breaker. After the configured consecutive-failure limit, later work is ledgered as `not_attempted / collection_circuit_open` instead of continuing a broken batch.\n''',
    '''CAPTCHA, unusual-traffic, verification challenges, or an unresolved browser blocker produce `NEEDS_HUMAN` and exit code 3. `NEEDS_HUMAN` is top-level control flow: stop dependent collection immediately, preserve the blocker/browser state, and require human resolution. Do not switch to headless or direct HTTP to bypass it.\n\nHTTP 429 / `Too Many Requests` is an explicit rate-limit acquisition failure. It must fail closed and must never be converted into `valid_no_data`, an empty successful discovery, or a production PASS.\n\nSystemic failures use a bounded circuit breaker. After the configured consecutive-failure limit, later work is ledgered as `not_attempted / collection_circuit_open` instead of continuing a broken batch.\n''',
)

print("PR39 rate-limit fix applied")
