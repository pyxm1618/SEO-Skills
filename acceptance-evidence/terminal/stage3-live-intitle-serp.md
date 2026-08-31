# 阶段三 Live 验收 2/7 · Google intitle（SERP 可选）

日期：2026-08-30
工作树：`/Users/milushangdi/Downloads/SEO-Skills-claude`
分支：`claude/claude-code-host`

结论：**PASS**（按 2026-08-31 修订后的验收契约）。必需项 intitle 已通过；SERP 在真实
Google 第二页进入 `/sorry/index`，collector fail closed 但没有持久化该 blocker。该事实仍不
冒充 SERP PASS 或 `ACCEPTED_ENVIRONMENT_BLOCKER`，只是 SERP 现已明确为可选增强，不再进入
Live 验收分母，也不再让本条 intitle 验收失败。

## intitle：PASS

```bash
SEO_GOOGLE_CDP_URL=http://127.0.0.1:9333 \
SEO_BROWSER_CDP_URL=http://127.0.0.1:9334 \
~/.venvs/seo-skills/bin/python runtime/collectors/google_live_collector.py intitle \
  --keyword 'wedding calculator' --market US \
  --evidence-dir .seo-run/stage3-live/google/evidence \
  --output .seo-run/stage3-live/traditional/google-intitle-wedding-calculator.json
```

```json
{"keyword":"wedding calculator","intitle_results":493,"source":"Google","market":"US","observed_at":"2026-08-30T14:49:27.298159+00:00"}
```

- normalized JSON：`.seo-run/stage3-live/traditional/google-intitle-wedding-calculator.json`
  (`fb1438ef5865fc171a3064f1bec4e84e1f806a48d3c17d722b45df61cd2bba42`)
- screenshot：`.seo-run/stage3-live/google/evidence/intitle-wedding-calculator.png`
- receipt：`.seo-run/stage3-live/traditional/google-intitle-wedding-calculator.receipt.json`
- production validator：`intitle_observation PASS`，`complete_count=1`。

## 可选 SERP：UNAVAILABLE（不阻断）

```bash
SEO_GOOGLE_CDP_URL=http://127.0.0.1:9333 \
SEO_BROWSER_CDP_URL=http://127.0.0.1:9334 \
~/.venvs/seo-skills/bin/python runtime/collectors/google_live_collector.py serp \
  --keyword 'wedding calculator' --market US \
  --evidence-dir .seo-run/stage3-live/google/evidence \
  --output .seo-run/stage3-live/traditional/google-serp-wedding-calculator.json
```

观察结果：collector 在第一页截图后跟随真实 Google 下一页；浏览器最终落在
`https://www.google.com/sorry/index`，页面正文明确为异常流量验证页。collector 退出，未生成
`google-serp-wedding-calculator.json` 或 receipt。继续候选的单独 intitle 尝试也 fail closed：

```text
BLOCKED: Page.wait_for_selector: Timeout 10000ms exceeded.
waiting for locator("#result-stats")
exit=2
```

证据：

| 证据 | 路径 | SHA256 |
| --- | --- | --- |
| 第一页 SERP screenshot | `.seo-run/stage3-live/google/evidence/serp-wedding-calculator.png` | `7cc6cb837c9d149641b47f97aa7b74ecac72b8ad0d9118a90ffbb1094c9ec398` |
| preserved `/sorry/` diagnostic JSON | `.seo-run/stage3-live/google/serp-sorry-diagnostic.json` | `ab8866c561a3ff072900851991a8264d05b79bf99ab96be26b802255e2c94ab5` |
| expected normalized output | `.seo-run/stage3-live/traditional/google-serp-wedding-calculator.json` | **不存在** |

diagnostic 是失败后对浏览器现场的只读保存，不冒充 collector 自身生成的 blocker evidence。

## `ACCEPTED_ENVIRONMENT_BLOCKER` 六条件

| 条件 | 是否满足 | 依据 |
| --- | --- | --- |
| real collector 抵达外部源并捕获 blocker evidence | **否** | 抵达 `/sorry/`，但 collector 未写 blocker JSON/screenshot；只有事后 diagnostic |
| 可证为纯外部原因而非 parser/contract bug | **否（混合）** | 外部异常流量页真实存在；但 collector 不识别中文 `/sorry/` 并不留证是代码缺口 |
| 未用 mock、合成、官方 API、替代 provider 或 fallback | 是 | 没有任何降级，输出缺失保持缺失 |
| collector 与下游 fail closed | 是 | exit 2；无 normalized SERP、无 receipt、无后续 SERP 决策 |
| 针对相关 parser/extractor 的回归测试 | **否** | 现有测试覆盖 Trends 429 error page，不覆盖 SERP `/sorry/` blocker 留证 |
| 无开放 P0/P1 门禁缺陷 | **是（修订契约下）** | blocker-evidence 缺口仅影响可选 SERP 留证，不再能绕过必需门或影响 release 决策 |

六项未全部满足，因此这次可选 SERP 尝试本身仍不是 PASS 或 AEB。修订后的 release contract
不要求用 AEB 把可选 SERP 失败转成可接受状态；它保持真实 unavailable，且未用于 KD 40–50 晋级。
