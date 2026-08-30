# 交接：SEO-Skills Claude 宿主适配 + 验收

> 最后更新：2026-08-30，提交 `d051e41`。
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

基线 **363 passed**（`python3 -m pytest -q`，约 6s；系统 python3 即可跑测试）。

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

**阶段三 · Live 采集** ⏳ 见下方"剩余问题"。

已完成的基础设施：
- Playwright + gspread 装在专用 venv **`~/.venvs/seo-skills`**（系统 python3 是 Homebrew 3.14，
  PEP 668 externally-managed，**不要**往里装）。跑采集脚本一律用 `~/.venvs/seo-skills/bin/python`。
- Sheet 导出层已在**真实 Google Sheet** 上端到端验证（`902e8ae`）：首跑写 header + append 一行，
  二次原地更新零 append，读回确认 `unknown` 保持为 `unknown`（不空、不为 0），事后删掉 smoke 工作表。
- stage hook 已从 `runtime/codex_stage_hook.py` 更名为宿主中立的 `runtime/stage_hook.py`
  （`a719d09`），两个宿主配置均已重指，转发垫片已删除（`d051e41`）。

## 剩余问题

**1. 阶段三 Live 验收 7 条，目前 0 条 PASS（唯一阻塞发布的项）**

`TRUST_BOUNDARY.md` 的 8 条里第 6 条（宿主门禁自动触发）已由阶段二完成，实际剩 7 条：
Autocomplete / intitle+SERP / Trends / Semrush Ideas+Exact / KGR / 一条 Traditional 工作流 /
一次 Emerging Monitor 真实时序跑通。

**2. 直接卡点：Google 限流**

唯一尝试过的 Emerging Radar 最小规模跑被 Google 429 挡住，记为 `ACCEPTED_ENVIRONMENT_BLOCKER`
（**不是 PASS**，真实关键词数据未取得），证据在
`acceptance-evidence/terminal/stage3-emerging-radar-live-attempt.md`。
`.seo-run/emerging-radar-live/emerging-keywords.json` 目前 `records: 0`。
下一步是换网络（如手机热点）重跑，命令见该文档。

**3. Semrush 与 Google 的浏览器 profile 互斥（尚无方案）**

Google 采集要求上下文**零认证 cookie**，否则 `connect()` 必须失败——为此用了全新隔离 profile
`/tmp/seo-google-clean-profile`（端口 9333，已验证 0 cookie）。
但 Semrush relay 需要 `sem.3ue.com` 的**已登录**会话。两者不能共用同一 profile，
第 4 条 Live 验收需要单独规划一个已登录 profile + 独立端口。

**4. 不要用合成数据补 Live 缺口**

`emerging-keywords.json` 是空的，往里塞假记录再导入 Sheet 就能"验证"导出——
但那正是本仓库存在的意义所禁止的。Sheet 导出层已按上文验证过，缺的是真实数据，不是导出逻辑。

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
