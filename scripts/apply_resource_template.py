#!/usr/bin/env python3
"""Apply the configured Resource frontmatter without changing note bodies."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


START = "<!-- codex:video-note-summary:start -->"
END = "<!-- codex:video-note-body:end -->"
TOP_LEVEL = re.compile(r"^(?P<key>[A-Za-z_][A-Za-z0-9_-]*):(?:\s*(?P<value>.*))?$")
LIST_ITEM = re.compile(r"^\s+-\s*(?P<value>.*)$")
RESOURCE_FIELDS = [
    "creator",
    "original_author",
    "cover",
    "source",
    "type",
    "Topic",
    "Subject",
    "status",
    "tags",
    "aliases",
    "created",
    "updated",
]


def fail(message: str) -> int:
    print(f"ERROR: {message}", file=sys.stderr)
    return 2


def frontmatter_bounds(lines: list[str]) -> tuple[int, int]:
    if not lines or lines[0].strip() != "---":
        raise ValueError("note has no YAML frontmatter")
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return 0, index
    raise ValueError("frontmatter has no closing delimiter")


def parse_frontmatter(lines: list[str]) -> tuple[dict[str, str], dict[str, list[str]], list[str]]:
    scalars: dict[str, str] = {}
    lists: dict[str, list[str]] = {}
    keys: list[str] = []
    current_list: str | None = None
    for line in lines:
        match = TOP_LEVEL.match(line)
        if match:
            key = match.group("key")
            value = (match.group("value") or "").strip()
            keys.append(key)
            current_list = None
            if value:
                scalars[key] = value
            else:
                scalars[key] = ""
                current_list = key
            continue
        item = LIST_ITEM.match(line)
        if item and current_list:
            lists.setdefault(current_list, []).append(item.group("value").strip())
    return scalars, lists, keys


def render_frontmatter(
    scalars: dict[str, str],
    lists: dict[str, list[str]],
    args: argparse.Namespace,
) -> str:
    tags = list(args.tags) if args.tags else list(lists.get("tags", []))
    aliases = list(lists.get("aliases", []))
    values = {
        "creator": scalars.get("creator") or args.creator,
        "original_author": scalars.get("original_author", ""),
        "cover": scalars.get("cover", ""),
        "source": scalars.get("source", ""),
        "type": args.resource_type,
        "Topic": args.topic,
        "Subject": args.subject,
        "status": args.status,
        "created": scalars.get("created", ""),
        "updated": scalars.get("updated", ""),
    }
    output = ["---"]
    for key in RESOURCE_FIELDS:
        if key == "tags":
            output.append("tags:")
            output.extend(f"  - {tag}" for tag in tags)
        elif key == "aliases":
            output.append("aliases:")
            output.extend(f"  - {alias}" for alias in aliases)
        else:
            output.append(f"{key}: {values[key]}" if values[key] else f"{key}:")
    output.append("---")
    return "\n".join(output)


def transform(path: Path, args: argparse.Namespace) -> tuple[str, str]:
    original = path.read_text(encoding="utf-8")
    lines = original.splitlines()
    _start, closing = frontmatter_bounds(lines)
    scalars, lists, keys = parse_frontmatter(lines[1:closing])
    unknown = sorted(set(keys) - set(RESOURCE_FIELDS))
    if unknown:
        raise ValueError(f"unsupported existing frontmatter fields: {', '.join(unknown)}")
    body = "\n".join(lines[closing + 1 :]).rstrip()
    if START not in body or END not in body:
        raise ValueError("note does not contain complete Codex generated markers")
    frontmatter = render_frontmatter(scalars, lists, args)
    transformed = f"{frontmatter}\n{body}\n"
    return original, transformed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("notes_root", help="Directory containing the existing video notes")
    parser.add_argument("--creator", default="Komaki Zhu")
    parser.add_argument("--resource-type", default="Resource")
    parser.add_argument("--topic", default="AI工程与智能体技术")
    parser.add_argument("--subject", default="技术与效率系统")
    parser.add_argument("--status", default="fruit")
    parser.add_argument("--tag", dest="tags", action="append", default=[])
    parser.add_argument("--expected-count", type=int)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = Path(args.notes_root).expanduser().resolve()
    if not root.is_dir():
        return fail(f"notes directory does not exist: {root}")
    paths = sorted(root.glob("*.md"))
    if args.expected_count is not None and len(paths) != args.expected_count:
        return fail(f"expected {args.expected_count} Markdown notes, found {len(paths)}")

    changes: list[tuple[Path, str]] = []
    for path in paths:
        try:
            original, transformed = transform(path, args)
        except (OSError, UnicodeError, ValueError) as exc:
            return fail(f"{path}: {exc}")
        if original != transformed:
            changes.append((path, transformed))

    if not args.dry_run:
        for path, transformed in changes:
            path.write_text(transformed, encoding="utf-8")
    print(f"resource template {'would update' if args.dry_run else 'updated'} {len(changes)} note(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
