# Semrush Relay Live Acceptance Report (V4)

## 1. Relay Origin & Authentication Probe

### Host Probe
- **Relay Origin**: `https://sem.3ue.com/`
- **Session Status**: Probe returned HTTP 302 Redirect to `gmitm.redirect.dash?msg=登录过期或无效,请重新登录`

```bash
$ curl -s -I https://sem.3ue.com/
HTTP/2 302 
location: https://sem.3ue.com/gmitm.redirect.dash?msg=%E7%99%BB%E5%BD%95%E8%BF%87%E6%9C%9F%E6%88%96%E6%97%A0%E6%95%88%2C%E8%AF%B7%E9%87%8D%E6%96%B0%E7%99%BB%E5%BD%95
```

---

## 2. Policy Enforcement

- **Official Semrush API**: Explicitly forbidden by policy.
- **Third-party fallback (Ahrefs, DataForSEO, Moz, Bing, WebSearch)**: Explicitly forbidden by policy.
- **Relay Unauthenticated**: Fail-closed status must be `BLOCKED`.

---

## 3. Stages Evaluated

| Stage | Mode | Live Result | Reason |
|---|---|---|---|
| Discovery Ideas | `semrush_ideas` | **BLOCKED** | Relay authentication session expired / absent |
| Exact Metrics | `semrush_exact` | **BLOCKED** | Relay authentication session expired / absent |

---

## 4. Verdict

- **Semrush Relay Live**: `BLOCKED`

