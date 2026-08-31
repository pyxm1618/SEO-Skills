# 交接：SEO-Skills Claude 宿主适配 + 验收

> 最后更新：2026-08-31，Traditional 完成重试与阶段三最终结论。
> 每次交接请更新本文件的"当前状态"与"剩余问题"，过时的交接比没有交接更危险。

## 你现在在哪

分支 `claude/claude-code-host`，worktree `/Users/milushangdi/Downloads/SEO-Skills-claude`，
已推送到 `origin/claude/claude-code-host`（GitHub: pyxm1618/SEO-Skills）。

**注意有两个克隆。** 主仓 `/Users/milushangdi/Downloads/SEO-Skills-main` 在
`codex/seo-a-plus-scope-correction` 分支上，**Codex 正在那里并发工作，不要动它**（PR 冲突由它负责）。
两个坑：① Claude Code 会话的默认 cwd 常常是 `-main`，对本仓库的每条 Bash 都要显式
`cd /Users/milushangdi/Downloads/SEO-Skills-claude &&` 或用 `git -C`（`cd` 不跨 Bash 调用持久）；
② hook 只接线在 `-claude` 这个克隆里，从 `-main` 启动的会话**不受门禁约束**，
别把"那里 Bash 能跑"当成门禁没问题的证据。

## 这个项目是什么

5 个职责分离的 SEO Agent Skills + 一套执行完整性运行时（stage 契约 → 证据绑定 → 验证收据 → hook 门禁）。
核心价值不是 SEO 方法，而是**不让 AI 伪造或跳过真实数据采集**：
`unknown` 不能变 0、Semrush 只走 `sem.3ue.com` relay、Google 必须真实 collector、缺证据就 BLOCKED。

范围边界见 `runtime/TRUST_BOUNDARY.md`。
发布判据：自动化套件通过 + P0/P1=0 + 每个覆盖宿主的 Host acceptance + 真实 Live 采集验收。

## 当前状态

最终基线 **379 passed**（`python3 -m pytest -q`，约 7s；系统 python3 即可跑测试）。
阶段三 Live 提交基线为 365；SERP 可选契约新增 14 个行为回归，最终提交必须以 379 为准。

**阶段一 · 前置检查** ✅
**阶段二 · Claude Code 宿主门禁生效** ✅ 证据在 `acceptance-evidence/terminal/stage2-claude-host-gates.md`

| 项 | 结果 |
| --- | --- |
| C PreToolUse 拦截受保护命令 | PASS |
| D 子目录下门禁不失效 | PASS |
| E Stop 拦截未完成 run | PASS |
| F SubagentStop 拦截子代理 | PASS |
| G 清除 manifest 后行为正确 | PASS（含一处预期纠正，见文档） |

A/B 由 C–G 反证：hook 拦得动就说明已加载且被信任；skills 已被会话列出。

**阶段三 · Live 采集** 已完成；按 2026-08-31 修订后的 SERP 可选契约重算，7 条全部 PASS：

| Live 验收 | 状态 | 摘要 |
| --- | --- | --- |
| Google Autocomplete | PASS | 真实 CDP，10 条可见建议，production receipt |
| Google intitle（SERP 可选） | PASS | intitle=493；可选 SERP 在 `/sorry/` fail closed，未冒充 PASS/AEB，也不进入验收分母 |
| Google Trends | PASS | 54 个真实周时序点，raw payload + screenshot + receipt |
| Semrush Ideas + Exact | PASS | `sem.3ue.com` 当前 UI 捕获；Ideas 30 行、Exact 完整 12 月趋势 |
| KGR | PASS | verified Exact + intitle；evaluator 算得 1.540625 |
| Traditional workflow | PASS | 早退分支 PASS；continuing Exact + intitle=113 + KGR=0.15694444 均有候选绑定 production receipt；SERP absent/可选 |
| Emerging Monitor | PASS | 5 个候选、15 个 timeline、2045 点；全部诚实 `watch -> new_root_watchlist` |

计数：`PASS=7`，`ACCEPTED_ENVIRONMENT_BLOCKER=0`，`FAIL=0`，`UNREVIEWED=0`；
`7 = 7 + 0 + 0 + 0`。逐条证据在 `acceptance-evidence/terminal/stage3-live-*.md`，
契约修订证据见 `stage3-serp-optional-contract.md`。

