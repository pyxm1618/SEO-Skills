# SEO Skills

> **一句话：** 一组可复用的 SEO Agent Skills，用来维护需求词根、发现传统与新兴关键词、筛选值得做的关键词，并把确认后的关键词映射到页面。

这个仓库采用 5 个职责分开的 Skill；A+ 只拆清执行职责，不重新设计 SEO 方法。

## 怎么唤醒 Skill

前提：你的 Agent / IDE 已经安装或加载本仓库的 Skills。

**最稳妥的方式：直接在提示词中写出 Skill 名称。**

例如：

```text
使用 seo-keyword-selection，帮我筛选这批候选关键词。
```

支持 Agent Skills 自动匹配的环境，也可以根据各 `SKILL.md` 的 `description` 自动选择；是否支持自动触发取决于宿主环境。需要确定调用哪个 Skill 时，直接点名最可靠。

## 选哪个 Skill

| Skill | 它负责什么 | 最简单的调用方式 |
| --- | --- | --- |
| [`keyword-root-library`](skills/keyword-root-library/SKILL.md) | 找、查、维护可复用的 SEO **需求词根库** | `使用 keyword-root-library，帮我找并整理 [行业] 的需求词根。` |
| [`seo-keyword-discovery`](skills/seo-keyword-discovery/SKILL.md) | 把 domain/root/Seed 通过真实 Google + Semrush 及显式配置的补漏来源扩展为 **concrete candidates**，并验证成熟需求覆盖 | `使用 seo-keyword-discovery，从这些 roots 和 Seeds 发现候选关键词。` |
| [`emerging-keyword-monitor`](skills/emerging-keyword-monitor/SKILL.md) | 从时间序列证据中发现 **正在形成、加速或出现新表达的搜索需求** | `使用 emerging-keyword-monitor，分析这批趋势数据里有哪些新兴关键词。` |
| [`seo-keyword-selection`](skills/seo-keyword-selection/SKILL.md) | 用真实指标、KGR、SERP 等证据 **筛选值得继续做的 SEO 关键词机会** | `使用 seo-keyword-selection，筛选这批候选关键词，告诉我哪些值得继续做。` |
| [`seo-page-keyword-mapping`](skills/seo-page-keyword-mapping/SKILL.md) | 把已确认的搜索需求 **分配给已知/规划页面**，确定 Primary / Secondary keyword 和页面归属 | `使用 seo-page-keyword-mapping，把这批关键词映射到这些页面。` |

## 两条工作流

传统路线：

```text
keyword-root-library
  -> seo-keyword-discovery (Full Coverage)
  -> seo-keyword-selection
  -> seo-page-keyword-mapping
```

Emerging 路线：

```text
emerging-keyword-monitor
  -> seo-keyword-selection
  -> seo-page-keyword-mapping
```

Confirmed `emerging` / `breakout` 已经是 concrete keyword，进入 selection 时不得重新跑 Seed -> Google Autocomplete -> Semrush Ideas discovery；已有 fresh compatible evidence 应复用，缺哪个 selection stage 就从最早缺失位置继续。

## 数据与来源原则

- `observed`：只能来自真实 source / collector。
- `calculated`：由程序从真实输入确定性计算。
- `analysis`：允许 AI 做语义、意图、SERP weakness、页面形态等判断，但不能冒充 observed。
- `unknown`：就是没有取得，不能变成 0 或估算值。
- `missing`、`invalid`、numeric `0`、`not_applicable`、`unknown` 必须区分。
- 当前 Semrush acquisition 只允许项目 `sem.3ue.com` authenticated same-origin relay；失败时不切换 official API、Ahrefs 或其他 provider。
- Google Autocomplete、intitle、SERP、Google Trends 必须是当前真实 Google evidence；拿不到就 BLOCKED。
- Full Traditional Discovery 的 required Seed 与 required Branch Seed 都必须完成 Google Autocomplete + Semrush Ideas/Related；Google PASS 不等于 Coverage PASS。
- Competitor Organic 是 domain/root-cluster 级补漏来源，仅在显式配置 competitor domains 时 mandatory；未配置记录 `not_configured`，配置后失败则 BLOCKED。
- `discovery_coverage` 必须绑定 production-verified `discovery_input_manifest`，并逐项核对 Root/Natural Seeds 原始总数、Candidate inventory 与完整 Candidate analysis；partial evidence 保留，失败项不能从 ledger 删除。
- `discovery_handoff` 只能在 validator 签发时重新验证 exact production `discovery_coverage` PASS receipt；不存在或被篡改的 receipt 不能生成 PASS handoff。

## 真实采集浏览器

需要真实 Google 与 `sem.3ue.com` 采集时，启动项目专用的可见 Chrome：

```bash
eval "$(python3 runtime/start_live_browser.py --port 9223)"
```

它只监听 `127.0.0.1`，使用持久目录 `.seo-run/browser-profile/`，不使用 `--headless`，也不会读取、复制或修改正常 Chrome 的 profile。目标端口被未知进程占用时会直接停止，不会抢占或杀进程。如果专用窗口显示 Semrush 登录页，请只在该窗口内完成登录，不要把密码、验证码、Cookie 或 Token 发给 Agent；登录完成后再运行 collector。

通常只需登录一次。锁屏不会清除登录；重启电脑后要重新启动专用 Chrome，但通常无需重新登录。正在采集时不要让机器睡眠。会话过期、主动退出、删除 `.seo-run/browser-profile/` 或清除浏览数据后，需要重新登录。

## 生产运行最短闭环

生产执行的第一步必须创建 active manifest；合成测试请把 `SEO_RUN_MANIFEST` 指向 `mktemp` 目录，禁止触碰已有 `.seo-run/active.json`：

