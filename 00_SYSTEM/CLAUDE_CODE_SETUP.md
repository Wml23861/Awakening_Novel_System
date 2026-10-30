# Claude Code 配置机制与验证说明

核验日期：2026-10-30  
实际 CLI：Claude Code 2.1.162  
配置范围：项目级 Agents、Skills、Slash Commands。

## 1. 实际采用的机制

| 类型 | 项目路径 | 格式与必要字段 |
|---|---|---|
| Agents | `.claude/agents/<agent-name>.md` | 首行开始的 YAML frontmatter；`name`、`description`，可选 `tools`；正文为系统提示 |
| Skills | `.claude/skills/<skill-name>/SKILL.md` | 每个技能独立目录；显式 `name`、`description`，名称与目录一致 |
| Commands | `.claude/commands/<command-name>.md` | 文件名提供命令名；frontmatter 可省略，本项目仅用 `description`、`argument-hint` |

本项目采用保守核心字段，未复制滚动文档中可能出现的新字段。命令正文使用 `$ARGUMENTS` 接收命令名后的全部输入；它是提示词替换，不是 PowerShell 环境变量。名称使用小写 ASCII、数字和连字符。

## 2. 非运行目录

`08_SKILLS/` 与 `09_AGENTS/` 只保存索引和版本说明，不具备自动加载意义。仅在 CLAUDE.md 中引用 Markdown 也不会注册 Skill 或 Agent。

## 3. 发现与重新加载

Skills 支持热重载，2.1.162 亦支持 `/reload-skills`。为统一验收 Agents、Skills 和 Commands，建议在完整配置后启动新会话，不假设所有组件都有相同的热重载行为。

新会话中的人工加载核验入口：

1. `/context` 查看已加载技能和自定义 Agent 上下文。
2. `/skills` 查看技能。
3. `/agents` 查看本版本 Agent。
4. 用无害测试参数调用 `/status`，检查命令和 `$ARGUMENTS` 行为。

这些实际加载检查不能由文件存在或静态脚本检查替代；当前报告须分别记录。

## 4. 本项目配置数量

- 主要 Agent 6 个，扩展 Agent 4 个，共 10 个。
- Skill 7 个。
- Slash Command 15 个。

数量只表示配置文件，不表示文学研究或创作能力已经验证。角色效果须在相应阶段用真实任务评价。

## 5. 官方依据

- Subagents：https://code.claude.com/docs/en/sub-agents
- Skills：https://code.claude.com/docs/en/skills
- Slash Commands：https://code.claude.com/docs/en/slash-commands
- `.claude` 目录：https://code.claude.com/docs/en/claude-directory
- 配置调试：https://code.claude.com/docs/en/debug-your-config
- CLI：https://code.claude.com/docs/en/cli-reference
- 2.1.162 变更记录：https://github.com/anthropics/claude-code/blob/v2.1.162/CHANGELOG.md

官方网页为滚动文档，可能包含高于 2.1.162 的内容；因此本项目以版本变更记录和保守核心格式为准。`claude doctor` 只用于安装/设置诊断，不作为全部组件已加载的证明。
