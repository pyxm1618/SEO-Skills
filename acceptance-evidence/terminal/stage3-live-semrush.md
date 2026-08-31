# 阶段三 Live 验收 4/7 · Semrush Ideas + Exact

日期：2026-08-30
工作树：`/Users/milushangdi/Downloads/SEO-Skills-claude`
分支：`claude/claude-code-host`

结论：**PASS**。

## 独立登录浏览器与同源探针

Semrush 使用 `.seo-run/browser-profile` 和 CDP `http://127.0.0.1:9334`，与 Google 9333
完全分离：

```bash
~/.venvs/seo-skills/bin/python runtime/start_live_browser.py --port 9334
```

```text
semrush_connect_same_origin=PASS
hostname=sem.3ue.com
title=Semrush Folders: Take control of your data
context_is_contexts0=True
```

登录不是由标题推断：同一会话的已登录控制台截图位于
`.seo-run/stage3-live/semrush/authenticated-home-login-probe.png`
(`2633676cc22b4223910734756cccf92c6b7e609e8d710404aef2355187a9714b`)，随后 UI 真实触发的
`ideas.GetKeywords` 与 `keywords.GetInfo` 都返回 HTTP/RPC success。

## 上层入口定位与命令

仓库入口来自 `seo-keyword-selection` Stage 5/6：当前 UI 网络捕获生成 descriptor，
再由 `runtime/collectors/semrush_relay_collector.py` 执行同源 fetch。没有凭历史 endpoint 拼命令。

```bash
SEO_BROWSER_CDP_URL=http://127.0.0.1:9334 \
~/.venvs/seo-skills/bin/python runtime/collectors/semrush_relay_collector.py \
  --request .seo-run/stage3-live/semrush/ideas-wedding-calculator-request.json \
  --output .seo-run/stage3-live/traditional/semrush-ideas-wedding-calculator.json \
  --raw-output .seo-run/stage3-live/traditional/semrush-ideas-wedding-calculator.raw.json

SEO_BROWSER_CDP_URL=http://127.0.0.1:9334 \
~/.venvs/seo-skills/bin/python runtime/collectors/semrush_relay_collector.py \
  --request .seo-run/stage3-live/semrush/exact-wedding-calculator-request.json \
  --output .seo-run/stage3-live/traditional/semrush-exact-wedding-calculator.json \
  --raw-output .seo-run/stage3-live/traditional/semrush-exact-wedding-calculator.raw.json
```

原始结果摘要：

```text
Ideas: seed=wedding calculator, rows=30, metric_database=us, exit=0
Exact: keyword=wedding calculator, volume=320, kd=22, cpc=1.7,
       trend_points=12, metric_database=us, exit=0
Continuing Exact: keyword=wedding cost calculator, volume=720, kd=18, cpc=1.65,
                  trend_points=12, metric_database=us, exit=0
```

Production validators：`discovery_semrush_ideas PASS`；两条 `stage6_exact PASS`；均为
`complete_count=1`、`blocked_count=0`。

## JSON 与哈希

| 证据 | 路径 | SHA256 |
| --- | --- | --- |
| Ideas normalized | `.seo-run/stage3-live/traditional/semrush-ideas-wedding-calculator.json` | `a874593c6c2e730f19c08c37c466d5af0d518a35fa85660ceb9bb0854bf3c428` |
| Exact normalized | `.seo-run/stage3-live/traditional/semrush-exact-wedding-calculator.json` | `b1f7f500ac0e590948dc3575f281c179deef633bec4ecbacc99351edf40cf7dc` |
| continuing Exact normalized | `.seo-run/stage3-live/traditional/semrush-exact-wedding-cost-calculator.json` | `c6f348e089fefd4d64d85eba8dd179562862ceb78deec7542d396182054f6fd5` |

每份 normalized JSON 都有同名 `.raw.json`、collector receipt，并绑定最小化的 current network
capture。捕获文件权限为 `0600` 且位于 gitignored `.seo-run`；文档未复制会话 token。

未调用官方 Semrush API、Ahrefs、relay 以外 provider、mock 或 fallback。
