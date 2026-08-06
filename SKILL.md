---
name: obsidian-video-notes
description: |
  根据视频原路径递归扫描本地视频和 SRT，在用户首次指定的 Obsidian Vault 中自动创建独立的视频笔记文件夹、Markdown 笔记和可被 Obsidian 识别的媒体链接。默认使用硬链接以保留原视频数据且支持时间戳跳转，也可显式配置软链接。笔记包含标题、带时间戳的核心总结表格和正文，支持 Resource 通用模板与自定义 tags，并严格校验 SRT 时间、Obsidian 媒体链接、中文字幕匹配、冲突保护和幂等更新。用户要求整理视频课程、批量生成 Obsidian 视频笔记、同步字幕或调用 $obsidian-video-notes 时使用。
---

# Obsidian Video Notes

## 工作边界

本 Skill 可以写入真实 Obsidian Vault，但只允许写入首次由用户明确配置的独立笔记文件夹。不得扫描、修改、复制、移动或删除 Vault 中的其他笔记、MOC、日志或媒体文件。不得猜测 Vault 路径；配置不存在时先询问。

默认生成目录是 `<Vault>/视频笔记/`，媒体目录是 `<Vault>/视频笔记/媒体/`。默认在媒体目录中创建硬链接：它不会复制视频数据，但会让 Obsidian 将媒体识别为 Vault 内的真实文件，从而让 `Video Notes` 的 `#t=整数秒` 链接可以解析。使用时间戳跳转前，确认 Vault 已启用 `Video Notes` 或兼容的媒体时间戳插件；Obsidian 核心本身不负责把本地视频的 `#t=` 链接绑定到播放器。只有用户明确选择软链接时才使用软链接；软链接可能不会被 Obsidian 索引。配置保存在本 Skill 目录下的 `config.json`，只保存 Vault 路径、相对文件夹、字幕语言、媒体链接方式和用户指定的标签，不保存凭据。

如果用户只要求返回 Markdown，不执行 Vault 同步；如果用户提供视频原路径并要求自动生成，则执行完整扫描、生成、校验和提交流程。

## 生成前确认

每次新建或批量更新笔记前，先向用户确认两个选项：第一，是否需要套用笔记模板；如果需要，询问模板文件路径或模板名称，用户选择 Resource 时读取 [resource-template.md](./references/resource-template.md)，不要擅自猜测 `Topic`、`Subject` 或 `status`。第二，是否需要自定义 tags；如果需要，要求用户提供完整 tag 列表并按原样写入；如果不需要，新笔记使用已保存的默认 tags，已有笔记保留原 tags。用户明确选择“不使用模板”时，只生成 Skill 规定的最小 Markdown 结构。

模板和 tags 是两个独立选项：用户可以使用 Resource 模板但保留已有 tags，也可以不使用模板但指定自定义 tags。若用户没有回答，暂停写入并继续询问，不生成猜测性的 frontmatter 或分类字段。

## 既有笔记批量更新 SOP

当用户要求更新已经存在的一批视频笔记时，必须按以下顺序执行，不能只修改抽查文件。先用视频原路径重新扫描全部视频和对应 SRT，确认扫描清单中的 `ready` 数量与用户要求的笔记数量一致；缺少字幕、字幕冲突或目标冲突的项目必须先报告，不能用空正文代替。随后逐个读取完整 SRT 和现有笔记，保留现有标题、标签、媒体链接以及自动标记区域之外的人工内容，根据字幕主要主题、案例、论证、数字、限制和结论重建正文。时间戳是语义段落的起点，不是机械换段标记：必须先判断一个完整的观点、案例或流程何时结束，再决定是否换段。连续的“背景—操作—输出—结果—意义”应放在同一段中；只有主题、任务、案例或论证发生变化时才换段。正文可使用少量 `###` 主题小标题，但不得新增其他二级标题。细粒度写作标准见 [detail-note-style.md](./references/detail-note-style.md)。

批量更新时只替换 `codex:video-note-summary` 和 `codex:video-note-body` 两个自动区域，不覆盖没有完整标记的旧笔记，也不覆盖普通文件或指向其他源文件的媒体链接。用户选择 Resource 模板时，再使用 `scripts/apply_resource_template.py` 只更新 frontmatter，不触碰正文和时间戳。核心总结保持 3–5 行表格；表格内的 Obsidian 时间戳必须把显示时间分隔符写成 `\\|`，正文内必须使用标准 `|`。所有生成内容先逐篇运行 `validate_note.py`，再提交到 Vault；提交后复查笔记数量、媒体链接目标、表格链接、正文链接、标题结构和 frontmatter 标签。

Resource 模板迁移示例：

```bash
python3 scripts/apply_resource_template.py \
  "/用户 Vault/视频笔记" \
  --expected-count 31 \
  --topic "用户确认的 Topic" \
  --subject "用户确认的 Subject" \
  --status fruit
```

