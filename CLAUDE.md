# CLAUDE.md

Skill 与 runtime 说明见 `README.md`；宿主接线与 `.seo-run` 运行期状态见 README 的「在 Claude Code 中启用」。

本文件只记录在此仓库工作时遇到的**环境约束与应对**，不重复项目文档。

## auto 权限模式的分类器故障

### 识别特征

工具调用被拒，错误形如：

```
claude-opus-5[1m] is temporarily unavailable (server error / connection failed),
so auto mode cannot determine the safety of Bash right now.
```

auto 模式下每个**非只读**调用都要先由安全分类器预判，分类器本身跑在上游模型上。该模型不可用时，所有写入与代码执行一律被拒。

这是平台侧可用性问题，**不是仓库配置问题，无法在仓库内修复**。

判据：`Read`、`git log`、`ls`、`cat`、`grep` 全程正常，而 `mkdir`、`cat > file`、`python3`、`pytest` 全部失败 —— 即可确认是本故障，不必再排查权限规则或命令写法。

### 应对：唯一已验证有效的手段

**切出 auto 模式** —— 按 `Shift+Tab` 循环权限模式，切到默认模式或 acceptEdits。分类器不在这两种模式的调用链上，写入立即恢复。

2026-08-29 的一次故障中此法即时生效。在此之前 20+ 次重试全部失败，**等待与重试无效**；`Agent` 与 `CronCreate` 同样走分类器，无法用作绕行。

### 故障期间仍可用的操作

平台内置一份**静态只读白名单**，这些不经过分类器，故障期间始终可用：

- `git log` / `git status` / `git diff` / `git worktree list`
- `ls` / `cat` / `head` / `grep` / `wc` / `find`
- `Read` 工具

可借此继续做静态审计。注意 `python3 -c "print(1)"` **不在**白名单内 —— 任意代码执行一律需要分类器。

故障期间曾出现"时好时坏"的假象，实为只读命令与写入命令交替所致，并非分类器间歇恢复。

### 尚未验证的思路（勿当作已知方案）

在 `.claude/settings.json` 增加 `permissions.allow` 白名单，理论上可让命中显式规则的调用跳过分类器判定。

**该做法在 2026-08-29 故障期间无法测试，未经验证**，因此没有写入本仓库配置。下次故障复现时可顺手验证；确认有效后再固化，并注意白名单是以放宽权限控制换取可用性，范围应只覆盖 `pytest` / `compileall` / `git` 只读这类例行校验。
