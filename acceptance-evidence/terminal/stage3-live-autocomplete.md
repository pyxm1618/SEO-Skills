# 阶段三 Live 验收 1/7 · Google Autocomplete

日期：2026-08-30
工作树：`/Users/milushangdi/Downloads/SEO-Skills-claude`
分支：`claude/claude-code-host`

结论：**PASS**。

## 双浏览器中的 Google 隔离探针

Google 使用独立 CDP `http://127.0.0.1:9333`；Semrush 使用
`http://127.0.0.1:9334`。两者同时传给 collector，确认 Google 专用 URL 与通用 URL 不同。

通过 `google_live_collector.connect()` 实测：

```text
google_connect=PASS
total_cookies=1
google_domain_cookies=1
google_auth_cookies=0
browser_contexts=1
dedicated_context_is_contexts0=True
```

关键门禁是 Google **认证** cookie 必须为 0；实测为 0。总 cookie 中的 1 个不是
`GOOGLE_AUTH_COOKIE_NAMES`，未触发认证上下文拒绝。

## 命令与原始输出

```bash
SEO_GOOGLE_CDP_URL=http://127.0.0.1:9333 \
SEO_BROWSER_CDP_URL=http://127.0.0.1:9334 \
~/.venvs/seo-skills/bin/python runtime/collectors/google_live_collector.py autocomplete \
  --seed 'wedding calculator' --country US --language en \
  --evidence-dir .seo-run/stage3-live/google/evidence \
  --output .seo-run/stage3-live/traditional/google-autocomplete-wedding-calculator.json
```

```text
exit=0
seed=wedding calculator
suggestion_count=10
country=US
language=en
source=google_autocomplete
observed_at=2026-08-30T14:49:15.010973+00:00
evidence_receipt_ref=.seo-run/stage3-live/traditional/google-autocomplete-wedding-calculator.receipt.json
```

Production validator：`discovery_autocomplete`，`status=PASS`，`complete_count=1`，
`blocked_count=0`。

## JSON、截图与哈希

| 证据 | 路径 | SHA256 |
| --- | --- | --- |
| normalized JSON | `.seo-run/stage3-live/traditional/google-autocomplete-wedding-calculator.json` | `212fb048f08d64501046c7bcf40b7367a2def8f81d8a28b04f6927c3fd3a0576` |
| visible dropdown screenshot | `.seo-run/stage3-live/google/evidence/autocomplete-wedding-calculator.png` | `299e67587b551d011d189d41b16bd353e0dfabd73183e61d3400eea6b20a521f` |
| structured observation | `.seo-run/stage3-live/google/evidence/autocomplete-wedding-calculator.json` | 由 receipt 绑定 |
| validation report | `.seo-run/stage3-live/traditional/validation/discovery-autocomplete.json` | 对应 receipt 在同目录 |

未使用 WebSearch、API、mock、合成建议或替代 provider。