批量更新只允许写入配置的 `notes_folder` 及其 `media_folder`，不得修改扫描源视频、SRT、Vault 中的重复目录或其他笔记目录。重复运行必须是幂等的，不生成重复文件或重复段落。Vault 如果启用了会自动维护 `created`/`updated` 等字段的外部插件，应将其视为 Vault 自动元数据；Skill 不主动新增这些字段，也不把它们当作人工正文区域覆盖。

## 自动同步流程

### 1. 首次配置

如果 `config.json` 不存在，询问用户提供真实 Obsidian Vault 根路径。Vault 必须已经存在且是目录。默认使用以下配置：

```json
{
  "vault_root": "/用户提供的/Vault",
  "notes_folder": "视频笔记",
  "media_folder": "媒体",
  "subtitle_language": "zh",
  "media_link_mode": "hardlink",
  "tags": []
}
```

使用以下命令保存配置；不要把真实路径写进 Skill 源码：

```bash
python3 scripts/obsidian_vault_sync.py configure \
  --vault "/用户提供的/Vault" \
  --media-link-mode hardlink \
  --tag "Resource/技术/Al" \
  --tag "keyword/吴恩达/Generative_Al_for_Everyone"
```

### 2. 扫描视频和 SRT

用户提供一个视频原路径后，调用：

```bash
python3 scripts/obsidian_vault_sync.py scan \
  "/用户提供的视频原路径" \
  --output "/临时目录/manifest.json"
```

输入可以是单个视频文件或目录。单个视频文件会扫描其所在目录及子目录；目录输入会递归扫描该目录。不要跟随软链接扫描，不要扫描已经生成的媒体目录。

支持 `.mp4`、`.mkv`、`.mov`、`.webm`、`.m4v` 和 `.avi`。用户给出不带扩展名且对应的 `.mp4` 文件存在时，默认补充 `.mp4`；不要把自然语言标题虚构为不存在的路径。

每个视频优先查找同目录字幕，也会查找扫描根目录或视频目录下的 `srt/`、`subtitles/` 和 `字幕/` 子目录。优先选择完全同名的 `<视频名>.srt`，其次选择唯一的中文后缀字幕；对于字幕文件名包含 `【视频文件名】`、`[视频文件名]` 或 `(视频文件名)` 的情况，也会进行唯一匹配。视频名末尾带有 `_Chinese_translated`、`-Chinese-translated` 等翻译后缀，而字幕省略该后缀时，也会按去除后缀的名称匹配。多个候选无法唯一判断时跳过并报告；没有匹配字幕时不生成空笔记。

### 3. 生成笔记

对 manifest 中 `status: ready` 的项目读取完整 SRT，按视频原始顺序整理内容。SRT 每条字幕的起始时间只是语义内容的候选锚点。先建立“定义—机制—案例—数字—限制—结论”的覆盖框架，再沿着讲解逻辑识别语义段落。一个语义段落可以包含多个连续字幕时间点，但只在段首放第一条相关 SRT 时间戳；不要因为出现新的字幕时间点就强制换段。每个独立定义、独立案例、关键数字、因果论证、步骤、限制或结论都必须在正文中有明确对应内容；不能把多个不同案例压成一句笼统概括，也不能把同一案例的背景、操作、输出和结论拆成多个孤立段落。正文段落通常包含 3–6 句完整 prose，具体数量以逻辑完整性和信息覆盖率为准，不设固定时间长度、字符数或段落数量。不得逐句机械抄写字幕，也不得补充字幕没有提供的事实。可在正文内部使用少量 `###` 主题小标题帮助组织内容，但每个小标题下必须继续覆盖对应字幕细节。

总结框架读取 [summary-frameworks.md](./references/summary-frameworks.md)，根据视频内容选择一个主框架。默认提炼 3–5 个互不重复的核心知识点。

生成 Markdown 时，若用户选择 Resource 模板，严格使用以下结构：

```markdown
---
creator: Komaki Zhu
original_author:
cover:
source:
type: Resource
Topic: 用户确认的 Topic
Subject: 用户确认的 Subject
status: 用户确认的 status
tags:
  - 用户指定的标签
aliases:
created:
updated:
---

# 标题

## 核心总结

| 总结维度 | 核心知识点 | 时间戳 |
| --- | --- | --- |
| 是什么 | 简短、可核验的核心结论。 | [[媒体/视频.mp4#t=251\|04:11]] |

## 正文

[[媒体/视频.mp4#t=251|04:11]]

对应的自然完整正文段落。
```

标题使用视频文件名去除扩展名后的原始名称。只保留三个顶层结构：标题、`## 核心总结` 和 `## 正文`。正文内部可以使用少量 `###` 主题小标题，但不得创建其他 `##` 顶层章节。用户选择 Resource 模板时，保留模板字段和用户指定 tags；不擅自增加模板之外的字段。用户不使用模板时，按确认结果生成最小 frontmatter。不要生成底部总结、操作日志或解释性文字。

