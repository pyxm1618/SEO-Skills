# 交接：SEO-Skills Claude 宿主适配 + 验收

> 最后更新：2026-08-30，本次阶段三 Live 采集验收。
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

最终基线 **365 passed**（`python3 -m pytest -q`，约 6s；系统 python3 即可跑测试）。
本次开始时旧 HEAD 为 363；同步 `origin/claude/claude-code-host` 的 8 个新提交后新增 2 个
discovery coverage 测试，最终提交必须以 365 为准。

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

**阶段三 · Live 采集** 已执行，结论 **DO NOT MERGE**。7 条台账已收敛：

| Live 验收 | 状态 | 摘要 |
| --- | --- | --- |
| Google Autocomplete | PASS | 真实 CDP，10 条可见建议，production receipt |
| Google intitle + SERP | FAIL | intitle=493 PASS；SERP 第二页进入 `/sorry/` 且 collector 未留 blocker evidence |
| Google Trends | PASS | 54 个真实周时序点，raw payload + screenshot + receipt |
| Semrush Ideas + Exact | PASS | `sem.3ue.com` 当前 UI 捕获；Ideas 30 行、Exact 完整 12 月趋势 |
| KGR | PASS | verified Exact + intitle；evaluator 算得 1.540625 |
| Traditional workflow | FAIL | 早退与 continuing Exact 均执行；continuing intitle 被 `/sorry/` 阻塞且不满足 AEB 六条件 |
| Emerging Monitor | PASS | 5 个候选、15 个 timeline、2045 点；全部诚实 `watch -> new_root_watchlist` |

计数：`PASS=5`，`ACCEPTED_ENVIRONMENT_BLOCKER=0`，`FAIL=2`，`UNREVIEWED=0`；
`7 = 5 + 0 + 2 + 0`。逐条证据在 `acceptance-evidence/terminal/stage3-live-*.md`。

已完成的基础设施：
- Playwright + gspread 装在专用 venv **`~/.venvs/seo-skills`**（系统 python3 是 Homebrew 3.14，
  PEP 668 externally-managed，**不要**往里装）。跑采集脚本一律用 `~/.venvs/seo-skills/bin/python`。
- Sheet 导出层已在**真实 Google Sheet** 上端到端验证（`902e8ae`）：首跑写 header + append 一行，
  二次原地更新零 append，读回确认 `unknown` 保持为 `unknown`（不空、不为 0），事后删掉 smoke 工作表。
- stage hook 已从 `runtime/codex_stage_hook.py` 更名为宿主中立的 `runtime/stage_hook.py`
  （`a719d09`），两个宿主配置均已重指，转发垫片已删除（`d051e41`）。

## 剩余问题

**1. 新的 release blocker：Google Search `/sorry/` 没有 collector blocker evidence**

真实 SERP 第一页可读，翻到第二页后进入 `www.google.com/sorry/index`。collector 正确 fail closed，
但当前 `assert_google()` 只匹配英文 `unusual traffic` / `captcha`，没有按 `/sorry/` 路径或中文正文
识别并持久化结构化 blocker JSON + screenshot。结果是：外部阻塞真实存在，却不满足
`ACCEPTED_ENVIRONMENT_BLOCKER` 的第 1、2、5、6 条，必须记 FAIL。修复范围应保持最小：
Search/intitle/SERP 共用的错误页识别、blocker 留证、针对性回归测试；修完后重新 Live 验收，不能复用本次失败当 PASS。

**2. Traditional 必须重跑 continuing candidate 的 intitle/KGR/SERP**

`wedding calculator` 已确定性早退（Volume 320）；`wedding cost calculator` 已通过 Exact
（Volume 720、KD 18），但下一 intitle 被上述 `/sorry/` 阻塞。修复并换到可用 Google Search
环境后，从该 continuing gate 继续；不要让早退 candidate 的独立 KGR/Trends 证据替代它。

**3. Release decision 仍是 DO NOT MERGE**

自动化与 Host acceptance 不能覆盖上述真实代码缺口。即使 Emerging 已真实 PASS、Semrush
relay-only 与 provenance 完整，只要 intitle+SERP 和 Traditional 仍 FAIL，或该 blocker 未按六条件
成为 AEB，`TRUST_BOUNDARY.md` 的 Release decision 就不允许推荐合并。

**4. 已完成但不要误读**

双浏览器方案已经实证：Google 9333 的 `google_auth_cookies=0`，Semrush 9334 的登录 relay 当前可用。
Emerging 最终数据库有 5 条真实记录并已导入 Sheet，读回 5/5 一致；34 个缺失单元保持 `unknown`。
旧的 429 尝试文档仍是历史 AEB 记录，不代表当前 7 条验收状态。

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
