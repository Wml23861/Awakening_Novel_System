# 觉醒小说 AI 创作工程

以《红楼梦》《水浒传》《三国演义》《西游记》的逐回研究为基础，结合可核验的现代商业阅读研究，建设原创觉醒长篇小说创作系统。

**当前状态：PHASE 0 工程初始化。尚未开始四书深度研究，未确定任何小说正文设定。**

## 入口

- [项目执行规则](CLAUDE.md)
- [工程总纲（用户原始文件）](觉醒小说%20AI%20创作工程总纲.md)
- [项目状态与阶段验收](00_SYSTEM/PROJECT_STATUS.md)
- [模板目录](00_SYSTEM/TEMPLATES/)
- [自动化工具说明](10_TOOLS/README.md)

## 目录用途

| 目录 | 用途 |
|---|---|
| `00_SYSTEM` | 宪法、协议、质量门槛、状态与标准模板 |
| `01_SOURCE` | 四书候选原著资料、版本档案、逐回研究与进度 |
| `02_CLASSIC_RESEARCH` | 分主题及四书交叉研究 |
| `03_COMMERCIAL_RESEARCH` | 有来源、有核验日期的商业研究 |
| `04_CREATIVE_KNOWLEDGE` | 心法、训练、风格与已验证方法 |
| `05_NOVEL_PROJECT` | 后续阶段的原创小说档案；当前不填写设定或正文 |
| `06_REVIEW` | 独立审稿、专项审查和验收报告 |
| `07_FEEDBACK` | 真实反馈与模拟反馈严格分离后的迭代资料 |
| `08_SKILLS` / `09_AGENTS` | 运行配置索引和版本说明，不是自动加载目录 |
| `10_TOOLS` | 标准库辅助脚本及测试 |
| `11_ARCHIVE` | 历史版本、废弃设定与规则变更留痕 |

## Claude Code 配置

实际项目配置放在 `.claude/agents/`、`.claude/skills/`、`.claude/commands/`。在新会话中可使用 `/status` 查看进度；其余命令受阶段门槛约束，不能用来跳过用户确认。

## 原著资料现状

项目根目录已有 `红楼梦.md`、`水浒传.md`、`三国演义.md`、`西游记.md`，PHASE 0 仅确认其存在并读取少量开头用于识别，不代表版本或完整性已验收。`01_SOURCE/*/原著/` 暂不复制这些文件，避免重复与来源混乱；PHASE 1 将登记、核验并确定规范存放方式。

## 验证

在项目根目录运行：

```powershell
python -I -m unittest discover -s 10_TOOLS/tests -v
python -I 10_TOOLS/validate_project.py
```

具体结果以[项目状态](00_SYSTEM/PROJECT_STATUS.md)和初始化验收报告为准。
