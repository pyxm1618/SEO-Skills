# Semrush Relay Live Acceptance Report (V4 Live Re-Audit)

## 1. Relay Origin & Authentication Probe

### Host Probe
- **Target Host**: `sem.3ue.com` (Same-Origin Relay)
- **Direct HTTP Probe**: Returned HTTP 302 Redirect to `https://sem.3ue.com/gmitm.redirect.dash?msg=%E7%99%BB%E5%BD%95%E8%BF%87%E6%9C%9F%E6%88%96%E6%97%A0%E6%95%88%2C%E8%AF%B7%E9%87%8D%E6%96%B0%E7%99%BB%E5%BD%95`
- **Browser CDP Relay Bridge**: Requires `SEO_BROWSER_CDP_URL` to attach to authenticated browser session and execute same-origin `fetch()` with credentials. Since CDP is unavailable on port 9222, relay collector cannot bridge into active session.

```bash
$ curl -s -I https://sem.3ue.com/
HTTP/2 302 
location: https://sem.3ue.com/gmitm.redirect.dash?msg=%E7%99%BB%E5%BD%95%E8%BF%87%E6%9C%9F%E6%88%96%E6%97%A0%E6%95%88%2C%E8%AF%B7%E9%87%8D%E6%96%B0%E7%99%BB%E5%BD%95
```

---

## 2. Policy Enforcement & Zero-Fallback Discipline

- **Semrush Official API**: Explicitly forbidden by policy (`Official API used: NO`).
- **Alternative Provider (Ahrefs, DataForSEO, Moz, Bing, WebSearch)**: Explicitly forbidden by policy (`Alternative provider used: NO`).
- **Relay Unauthenticated / Bridge Unavailable**: Fail-closed status is `BLOCKED`.

---

## 3. Stages Evaluated

| Stage | Mode | Live Result | Reason |
|---|---|---|---|
| Discovery Ideas | `semrush_ideas` | **BLOCKED** | CDP browser bridge unavailable / direct session unauthenticated |
| Exact Metrics | `semrush_exact` | **BLOCKED** | CDP browser bridge unavailable / direct session unauthenticated |

---

## 4. Verdict

- **Semrush authenticated relay**: `BLOCKED`
- **Semrush Ideas Live**: `BLOCKED`
- **Semrush Exact Live**: `BLOCKED`
- **Official API used**: `NO`
- **Alternative provider used**: `NO`

