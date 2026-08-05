#!/usr/bin/env python3
"""Validate isolated Obsidian video-note formatting."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


LINK_PATTERN = re.compile(
    r"\[\[([^\n#]+)#t=(\d+)(?:\\)?\|((?:\d{2}:)?\d{2}:\d{2})\]\]"
)
LINK_CANDIDATE_PATTERN = re.compile(r"\[\[[^\n]*#t=[^\n]*\]\]")
TIME_TOKEN = r"(?:\d{1,2}:)?\d{1,3}:\d{2}"
RANGE_PATTERN = re.compile(
    rf"(?<!\d){TIME_TOKEN}\s*(?:-|–|—|~|至)\s*{TIME_TOKEN}(?!\d)"
)
SINGLE_TIME_PATTERN = re.compile(rf"(?<!\d){TIME_TOKEN}(?!\d)")
LIST_PATTERN = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)")
H1_PATTERN = re.compile(r"^\s{0,3}#(?!#)\s+")
HEADING_PATTERN = re.compile(r"^\s{0,3}#{1,6}\s+")
SUMMARY_HEADING = "## 核心总结"
BODY_HEADING = "## 正文"
SUMMARY_HEADERS = ["总结维度", "核心知识点", "时间戳"]
SUMMARY_START = "<!-- codex:video-note-summary:start -->"
SUMMARY_END = "<!-- codex:video-note-summary:end -->"
BODY_START = "<!-- codex:video-note-body:start -->"
BODY_END = "<!-- codex:video-note-body:end -->"


def parse_time(value: str) -> int | None:
    """Return total seconds for MM:SS or HH:MM:SS, or None if invalid."""
    parts = value.split(":")
    if len(parts) == 2:
        hours = 0
        minutes, seconds = (int(part) for part in parts)
    elif len(parts) == 3:
        hours, minutes, seconds = (int(part) for part in parts)
    else:
        return None

    if minutes < 0 or seconds < 0 or seconds >= 60:
        return None
    if len(parts) == 3 and minutes >= 60:
        return None
    return hours * 3600 + minutes * 60 + seconds


def format_time(total_seconds: int) -> str:
    """Format seconds as MM:SS below one hour, otherwise HH:MM:SS."""
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{total_seconds // 60:02d}:{seconds:02d}"


def split_table_row(line: str) -> list[str] | None:
    """Split a Markdown table row without splitting pipes inside wikilinks."""
    stripped = line.strip()
    if not stripped.startswith("|"):
        return None

    body = stripped[1:]
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]

    cells: list[str] = []
    current: list[str] = []
    in_wikilink = False
    escaped = False
    index = 0

    while index < len(body):
        if body.startswith("[[", index):
            in_wikilink = True
            current.extend("[[")
            index += 2
            continue
        if body.startswith("]]", index) and in_wikilink:
            in_wikilink = False
            current.extend("]]" )
            index += 2
            continue

        char = body[index]
        if char == "|" and not in_wikilink and not escaped:
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(char)

        escaped = char == "\\" and not escaped
        if char != "\\":
            escaped = False
        index += 1

    cells.append("".join(current).strip())
    return cells


def is_separator_row(cells: list[str]) -> bool:
    return bool(cells) and all(
        re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells
    )


def find_frontmatter_end(lines: list[str]) -> tuple[int, str | None]:
    if not lines or lines[0].strip() != "---":
        return 0, None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return index + 1, None
    return len(lines), "YAML frontmatter has no closing delimiter"


def validate_link(match: re.Match[str], line_number: int) -> list[str]:
    filename, raw_seconds, label = match.groups()
    errors: list[str] = []
    seconds = int(raw_seconds)
    label_seconds = parse_time(label)

    if not filename.strip():
        errors.append(f"line {line_number}: video filename is empty")
    if label_seconds is None:
        errors.append(f"line {line_number}: invalid display time '{label}'")
    elif label_seconds != seconds:
        errors.append(
            f"line {line_number}: display time '{label}' does not match #t={seconds}"
        )
    elif label != format_time(seconds):
        errors.append(
            f"line {line_number}: display time '{label}' should be '{format_time(seconds)}'"
        )
    return errors


def validate_summary(lines: list[str], start: int, errors: list[str], allow_short: bool) -> int:
    """Validate the summary table and return the first line after it."""
    index = start
    while index < len(lines) and not lines[index].strip():
        index += 1

    if index >= len(lines) or not H1_PATTERN.match(lines[index]):
        errors.append("note must start with a level-one title before the summary")
        return index
    summary_index = next(
        (candidate for candidate in range(index + 1, len(lines)) if lines[candidate].strip() == SUMMARY_HEADING),
        None,
    )
    if summary_index is None:
        errors.append("summary must contain '## 核心总结'")
        return index
    index = summary_index + 1

    while index < len(lines) and (
        not lines[index].strip() or lines[index].strip() == SUMMARY_START
    ):
        index += 1
    header = split_table_row(lines[index]) if index < len(lines) else None
    if header != SUMMARY_HEADERS:
        errors.append("summary table headers must be: 总结维度 | 核心知识点 | 时间戳")
        return index
    index += 1

    while index < len(lines) and not lines[index].strip():
        index += 1
    separator = split_table_row(lines[index]) if index < len(lines) else None
    if separator is None or not is_separator_row(separator):
        errors.append("summary table is missing a valid separator row")
        return index
    index += 1

    data_rows: list[tuple[int, list[str]]] = []
    while index < len(lines):
        if not lines[index].strip():
            break
        row = split_table_row(lines[index])
        if row is None:
            break
        data_rows.append((index + 1, row))
        index += 1

    minimum = 1 if allow_short else 3
    if len(data_rows) < minimum:
        errors.append(
            f"summary must contain {minimum}-5 knowledge-point rows; found {len(data_rows)}"
        )
    if len(data_rows) > 5:
        errors.append(f"summary must contain no more than 5 knowledge-point rows; found {len(data_rows)}")

    for line_number, row in data_rows:
        if len(row) != 3:
            errors.append(
                f"line {line_number}: summary row must contain exactly three cells"
            )
            continue
        links = list(LINK_PATTERN.finditer(row[2]))
        if len(links) != 1 or links[0].group(0) != row[2].strip():
            errors.append(
                f"line {line_number}: timestamp cell must contain exactly one complete video link"
            )

    return index


def validate_template(
    lines: list[str],
    errors: list[str],
    allow_generated_markers: bool,
) -> None:
    headings = [(index, line.strip()) for index, line in enumerate(lines) if H1_PATTERN.match(line) or HEADING_PATTERN.match(line)]
    h1_indexes = [index for index, heading in headings if H1_PATTERN.match(lines[index])]
    if not h1_indexes or h1_indexes[0] != 0:
        errors.append("note must start with a level-one title")
    summary_index = next((index for index, heading in headings if heading == SUMMARY_HEADING), None)
    body_index = next((index for index, heading in headings if heading == BODY_HEADING), None)
    if summary_index is None:
        errors.append("note must contain '## 核心总结'")
    if body_index is None:
        errors.append("note must contain '## 正文'")
    if summary_index is not None and body_index is not None and summary_index > body_index:
        errors.append("'## 核心总结' must appear before '## 正文'")

    level_two = [heading for index, heading in headings if HEADING_PATTERN.match(lines[index]) and lines[index].lstrip().startswith("## ")]
    unexpected = [heading for heading in level_two if heading not in {SUMMARY_HEADING, BODY_HEADING}]
    if unexpected:
        errors.append(f"only '## 核心总结' and '## 正文' are allowed as level-two headings: {unexpected}")

    marker_set = {SUMMARY_START, SUMMARY_END, BODY_START, BODY_END}
    present = {line.strip() for line in lines if line.strip() in marker_set}
    if present and present != marker_set:
        errors.append("generated note markers must appear as a complete set")
    if not allow_generated_markers and present:
        errors.append("generated note markers are not allowed in this validation mode")

    if summary_index is not None and body_index is not None and body_index > summary_index:
        summary_lines = lines[summary_index:body_index]
        table_start = next((idx for idx, line in enumerate(summary_lines) if split_table_row(line) == SUMMARY_HEADERS), None)
        if table_start is None:
            errors.append("## 核心总结 must contain the standard three-column table")

    if body_index is not None:
        body_lines = lines[body_index + 1 :]
        for index, line in enumerate(body_lines):
            if LINK_PATTERN.fullmatch(line.strip()):
                following = next((candidate.strip() for candidate in body_lines[index + 1 :] if candidate.strip()), "")
                if not following or HEADING_PATTERN.match(following) or LIST_PATTERN.match(following):
                    errors.append(f"line {body_index + index + 2}: timestamp must be followed by a prose paragraph")


def path_error(path: str, allowed_root: str | None) -> str | None:
    resolved = Path(path).expanduser().resolve()
    if allowed_root:
        root = Path(allowed_root).expanduser().resolve()
        if resolved != root and root not in resolved.parents:
            return f"path is outside the allowed isolated root: {resolved}"
    return None


def read_input(path: str | None, allowed_root: str | None) -> str:
    if path:
        error = path_error(path, allowed_root)
        if error:
            raise ValueError(error)
        return Path(path).read_text(encoding="utf-8")
    return sys.stdin.read()


def validate(
    markdown: str,
    allow_lists: bool = False,
    allow_frontmatter: bool = False,
    require_summary: bool = False,
    allow_short_summary: bool = False,
    require_template: bool = False,
    allow_generated_markers: bool = False,
) -> list[str]:
    errors: list[str] = []
    lines = markdown.splitlines()
    content_start, frontmatter_error = find_frontmatter_end(lines)

    if frontmatter_error:
        errors.append(frontmatter_error)
    if content_start and not allow_frontmatter:
        errors.append("YAML frontmatter is not allowed in the generated note")

    if require_template:
        validate_summary(lines, content_start, errors, allow_short_summary)
        validate_template(lines[content_start:], errors, allow_generated_markers)
    elif require_summary:
        validate_summary(lines, content_start, errors, allow_short_summary)

    first_h1 = next(
        (index for index, line in enumerate(lines[content_start:], start=content_start) if H1_PATTERN.match(line)),
        None,
    )
    if require_summary and first_h1 is not None:
        summary_heading = next(
            (index for index, line in enumerate(lines[content_start:], start=content_start) if line.strip() == SUMMARY_HEADING),
            None,
        )
        if summary_heading is not None and first_h1 is not None and summary_heading < first_h1:
            errors.append("summary must appear after the first level-one heading")

    in_fence = False
    for line_number, line in enumerate(lines[content_start:], start=content_start + 1):
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        if HEADING_PATTERN.match(line):
            if RANGE_PATTERN.search(line) or SINGLE_TIME_PATTERN.search(line):
                errors.append(
                    f"line {line_number}: heading contains a timestamp or time range"
                )
            if first_h1 is not None and line_number - 1 > first_h1 and stripped == "## 核心知识点":
                errors.append(f"line {line_number}: legacy core-summary heading is not allowed")

        if not allow_lists and LIST_PATTERN.match(line):
            errors.append(f"line {line_number}: list syntax is not allowed by default")

        for candidate in LINK_CANDIDATE_PATTERN.finditer(line):
            if not LINK_PATTERN.fullmatch(candidate.group(0)):
                errors.append(
                    f"line {line_number}: malformed Obsidian video timestamp link"
                )

        for match in LINK_PATTERN.finditer(line):
            errors.extend(validate_link(match, line_number))

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", help="Markdown file; read stdin when omitted")
    parser.add_argument(
        "--allowed-root",
        help="Reject file paths outside this Codex isolation root",
    )
    parser.add_argument(
        "--allow-frontmatter",
        action="store_true",
        help="Allow existing frontmatter in an isolated note copy",
    )
    parser.add_argument(
        "--require-summary",
        action="store_true",
        help="Require the timestamped 3-5 row summary table after the H1 title",
    )
    parser.add_argument(
        "--require-template",
        action="store_true",
        help="Require the title, core-summary table, and body structure",
    )
    parser.add_argument(
        "--allow-generated-markers",
        action="store_true",
        help="Allow complete Codex generated-content markers",
    )
    parser.add_argument(
        "--allow-short-summary",
        action="store_true",
        help="Allow one or two summary rows when the source is too short",
    )
    parser.add_argument(
        "--allow-lists",
        action="store_true",
        help="Allow Markdown bullet and numbered lists for an explicit user request",
    )
    args = parser.parse_args()

    try:
        markdown = read_input(args.path, args.allowed_root)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    errors = validate(
        markdown,
        allow_lists=args.allow_lists,
        allow_frontmatter=args.allow_frontmatter,
        require_summary=args.require_summary,
        allow_short_summary=args.allow_short_summary,
        require_template=args.require_template,
        allow_generated_markers=args.allow_generated_markers,
    )
    if errors:
        print("INVALID")
        for error in errors:
            print(f"- {error}")
        return 1

    link_count = len(LINK_PATTERN.findall(markdown))
    print(f"VALID: {link_count} timestamp link(s) checked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
