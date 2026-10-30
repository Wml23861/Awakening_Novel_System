---
description: 对已核验底本执行四大名著逐回研究与复核
argument-hint: "<作品> <回目范围>"
---

研究输入：$ARGUMENTS

先读取项目状态和研究协议。只有 PHASE 2 已获用户确认且底本已验收时才执行；否则停止并说明缺口。输入不完整时询问作品与范围。调用 `classic-chapter-research` Skill 和 `literature-scholar` Agent，保存逐回报告、更新真实进度并列出待复核项。不得用全书摘要代替逐回研究，不得创作正文或自动进入下一阶段。
