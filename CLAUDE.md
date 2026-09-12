# CLAUDE.md

项目方法、Skill 边界、真实采集浏览器、生产 manifest 与 Claude Code hook 接线以 [`README.md`](README.md)、[`runtime/BROWSER_RUNTIME_CONTRACT.md`](runtime/BROWSER_RUNTIME_CONTRACT.md) 和 [`runtime/TRUST_BOUNDARY.md`](runtime/TRUST_BOUNDARY.md) 为准。本文件只保留 Claude Code 中仍长期有效的宿主操作原则，不记录单次事故现场。

## 区分平台权限故障与仓库门禁拒绝

Claude Code 的平台权限/安全分类器故障与本仓库 `runtime/stage_hook.py` 的 fail-closed 拒绝是两类问题，不要混在一起排查。

先用只读操作确认仓库状态，例如：

```bash
git status
git log -1 --oneline
git diff
```

如果只读操作正常，而平台明确报告 auto/permission classifier 或上游模型不可用，按 Claude Code 当前 UI/平台指引切换到可执行的权限模式或重新开始会话；不要通过修改本仓库 hook、放宽 stage contract、伪造 receipt 或删除 evidence 来绕过平台故障。

如果错误来自 `runtime/stage_hook.py`，则按 `runtime/TRUST_BOUNDARY.md` 的 fail-closed 规则处理：先确认 active manifest、前置 stage、candidate identity、hook wiring 与当前工作目录，再修复真实根因。

## Hook 配置变更

Claude Code 在会话启动时读取项目 hook wiring。修改 `.claude/settings.json`、hook 命令或 hook 脚本路径后，应重新启动 Claude Code 会话并重新确认信任；不要假设已运行的会话会自动采用磁盘上的新配置。

变更 hook 路径时，遵守 `runtime/TRUST_BOUNDARY.md` 的顺序：先保留旧路径、更新配置、重启受影响会话并确认新 wiring 生效，最后再删除旧路径。这样可以避免运行中的会话继续引用已经不存在的脚本。

## 运行期状态

`.seo-run/active.json` 是运行期状态，不是项目配置。不要把调试残留的 `IN_PROGRESS` manifest 当成正常仓库状态，也不要在同一 worktree 中并发运行多个 production host session。并发隔离要求见 README 与 `runtime/TRUST_BOUNDARY.md`。

## 证据原则不因宿主故障而改变

无论 Claude Code 当前处于什么权限模式：

- `unknown` 不得改写成 `0`；
- Google/Semrush 必需来源失败时保留真实 `BLOCKED`；
- 不使用替代 provider 或手写 observed 数据补齐流程；
- 不为了让 Hook 放行而改写 validator、receipt、manifest 或 evidence。
