# 阶段三 · Emerging Radar 真实 Live 采集尝试

> **状态更新（2026-09-13）：本文件记录的 2026-08-30 `ACCEPTED_ENVIRONMENT_BLOCKER` 已被 PR #39 的本机独立 Chrome/CDP 成功复验所 supersede。当前 Emerging Radar Live 验收结论为 `PASS / GO`。历史 429 记录保留，作为 fail-closed 行为证据。PR #39 已合并到 `main`，merge commit：`06a05acd03bd7de0961afd1aa7e67a933a5221e7`。**

宿主：Claude Code
工作树：`/Users/milushangdi/Downloads/SEO-Skills-claude`
分支：`claude/claude-code-host`
提交：`902e8ae`（记录时）
日期：2026-08-30

结论：**`ACCEPTED_ENVIRONMENT_BLOCKER`，不是 `PASS`。**
真实关键词数据**未取得**。本次证明的是「外部依赖不可用时软件行为正确」，不构成对采集结果的验收。

---

## 环境准备

Playwright 与 gspread 装在专用虚拟环境 `~/.venvs/seo-skills`，未修改 Homebrew 系统 Python
（Homebrew Python 3.14 为 PEP 668 externally-managed，直接安装会被拒且有破坏风险）。

Google 浏览器隔离：全新 profile，独立调试端口，与用户日常浏览器完全分离。

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --remote-debugging-port=9333 \
  --user-data-dir=/tmp/seo-google-clean-profile \
  --no-first-run --no-default-browser-check --disable-sync
```

`SEO_GOOGLE_CDP_URL=http://127.0.0.1:9333`

### 登出隔离验证

设计要求 Google 采集上下文不得含任何 Google 认证 cookie，否则 `connect()` 必须失败。
实测通过 `google_live_collector.connect()`：

```
connect() succeeded -> isolation check passed
total cookies in context : 0
google.* cookies         : 0
google AUTH cookies      : 0 (must be 0)
browser contexts         : 1
```

---

## 执行命令

```bash
SEO_GOOGLE_CDP_URL=http://127.0.0.1:9333 \
~/.venvs/seo-skills/bin/python skills/emerging-keyword-monitor/scripts/run_emerging_radar.py \
  --domain wedding --anchor wedding \
  --max-depth 1 --per-anchor-limit 5 --max-candidates 5 \
  --run-dir .seo-run/emerging-radar-live \
  --output .seo-run/emerging-radar-live/run-summary.json
```

规模为刻意选择的最小值，用于先验证链路而非追求候选数量。

## 结果

```json
{"status": "BLOCKED", "candidate_counts": {"discovered": 0, "supplemental": 0, "unique_pool": 0, "classified": 0}}
```

阶段记录：

```json
"emerging_radar_run": {
  "status": "BLOCKED",
  "blocked_reason": "BLOCKED: Google Trends related result could not be confirmed; blocker_evidence_ref=...; blocker_screenshot_ref=..."
}
```

`recursive_edge_policy = google_trends_rising_only`，`supplemental_recursive = false`，anchor pool 记录完整。

### 外部阻塞的直接证据

采集器抵达的真实页面：`https://trends.google.com/trends/explore?geo=US&date=today+12-m&q=wedding`

页面正文（截图与 JSON 一致）：

```
429. that's an error.
we're sorry, but you have sent too many requests to us recently.
please try again later. that's all we know.
```

证据文件（`.seo-run/` 被 `.gitignore` 排除，此处留存哈希以便追溯）：

| 文件 | SHA256 |
| --- | --- |
| `evidence/trends-related-wedding-us-today-12-m-60211c496098-blocked.json` | `05703ed9def2008c93caf1ff11d2fdc08d49ec551230c19b5c58c5aef37553d8` |
| `evidence/trends-related-wedding-us-today-12-m-60211c496098-blocked.png` | `b6e1d80286065fcc2b3a14c63db8321a527836096bf3b87b383609c24e6c8213` |
| `run-summary.json` | `ad5b035232f0bed13431f2bebd04d83b7d128f8b25c5f253f5e0ffd80643f036` |

---

## `ACCEPTED_ENVIRONMENT_BLOCKER` 六项条件逐条核对

依据 `runtime/TRUST_BOUNDARY.md`。

| 条件 | 结果 | 依据 |
| --- | --- | --- |
| 真实采集器抵达目标外部源并捕获阻塞证据 | 满足 | 页面 URL 为 trends.google.com/trends/explore；JSON + 截图均已落盘 |
| 阻塞可证为外部原因而非解析/契约缺陷 | 满足 | Google 返回 429 限流页；页面无 Trends 结果结构可供解析 |
| 未使用 mock、合成数据、官方 Semrush API、替代 provider 或任何 fallback | 满足 | 候选数为 0；无任何替代来源被调用 |
| 采集器与下游工作流 fail closed，未伪造亦未带不完整证据前进 | 满足 | run `BLOCKED`；stage `BLOCKED` 并保留结构化 blocker |
| 有针对性回归测试覆盖相关 parser/extractor 行为 | 满足（**本次新增**） | 见下 |
| 无开放 P0/P1 表明有效源数据会被错误接受或门禁可被绕过 | 满足 | 363 passed；PR #24 四项 P1 已逐条复核并实测 |