正文中的时间戳必须单独占一行，下一段再写正文；表格中的时间戳仍然是完整的 Obsidian wikilink，但必须把显示时间前的分隔符写成转义形式 `\|`，例如 `[[媒体/视频.mp4#t=251\|04:11]]`，防止 Markdown 表格把它拆成两列。正文中的时间戳使用标准形式 `[[媒体/视频.mp4#t=251|04:11]]`，不要转义。时间戳不能放入任何标题。默认不使用项目符号或编号列表；将字幕中的清单改写成连续自然段。时间戳应放在最能支撑该段内容的语义段落之前，不要机械重复章节起点。

专业名词首次出现时必须同时提供英文说明，格式为“中文（English）”。适用范围包括技术概念、编程语言、算法、模型、方法论、开发框架、协议、行业术语和关键缩写，例如“监督学习（Supervised learning）”“应用程序接口（Application Programming Interface，API）”“分布式内存计算框架（Distributed in-memory computing framework）”。如果术语本身是英文品牌、产品名或项目名，则保留官方英文名称；已经在中文中约定俗成且没有稳定英文对应词的普通词语不强行翻译。后续再次出现同一术语时可以只使用中文或缩写，但首次定义必须完整。

正文整理完成后，必须反向对照 SRT 检查覆盖率：从视频开头到结尾逐段确认定义、案例、数据、机制、限制和结论均已出现；如果连续一大段字幕只对应一个过度概括的段落，应继续拆分。如果一个段落只是前一段的继续，或以“因此、所以、然后、而且、并且、但、不过、这就是、这意味着、如果”等续接词开头，应优先合并并重新整理为完整语义段。时间戳数量只能作为异常提示，不能代替内容覆盖检查。

### 4. 时间戳规则

时间链接使用媒体相对路径，并严格遵守：

```markdown
[[媒体/相对目录/视频文件名.mp4#t=整数秒|显示时间]]
```

SRT 起始时间转换为整数秒：毫秒低于 `.500` 向下取整，`.500` 及以上向上取整。链接显示时间必须与整数秒完全一致。一小时以内使用 `MM:SS`，一小时及以上使用 `HH:MM:SS`。例如 `00:04:11,500` 必须写成 `[[媒体/视频.mp4#t=252|04:12]]`。

### 5. 提交到 Vault

把每篇已生成 Markdown 放入临时内容目录后，先运行：

```bash
python3 scripts/validate_note.py \
  --require-template \
  --allow-frontmatter \
  --allow-generated-markers \
  "/临时目录/笔记.md"
```

所有笔记通过校验后，再调用：

```bash
python3 scripts/obsidian_vault_sync.py commit \
  --manifest "/临时目录/manifest.json" \
  --content-dir "/临时目录/notes"
```

脚本会在 Vault 中创建笔记和媒体目录，并默认用硬链接连接到原视频，不复制视频数据。媒体链接目标形如 `媒体/章节/视频.mp4`，保留视频原始文件名和目录层级；只有显式使用 `--media-link-mode symlink` 时才创建软链接，但 Obsidian 可能无法索引软链接，时间戳跳转也可能失效。

## 幂等更新和冲突保护

新笔记使用隐藏的 Codex 标记区分自动生成区域：

```markdown
## 核心总结

<!-- codex:video-note-summary:start -->
自动生成的总结表格
<!-- codex:video-note-summary:end -->

## 正文

<!-- codex:video-note-body:start -->
自动生成的正文
<!-- codex:video-note-body:end -->
```

重复运行时，缺少笔记或媒体链接则创建；正确的现有硬链接保持不变；正确的旧软链接会在默认硬链接模式下安全迁移为硬链接；错误软链接和普通文件不覆盖。已有笔记只有在同时包含完整 Codex 标记时才更新，更新时仅替换标记区域，区域外的人工内容保留。没有标记的旧笔记视为人工笔记，跳过并报告冲突。

任何一个项目的字幕不明确、笔记目标冲突、媒体链接目标冲突或 Markdown 校验失败，都必须在最终报告中说明。不得虚构时间、视频文件名或字幕内容。

## 最终检查

使用 [validate_note.py](./scripts/validate_note.py) 检查标题顺序、核心总结表格、正文位置、时间戳秒数、显示时间、标题时间范围、列表语法和生成标记。使用 [obsidian_vault_sync.py](./scripts/obsidian_vault_sync.py) 的扫描和提交结果检查创建、更新、跳过和冲突项目。

Skill 本身完成修改后，运行 `quick_validate.py` 检查 Skill frontmatter 和目录结构；再使用临时 Vault、临时视频文件、多个 SRT 和重复运行场景进行端到端验证。
