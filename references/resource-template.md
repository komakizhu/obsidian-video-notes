# Resource 通用模板

当用户选择 Resource 模板时，使用以下 frontmatter。没有可靠值的字段保留为空，不要虚构来源、作者或别名；用户已有的 `tags`、`created` 和 `updated` 应保留。

```yaml
---
creator: Komaki Zhu
original_author:
cover:
source:
type: Resource
Topic: AI工程与智能体技术
Subject: 技术与效率系统
status: fruit
tags:
  - 用户指定的标签
aliases:
created:
updated:
---
```

视频笔记的 frontmatter 之后继续使用 Skill 规定的标题、`## 核心总结` 和 `## 正文` 结构。`Topic`、`Subject` 和 `status` 应根据用户选择或已有 Vault 分类调整；用户没有确认时，先询问，不要把示例值当成普适答案。