### 第 5 项原本不满足，为此新增回归测试

记录本次尝试前，`tests/test_emerging_radar_google_safety.py` 覆盖了上下文隔离、cookie 拒绝、
延迟 payload 等待与解析器行为，但**没有任何测试覆盖「Google 返回错误页时必须 fail-closed 并留证」**
——即本次真实发生的场景。因此新增：

`test_related_fails_closed_with_evidence_when_google_returns_an_error_page`

断言：抛出 `RuntimeError` 且错误消息含 `blocker_evidence_ref=` 与 `blocker_screenshot_ref=`；
blocker JSON 落盘且 `observed_related_payload_count == 0`、`blocker == related_result_not_confirmed`、
`body_excerpt` 含 `429`；且 payload 中**不含** `related_queries` 字段
（即不得留下任何可能被误认为已观测需求的内容）。

在补上该测试之前，本条件不成立，故不得记录为 `ACCEPTED_ENVIRONMENT_BLOCKER`。

---

## 仍未完成（截至 2026-08-30）

- **真实关键词数据未取得。** 限流按 IP 计，需更换网络出口或等待其自然解除后重跑。
- 未取得 Trends timeline 真实序列，故 `estimated_birth_window` 的真实数据表现尚未验证
  （仅有构造数据与单元测试覆盖）。
- Google Sheet 导出已在真实表格上验证（见提交 `902e8ae`），但导入的是构造样例数据，
  尚未导入真实雷达输出。

---

## 2026-09-13 · PR #39 最终本机 Live Smoke 复验

PR：`#39 fix: reconcile Emerging Radar evidence and delivery`

- 验证 PR HEAD：`efee36022c6d85d482f4d04408a80a6465dd0edc`
- 基线：`645539a4c91aef66a5a715c54e12207f667f6c45`
- 本机仓库：`/Users/milushangdi/Projects/SEO-Skills`
- 独立未登录 Google Chrome profile：`/tmp/seo-google-smoke-profile`
- CDP：`127.0.0.1:9222`
- Google auth cookies：`[]`
- 无 HTTP fallback、mock、生产 Sheet 写入。

### Related 与 Timeline 真实采集

`runtime/collectors/google_trends_collector.py` 对 `keyword=perfume`、`market=US`、`timeframe=today 12-m` 的两类真实请求均通过严格 request binding：

| 采集 | 结果 |
| --- | --- |
| Related | exit 0；`verification_status=verified`；`request_binding_status=verified`；截图 `captured`；Evidence Receipt 签发；`collector=google_trends_collector`；`evidence_type=google_trends_related` |
| Timeline | exit 0；`verification_status=verified`；`request_binding_status=verified`；`acquisition_status=data_acquired`；54 个 weekly temporal points；截图 `captured`；Evidence Receipt 签发；`evidence_type=google_trends` |

Timeline 的 54 个真实周级时序点覆盖 2025-09-07 至 2026-09-13；receipt 同时绑定 temporal payload 与 screenshot artifact 及其 SHA256。

### Candidate cap 与全链对账

输入两个候选：`perfume`、`perfume for men`，设置 `max_total_candidates=1`。

实际 timeline acquisition 仅发生 1 次：

```text
actual_calls == [('perfume', 'today 12-m')]
```

Candidate Ledger：

- `cand_43e5c3ed9efedd8ebd1c` (`perfume`)：`data_acquired / verified / delivery_eligible=true`
- `cand_95eab1358126f25861bd` (`perfume for men`)：`not_attempted / batch_candidate_limit / verification_status=not_run / delivery_eligible=false / final_disposition=not_attempted_batch_limit`

Canonical reconciliation：

```text
candidate_ids   = 2
classified_ids  = 1
route_ids       = 1
route_ids == classified_ids
delivery_ids    = 1
delivery_ids <= route_ids
terminal_state_counts = {"monitor_record": 1, "not_attempted_batch_limit": 1}
identity_sha256 = 47d0d6ad7b1ad88eb07facdafd93077b11a7c269db1a8bd1f71437c2a9029eab
receipt_schema  = seo-emerging-pipeline/v1
```

Radar 与 canonical pipeline 的 `identity_sha256` 完全一致；未尝试采集的候选没有进入 delivery。

### 429 fail-closed 现场复核

全新 session 初次访问 Google Trends 曾实际收到 429。collector 正确中止并返回结构化：

```text
google_trends_rate_limited: HTTP 429 / Too Many Requests
```

没有把 429 降级为 `valid_no_data` 或空 PASS。调整 macOS WindowServer/后台窗口 occlusion 相关启动环境后，同一独立未登录 Chrome 模式成功完成 Related、Timeline、截图及 receipt 验证；没有使用 `bring_to_front`。

### 最终质量门禁

```text
python3 -m pytest -q
536 passed in 8.58s

python3 -m compileall -q skills runtime
PASS

git diff --check 645539a4c91aef66a5a715c54e12207f667f6c45...efee36022c6d85d482f4d04408a80a6465dd0edc
PASS
```

最终判定：**PASS / GO**。此前“真实关键词数据未取得 / Timeline 未实测”的缺口已关闭。

PR #39 随后转为 Ready 并合并到 `main`：

```text
merge commit = 06a05acd03bd7de0961afd1aa7e67a933a5221e7
```
