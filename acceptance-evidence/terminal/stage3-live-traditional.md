# 阶段三 Live 验收 6/7 · Traditional workflow

日期：2026-08-30
工作树：`/Users/milushangdi/Downloads/SEO-Skills-claude`
分支：`claude/claude-code-host`

结论：**FAIL**。早期淘汰分支与 continuing candidate 的 Exact 门已真实执行；continuing
candidate 在下一 intitle 门遇到 Google `/sorry/`，而该 blocker 不满足 AEB 六条件，故不能把
“走到外部允许的位置”压成 PASS。

## 显式候选台账

| candidate | Exact 门 | evaluator | 后续 |
| --- | --- | --- | --- |
| `wedding calculator` | PASS：Volume 320 / KD 22 / CPC 1.7 | `principle_eliminate_volume` | 按 Traditional 规则应在 Exact 后确定性早退 |
| `wedding cost calculator` | PASS：Volume 720 / KD 18 / CPC 1.65 | `do_candidate`（Exact stage） | intitle collector BLOCKED；无 continuing KGR/SERP |

两个 candidate 的 identity 分别绑定到 production validator：

```text
cand_wedding_calculator_early -> stage6_exact PASS, candidate_keyword=wedding calculator
cand_wedding_cost_calculator_continue -> stage6_exact PASS, candidate_keyword=wedding cost calculator
```

全局真实证据：

- `discovery_autocomplete PASS`：10 条 Google 可见建议；
- `discovery_semrush_ideas PASS`：30 条当前 `sem.3ue.com` Ideas；
- 两条 `stage6_exact PASS`：当前 US Exact；
- continuing intitle：`BLOCKED: Page.wait_for_selector ... #result-stats`，exit 2；
- continuing SERP：未执行，保留为未满足，不用早退 candidate 的独立 KGR/Trends 冒充。

独立 KGR 与 Trends 验收确实使用了 `wedding calculator` 的真实证据，但它们属于第 5/7 与 3/7
验收，不改变 Traditional 的早退顺序，也不补 continuing candidate 的缺口。

## 证据路径

| 证据 | 路径 | SHA256 / 状态 |
| --- | --- | --- |
| early evaluator | `.seo-run/stage3-live/traditional/evaluation-early.json` | `8ccb7b48138a8c8f0f724fed5742a14e285aea7507fac419a0c264b0653539dc` |
| continuing evaluator | `.seo-run/stage3-live/traditional/evaluation-continuing.json` | `f2ded151b7da0446f2ae0f4410ace04f88d9f582aefea440bfa8c77efc173e5b` |
| early Exact validation | `.seo-run/stage3-live/traditional/validation/early-exact.json` | PASS |
| continuing Exact validation | `.seo-run/stage3-live/traditional/validation/continuing-exact.json` | PASS |
| continuing intitle output | `.seo-run/stage3-live/traditional/google-intitle-wedding-cost-calculator.json` | **不存在（fail closed）** |
| Google blocker diagnostic | `.seo-run/stage3-live/google/serp-sorry-diagnostic.json` | `ab8866c561a3ff072900851991a8264d05b79bf99ab96be26b802255e2c94ab5` |
| first-page SERP screenshot | `.seo-run/stage3-live/google/evidence/serp-wedding-calculator.png` | `7cc6cb837c9d149641b47f97aa7b74ecac72b8ad0d9118a90ffbb1094c9ec398` |

没有 mock、合成数据、手写指标、官方 API 或 provider 降级；失败保持失败。