```bash
export SEO_RUN_MANIFEST=.seo-run/active.json
python3 runtime/start_seo_run.py --route traditional
```

启动器只创建 `run_id`、`route`、`status=IN_PROGRESS`、空的 `stages` 和空的 `candidates`，并拒绝覆盖已有运行。普通代码开发/审核会话没有启动 SEO production run 时，Stop Hook 仍可正常结束。

传统路线先完成 global discovery，再建立候选。候选 ID 必须同时出现在 manifest、validator 参数和受保护命令的环境标记中；keyword 不接受第二个自由输入，而由唯一 `complete` row 派生：

```bash
python3 -c 'import json, os; from pathlib import Path; p=Path(os.environ["SEO_RUN_MANIFEST"]); m=json.loads(p.read_text()); m.setdefault("candidates", {})["cand_wedding_cost_calculator"]={"keyword":"wedding cost calculator"}; p.write_text(json.dumps(m, ensure_ascii=False, indent=2)+"\n")'
SEO_CANDIDATE_ID=cand_wedding_cost_calculator python3 runtime/stage_validator.py \
  --stage stage6_exact --candidate-id cand_wedding_cost_calculator --production \
  --input .seo-run/evidence/exact-wedding-cost-calculator.json \
  --report .seo-run/validation/cand-wedding-cost-calculator-exact.json
```

validator 成功后，把该 report 的 `validation_receipt_ref` 写入同一 candidate 的 stage 记录；intitle、KGR、SERP、Finalist Trends 继续使用同一个 literal `SEO_CANDIDATE_ID`。缺少 marker、ID 错配、keyword 错配或多于一条 complete row 都会被拒绝。外部证据不可用时记录真实 `BLOCKED`，不要用手写数据补齐。

Emerging 路线也必须先启动 manifest，然后固定 `as_of` 完整执行四步并生成 receipt：

```bash
export SEO_RUN_MANIFEST=.seo-run/active.json
python3 runtime/start_seo_run.py --route emerging
python3 runtime/emerging_pipeline.py \
  --input observations.json --as-of 2026-08-29T23:59:59Z \
  --output-dir .seo-run/emerging/20260829T235959Z
```

将 receipt 的路径写入 `emerging_pipeline_receipt_ref`，将 `outputs.routed.path` 原样写入 `route_handoff_ref`；只有 pipeline 实际产出的 `selection_handoff` 才能在 manifest 中建立匹配的 `keyword`、`root_id`、`status` candidate。`no_handoff`、`watch`、`insufficient_evidence` 等真实结果必须如实保留，不得伪造 handoff。

项目 `.codex/hooks.json` 需要在 Codex 中审阅并信任；配置变化后可能需要重新确认。普通 pytest/compileall 只能证明代码契约，不能代替真实 Host 自动触发的 PreToolUse/Stop 验收。

## 仓库结构

```text
skills/
  keyword-root-library/
  seo-keyword-discovery/
  emerging-keyword-monitor/
  seo-keyword-selection/
  seo-page-keyword-mapping/
runtime/
  collectors/
  discovery_coverage.py
  stage_contracts.json
  stage_validator.py
  stage_hook.py
  start_seo_run.py
  emerging_pipeline.py
  kgr_evidence_merge.py
.codex/
  hooks.json
.claude/
  settings.json
  skills/          # 指向 skills/ 的软链，供 Claude Code 自动发现
```

唯一 canonical `root-library.csv` 位于 `keyword-root-library` 中，其他 Skill 只通过 handoff / `root_id` 使用它，不复制该资产。

## 在 Claude Code 中启用

Skill 与 runtime 是宿主无关的，但**门禁配置不通用**：Codex 读 `.codex/hooks.json`，Claude Code 只读 `.claude/settings.json`。两份必须保持一致，`tests/test_claude_hooks_config.py` 守住这一点。

仓库已内置 `.claude/`，clone 后无需额外配置：

- `.claude/settings.json` 注册三个门禁事件：`PreToolUse`（拦截前置 stage 未满足的受保护命令）、`Stop`、`SubagentStop`。
- `.claude/skills/` 是指向 `skills/` 的软链，供 Claude Code 自动发现 5 个 Skill；canonical 资产仍只存在于 `skills/` 下。

三点必须知道：

1. **`SubagentStop` 不能省。** Claude Code 的 `Stop` 只在主代理结束时触发。若 SEO 流程跑在子代理里，缺了 `SubagentStop` 就会完全绕过完整性门禁——保护看起来在，实际没上电。
2. **hooks 在会话启动时快照。** 首次 clone 或修改 `.claude/settings.json` 后需重启 Claude Code 会话，并在提示时确认信任这些 hook。未被信任的 hook 不会执行。
3. **`.seo-run/active.json` 是运行期状态，不是配置。** 它存在且 `status=IN_PROGRESS` 时 `Stop` 门禁会拦截回合结束，这是设计意图。run 必须收敛到 `COMPLETE`，或收敛到带真实 blocker 的 `BLOCKED`；遗留的调试态 manifest 会拦住这个仓库里所有后续工作。

## 开发 / 验证

仅在修改 Skill / runtime 实现时需要：

```bash
python3 -m pytest skills/keyword-root-library/tests/test_root_library.py -q
python3 -m pytest skills/seo-keyword-selection/tests/test_selection.py -q
python3 -m pytest skills/emerging-keyword-monitor/tests -q
python3 -m pytest skills/seo-page-keyword-mapping/tests -q
python3 -m pytest -q
python3 -m compileall -q skills runtime
```

`discovery_coverage.py` is a finite run ledger/validator, not a long-term Discovery database or a recursive keyword crawler. Branch safety limits are execution guards, not SEO decision thresholds.
