# obsidian-auto-videonotes

[English](README.en.md) · **中文**

一个面向 Codex 的 Obsidian 视频笔记 Skill。它根据视频原路径递归扫描视频和 SRT 字幕，生成带可跳转时间戳的中文 Markdown 笔记，并将媒体以 Obsidian 可识别的链接放入独立目录。

## 能做什么

- 递归扫描 `.mp4`、`.mkv`、`.mov`、`.webm`、`.m4v` 和 `.avi` 视频。
- 优先匹配同名 SRT，并在候选不唯一或字幕缺失时报告问题，不生成虚构内容。
- 默认在 Vault 的 `视频笔记/媒体/` 中创建硬链接；也可以显式选择软链接。
- 生成标题、带时间戳的核心总结表格和正文，支持 Resource 模板与自定义 tags。
- 自动为首次出现的专业名词补充英文说明，例如“监督学习（Supervised learning）”。
- 只更新 Codex 自动标记区域，保留人工修改，并在重复运行时避免覆盖冲突文件。

## 语义分段规则

时间戳是语义段落的起点，不是机械换段标记。生成正文时，先从完整 SRT 提炼“定义—机制—案例—数字—限制—结论”，再按主题、任务、案例或论证是否发生变化来分段。连续的“背景—操作—输出—结果—意义”应放在同一段中，一个段落只在开头放第一条相关字幕的时间戳。

正文必须覆盖字幕中的具体定义、案例、数字、因果关系、步骤和限制；不使用固定字符数、时间长度或段落数量作为标准。若段落只是前一段的继续，或以“因此、所以、然后、而且、并且、但、不过、这就是、这意味着、如果”等续接词开头，应优先合并或重写。详细规范见 [`references/detail-note-style.md`](references/detail-note-style.md)。

## 安装与调用

将本目录作为 Codex Skill 安装后，使用 `$obsidian-video-notes` 调用。首次运行需要提供真实 Obsidian Vault 路径，并选择是否使用笔记模板、是否使用自定义 tags；后续通常只需提供视频文件或目录路径。

Skill 只会写入配置的独立笔记目录，不会扫描或修改 Vault 中的其他目录、重复笔记、原视频或原始 SRT。

## 配置

下面的命令只保存 Vault 路径、相对目录、媒体链接方式和 tags，不保存凭据。默认笔记目录为 `视频笔记`，媒体目录为 `媒体`，默认使用硬链接。

```bash
python3 scripts/obsidian_vault_sync.py configure \
  --vault "/Users/you/Documents/Obsidian/MyVault" \
  --media-link-mode hardlink \
  --tag "Resource/技术/AI" \
  --tag "keyword/example"
```

配置文件位于 Skill 目录下的 `config.json`，已被 `.gitignore` 排除，不应提交到仓库。

## 批量流程

先扫描视频所在目录及其子目录，生成清单：

```bash
python3 scripts/obsidian_vault_sync.py scan \
  "/path/to/video-or-folder" \
  --output "/tmp/obsidian-video-manifest.json"
```

随后由 Skill 根据完整 SRT 生成 Markdown，并把生成内容放入临时目录。所有笔记通过校验后，再提交到 Vault：

```bash
python3 scripts/validate_note.py \
  --require-template \
  --allow-frontmatter \
  --allow-generated-markers \
  "/tmp/notes/example.md"

python3 scripts/obsidian_vault_sync.py commit \
  --manifest "/tmp/obsidian-video-manifest.json" \
  --content-dir "/tmp/notes" \
  --fail-on-conflict
```

## 笔记结构与时间戳

Resource 模板的主体结构如下：

```markdown
# 标题

## 核心总结

| 总结维度 | 核心知识点 | 时间戳 |
| --- | --- | --- |
| 是什么 | 简短、可核验的结论 | [[媒体/视频.mp4#t=251\|04:11]] |

## 正文

[[媒体/视频.mp4#t=251|04:11]]

对应的完整正文段落。
```

表格中的 `|` 必须写成 `\|`，正文中的时间戳使用标准 `|`。SRT 起始时间会转换成整数秒；毫秒低于 `.500` 向下取整，`.500` 及以上向上取整。显示时间必须与 `#t=` 秒数一致，一小时以内使用 `MM:SS`，一小时及以上使用 `HH:MM:SS`。

## 目录说明

```text
obsidian-auto-videonotes/
├── SKILL.md
├── agents/openai.yaml
├── references/
└── scripts/
    ├── apply_resource_template.py
    ├── obsidian_vault_sync.py
    └── validate_note.py
```

`SKILL.md` 定义交互流程和写作规范，`obsidian_vault_sync.py` 负责扫描、冲突保护和提交，`validate_note.py` 负责检查 Markdown 结构、时间戳和模板规则。完整说明见 [`SKILL.md`](SKILL.md)。

## 许可与安全边界

本 Skill 不会自动调用转录或翻译服务，也不会把视频复制到 Vault。缺少字幕、字幕不唯一、时间戳无效或目标文件冲突时会停止对应项目并报告。任何已有人工笔记只有在包含完整 Codex 自动标记时才允许更新。