已完成的基础设施：
- Playwright + gspread 装在专用 venv **`~/.venvs/seo-skills`**（系统 python3 是 Homebrew 3.14，
  PEP 668 externally-managed，**不要**往里装）。跑采集脚本一律用 `~/.venvs/seo-skills/bin/python`。
- Sheet 导出层已在**真实 Google Sheet** 上端到端验证（`902e8ae`）：首跑写 header + append 一行，
  二次原地更新零 append，读回确认 `unknown` 保持为 `unknown`（不空、不为 0），事后删掉 smoke 工作表。
- stage hook 已从 `runtime/codex_stage_hook.py` 更名为宿主中立的 `runtime/stage_hook.py`
  （`a719d09`），两个宿主配置均已重指，转发垫片已删除（`d051e41`）。

## 剩余问题

**1. 阶段三没有剩余 release blocker**

`wedding calculator` 已确定性早退（Volume 320）；`wedding cost calculator` 已完成候选绑定 Exact
（Volume 720、KD 18）、真实 intitle=113 与 KGR=0.15694444。首次 `/sorry/` 失败仍留在证据中，
完成重试没有复用或改写失败数据。SERP 已是可选项，不要求补跑。

**2. 可选 SERP blocker 留证仍可改进，但不再阻断 release**

真实 SERP 第二页进入 `www.google.com/sorry/index`。collector 正确 fail closed，但没有按 `/sorry/`
路径或中文正文持久化结构化 blocker JSON + screenshot，所以这次可选尝试本身仍不是 PASS/AEB。
它没有进入决策、没有 fallback、没有伪造，按新契约属于非阻断改进；以后若主动使用 SERP，
任何声称 PASS 的结果仍必须通过真实 top-10 receipt。

**3. Release decision：READY TO MERGE**

自动化 379 tests、Claude Host acceptance、7 条 Live acceptance、Semrush relay-only 与 provenance
均已满足，未发现开放 P0/P1。按 `TRUST_BOUNDARY.md` 可以推荐合并；本任务只提交并推送，不代替用户执行合并。

**4. 已完成但不要误读**

双浏览器方案已经实证：Google 9333 的 `google_auth_cookies=0`，Semrush 9334 的登录 relay 当前可用。
Emerging 最终数据库有 5 条真实记录并已导入 Sheet，读回 5/5 一致；34 个缺失单元保持 `unknown`。
Keyword Selection 和 Page Keyword Mapping 两个 Skill 都已将 SERP 改为可选：缺失保持 `unknown`/
`observe_serp`，不会阻断批次；observed mismatch、伪造 PASS、无证据 KD 晋级和无 overlap 的独立 URL
仍会 fail closed。旧的 429 尝试文档仍是历史 AEB 记录，不代表当前 7 条验收状态。

## 三个环境坑（都真实发生过）

1. **auto 模式分类器故障**：写入与代码执行全被拒、只读正常。
   不要重试，让用户按 `Shift+Tab` 切出 auto 模式。详见 `CLAUDE.md`。

2. **`~/Downloads` 的 TCC 授权丢失**：Bash 全败且 hook 报 cannot read cwd。
   这是目录授权问题，切权限模式无效。

3. **fail-closed hook 自身失败 → 全 Bash 死锁**：
   hook 执行失败（不是判定拒绝）会拒掉每一条 Bash，包括用来修复的那条。
   这是正确行为，已作为"接受的运维风险"写入 `TRUST_BOUNDARY.md`。
   **自救：`Write`/`Edit` 不经过 Bash hook**，用它们把缺失的脚本写回去即可立刻恢复；
   环境类成因则需重启会话。
   **改 hook 路径必须按序**：保留旧文件 → 改配置 → 重启所有会话 → 才能删旧文件
   （宿主在启动时把 wiring 读进内存，改磁盘对当前会话无效）。

## 用户偏好

- 回答用中文
- 要实证不要推断：「测试是否通过」这类结论必须实跑，不能靠读代码猜
- 遇到问题先排查根因再给方案，不要盲目重试
