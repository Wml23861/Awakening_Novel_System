# Agents 配置索引

本目录只保存项目说明和版本索引，**不会因目录名自动加载 Agents**。实际运行定义位于项目根目录 `.claude/agents/*.md`，适用于 Claude Code 2.1.162 的项目 Agent 机制。

## 六个主要 Agent

| Agent | 职责 | 关键边界 |
|---|---|---|
| `literature-scholar` | 四书研究、依据核验、技法与交叉研究 | 不写正式正文，不伪造事实 |
| `commercial-editor` | 平台、案例、阅读体验与商业编辑 | 不信算法传闻，不破坏人物逻辑 |
| `character-analyst` | 动机、关系、人性、自主性与行动模拟 | 不让人物成为主角工具 |
| `plot-architect` | 主线、分卷、冲突、伏笔、反转和群像 | 不擅定核心设定，不写无因果剧情 |
| `independent-reviewer` | 独立终审与复验 | 新会话调用，不改正文，不放宽标准 |
| `continuity-keeper` | 人物、时间、地点、物品、能力、规则、伏笔 | 不擅自修改正文 |

## 四个扩展 Agent

| Agent | 职责 |
|---|---|
| `story-coach` | L1—L4 训练指导与失败归因 |
| `reader-simulator` | 五类 AI 读者模拟，不冒充真实数据 |
| `originality-auditor` | 原创性、剧情换皮与反模板审查 |
| `longform-manager` | 长篇状态、疲劳、风格、反馈和规则版本 |

Agent 配置在会话启动时发现；静态文件检查通过后，仍需在新会话中确认实际加载。不在此目录维护第二份 Agent 正文，以免版本漂移。
