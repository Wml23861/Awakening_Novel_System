# Skills 配置索引

本目录只保存项目说明和版本索引，**不会因目录名自动加载 Skills**。实际运行定义位于项目根目录 `.claude/skills/<技能名>/SKILL.md`，适用于 Claude Code 2.1.162 的项目技能机制。

| Skill | 用途 | 主要入口 |
|---|---|---|
| `classic-chapter-research` | 四书逐回研究、证据分层和复核 | `/research` |
| `classic-cross-study` | 四书交叉研究与融合边界 | `/cross-study` |
| `commercial-research` | 有来源和日期的商业研究 | `/commercial` |
| `creative-training` | L1—L4 训练、独立审稿与复测 | `/train` |
| `independent-chapter-review` | 独立章节终审 | `/review` |
| `novel-originality-audit` | 原创性与反模板审查 | 由创作/审稿流程调用 |
| `novel-continuity-audit` | 长篇设定与剧情连续性 | `/audit` |

所有 Skill 受项目阶段门槛约束。配置在会话启动时发现；静态文件检查通过后，仍需在新会话中确认实际加载。不在此目录维护第二份 Skill 正文，以免版本漂移。
