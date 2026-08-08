# obsidian-auto-videonotes

**English** · [中文](README.md)

An Obsidian video-notes Skill for Codex. It recursively scans videos and SRT subtitles from a source path, produces Markdown notes with clickable timestamps, and places Obsidian-compatible media links in a dedicated note folder.

## Features

- Recursively scans `.mp4`, `.mkv`, `.mov`, `.webm`, `.m4v`, and `.avi` videos.
- Prefers matching SRT files and reports missing or ambiguous subtitles instead of inventing content.
- Creates hard links in `视频笔记/媒体/` by default; symlinks can be selected explicitly.
- Produces a title, a timestamped core-summary table, and detailed prose, with Resource templates and custom tags supported.
- Adds English explanations to technical terms on first use, such as `监督学习（Supervised learning）`.
- Updates only Codex-generated regions, preserves manual edits, and protects conflicting files on repeated runs.

## Semantic segmentation

A timestamp marks the start of a semantic paragraph; it is not a mechanical split point. The Skill first extracts a coverage frame of definitions, mechanisms, cases, numbers, limitations, and conclusions, then segments by changes in topic, task, case, or argument. A continuous chain of background, operation, output, result, and meaning stays in one paragraph, with one timestamp at the beginning.

The body must retain concrete definitions, examples, numbers, causal relationships, steps, and limitations from the subtitles. It does not use fixed character counts, time spans, or paragraph counts. If a paragraph only continues the previous one, or starts with a connective such as “therefore”, “then”, “but”, or “if”, it should be merged or rewritten. See [`references/detail-note-style.md`](references/detail-note-style.md) for the detailed writing standard.

## Installation and invocation

Install this directory as a Codex Skill and invoke it with `$obsidian-video-notes`. On first use, provide the real Obsidian Vault path and choose whether to use a note template and custom tags. Later runs generally require only a video file or directory path.

The Skill writes only to the configured note folder. It does not scan or modify other Vault directories, duplicate notes, source videos, or original SRT files.

## Configuration

The configuration stores only the Vault path, relative folders, media-link mode, and tags. It stores no credentials. The default note folder is `视频笔记`, the media folder is `媒体`, and the default media mode is hardlink.

```bash
python3 scripts/obsidian_vault_sync.py configure \
  --vault "/Users/you/Documents/Obsidian/MyVault" \
  --media-link-mode hardlink \
  --tag "Resource/Technology/AI" \
  --tag "keyword/example"
```

The configuration file lives in the Skill directory as `config.json`. It is excluded by `.gitignore` and must not be committed.

## Batch workflow

Scan the directory containing the videos and its subdirectories:

```bash
python3 scripts/obsidian_vault_sync.py scan \
  "/path/to/video-or-folder" \
  --output "/tmp/obsidian-video-manifest.json"
```

The Skill then reads the complete SRT files and writes generated Markdown to a temporary content directory. Validate every note before committing it to the Vault:

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

## Note structure and timestamps

The Resource-template body uses this structure:

```markdown
# Title

## 核心总结

| 总结维度 | 核心知识点 | 时间戳 |
| --- | --- | --- |
| What | A short, verifiable conclusion | [[媒体/视频.mp4#t=251\|04:11]] |

## 正文

[[媒体/视频.mp4#t=251|04:11]]

A complete prose paragraph for the segment.
```

The pipe in a table timestamp must be escaped as `\|`; timestamps in the body use the standard `|`. SRT start times are converted to integer seconds: milliseconds below `.500` round down, while `.500` and above round up. The display time must match `#t=` exactly. Use `MM:SS` below one hour and `HH:MM:SS` at one hour or longer.

## Repository layout

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

`SKILL.md` defines the interaction flow and writing rules. `obsidian_vault_sync.py` handles scanning, conflict protection, and Vault commits. `validate_note.py` checks Markdown structure, timestamps, and template rules. See [`SKILL.md`](SKILL.md) for the complete specification.

## Safety boundaries

The Skill does not automatically call transcription or translation services and does not copy videos into the Vault. Missing subtitles, ambiguous matches, invalid timestamps, or target conflicts stop the affected item and are reported. Existing manual notes are updated only when they contain the complete Codex-generated markers.
