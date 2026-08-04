#!/usr/bin/env python3
"""Scan video/SRT batches and safely sync generated notes into an Obsidian Vault."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

try:
    from validate_note import LINK_PATTERN, validate
except ImportError:  # pragma: no cover - supports direct module loading
    LINK_PATTERN = None  # type: ignore[assignment]
    validate = None  # type: ignore[assignment]


DEFAULT_NOTES_FOLDER = "视频笔记"
DEFAULT_MEDIA_FOLDER = "媒体"
DEFAULT_SUBTITLE_LANGUAGE = "zh"
SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".webm", ".m4v", ".avi"}
CHINESE_SUFFIXES = (".zh", "_zh", "-zh", ".zh-cn", "_zh-cn", "-zh-cn", ".中文", "_中文", "-中文")
SUMMARY_START = "<!-- codex:video-note-summary:start -->"
SUMMARY_END = "<!-- codex:video-note-summary:end -->"
BODY_START = "<!-- codex:video-note-body:start -->"
BODY_END = "<!-- codex:video-note-body:end -->"
SRT_START_PATTERN = re.compile(
    r"^(?P<start>\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*\d{2}:\d{2}:\d{2}[,.]\d{3}"
)


def default_config_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config.json"


def fail(message: str, code: int = 2) -> int:
    print(f"ERROR: {message}", file=sys.stderr)
    return code


def ensure_relative_folder(value: str, field: str) -> str:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{field} must be a relative folder inside the configured Vault")
    cleaned = value.strip("/\\")
    if not cleaned or cleaned == ".":
        raise ValueError(f"{field} must not be empty")
    return cleaned.replace("\\", "/")


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValueError(f"Vault is not configured; run configure first: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    vault_root = Path(str(data.get("vault_root", ""))).expanduser()
    if not vault_root.is_absolute() or not vault_root.is_dir():
        raise ValueError(f"configured vault_root is not an existing directory: {vault_root}")
    data["vault_root"] = str(vault_root.resolve())
    data["notes_folder"] = ensure_relative_folder(
        str(data.get("notes_folder", DEFAULT_NOTES_FOLDER)), "notes_folder"
    )
    data["media_folder"] = ensure_relative_folder(
        str(data.get("media_folder", DEFAULT_MEDIA_FOLDER)), "media_folder"
    )
    data["subtitle_language"] = str(
        data.get("subtitle_language", DEFAULT_SUBTITLE_LANGUAGE)
    )
    return data


def write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    os.replace(temporary, path)


def configure(args: argparse.Namespace) -> int:
    config_path = Path(args.config).expanduser().resolve()
    vault_root = Path(args.vault).expanduser().resolve()
    if not vault_root.is_dir():
        return fail(f"Vault directory does not exist: {vault_root}")
    try:
        notes_folder = ensure_relative_folder(args.notes_folder, "notes_folder")
        media_folder = ensure_relative_folder(args.media_folder, "media_folder")
    except ValueError as exc:
        return fail(str(exc))
    data = {
        "vault_root": str(vault_root),
        "notes_folder": notes_folder,
        "media_folder": media_folder,
        "subtitle_language": args.subtitle_language,
    }
    write_json_atomic(config_path, data)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def supported_video(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in SUPPORTED_VIDEO_EXTENSIONS


def resolve_video_input(raw: str) -> Path:
    path = Path(raw).expanduser()
    if not path.exists() and not path.suffix:
        candidate = Path(f"{path}.mp4")
        if candidate.exists():
            path = candidate
    return path.resolve()


def is_inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def scan_root(input_path: Path, configured_output: Path) -> tuple[Path, list[Path]]:
    if input_path.is_dir():
        root = input_path
        candidates = [
            path
            for path in root.rglob("*")
            if supported_video(path)
            and not path.is_symlink()
            and not is_inside(path, configured_output)
        ]
    elif supported_video(input_path):
        root = input_path.parent
        candidates = [
            path
            for path in root.rglob("*")
            if supported_video(path)
            and not path.is_symlink()
            and not is_inside(path, configured_output)
        ]
    else:
        raise ValueError(f"video path is not a supported video file or directory: {input_path}")
    candidates = sorted({path.resolve() for path in candidates}, key=lambda p: str(p))
    if not candidates:
        raise ValueError(f"no supported videos found below: {root}")
    return root.resolve(), candidates


def chinese_srt_candidate(video: Path, srt: Path) -> bool:
    stem = video.stem.casefold()
    name = srt.name.casefold()
    if not name.endswith(".srt"):
        return False
    base = name[:-4]
    return any(base == f"{stem}{suffix}" for suffix in CHINESE_SUFFIXES)


def exact_srt_candidate(video: Path, srt: Path) -> bool:
    return srt.name.casefold() == f"{video.stem.casefold()}.srt"


def match_srt(video: Path) -> tuple[Path | None, str | None]:
    candidates = sorted(
        [path for path in video.parent.iterdir() if path.is_file() and path.suffix.lower() == ".srt"],
        key=lambda p: str(p),
    )
    exact = [path for path in candidates if exact_srt_candidate(video, path)]
    if len(exact) == 1:
        return exact[0], None
    if len(exact) > 1:
        return None, "multiple exact-name SRT files found"

    chinese = [path for path in candidates if chinese_srt_candidate(video, path)]
    if len(chinese) == 1:
        return chinese[0], None
    if len(chinese) > 1:
        return None, "multiple Chinese SRT files found"
    return None, "matching SRT not found"


def parse_srt_time(raw: str) -> int:
    hours, minutes, seconds_millis = raw.replace(".", ",").split(":")
    seconds, millis = seconds_millis.split(",")
    base = int(hours) * 3600 + int(minutes) * 60 + int(seconds)
    return base + (1 if int(millis) >= 500 else 0)


def parse_srt_start_seconds(path: Path) -> tuple[list[int], str | None]:
    starts: list[int] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        match = SRT_START_PATTERN.match(line.strip())
        if match:
            starts.append(parse_srt_time(match.group("start")))
    if not starts:
        return [], "SRT contains no valid timestamp ranges"
    return sorted(set(starts)), None


def relative_posix(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def build_item(video: Path, root: Path, config: dict[str, Any]) -> dict[str, Any]:
    srt_path, reason = match_srt(video)
    srt_timestamps: list[int] = []
    if srt_path:
        try:
            srt_timestamps, parse_reason = parse_srt_start_seconds(srt_path)
        except (OSError, UnicodeError) as exc:
            parse_reason = f"unable to read SRT: {exc}"
        if parse_reason:
            srt_path = None
            reason = parse_reason
    relative_video = relative_posix(video, root)
    relative_dir = Path(relative_video).parent.as_posix()
    if relative_dir == ".":
        relative_dir = ""
    stem = Path(relative_video).stem
    note_relative = f"{relative_dir}/{stem}.md" if relative_dir else f"{stem}.md"
    media_relative = f"{relative_dir}/{Path(relative_video).name}" if relative_dir else Path(relative_video).name
    media_link = f"{config['media_folder']}/{media_relative}"
    status = "ready" if srt_path else ("conflict" if reason != "matching SRT not found" else "skipped")
    return {
        "video_path": str(video),
        "srt_path": str(srt_path) if srt_path else None,
        "srt_timestamps": srt_timestamps,
        "relative_video": relative_video,
        "title": stem,
        "note_relative": note_relative,
        "media_relative": media_relative,
        "media_link": media_link,
        "status": status,
        "reason": reason,
    }


def scan(args: argparse.Namespace) -> int:
    config_path = Path(args.config).expanduser().resolve()
    try:
        config = load_config(config_path)
        input_path = resolve_video_input(args.video)
        output_root = Path(config["vault_root"]) / config["notes_folder"]
        root, videos = scan_root(input_path, output_root)
        items = [build_item(video, root, config) for video in videos]
        note_targets: dict[str, list[dict[str, Any]]] = {}
        for item in items:
            note_targets.setdefault(item["note_relative"], []).append(item)
        for duplicate_items in note_targets.values():
            if len(duplicate_items) > 1:
                for item in duplicate_items:
                    item["status"] = "conflict"
                    item["reason"] = "note path collision"
        manifest = {
            "version": 1,
            "config_path": str(config_path),
            "vault_root": config["vault_root"],
            "notes_folder": config["notes_folder"],
            "media_folder": config["media_folder"],
            "scan_root": str(root),
            "items": items,
        }
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return fail(str(exc))

    rendered = json.dumps(manifest, ensure_ascii=False, indent=2)
    if args.output:
        output = Path(args.output).expanduser().resolve()
        write_json_atomic(output, manifest)
        print(output)
    else:
        print(rendered)
    return 0


def line_index(lines: list[str], value: str) -> int:
    try:
        return next(index for index, line in enumerate(lines) if line.strip() == value)
    except StopIteration:
        return -1


def inject_markers(markdown: str) -> str:
    if all(marker in markdown for marker in (SUMMARY_START, SUMMARY_END, BODY_START, BODY_END)):
        return markdown
    lines = markdown.splitlines()
    summary = line_index(lines, "## 核心总结")
    body = line_index(lines, "## 正文")
    if summary < 0 or body < 0 or body <= summary:
        raise ValueError("generated note must contain ## 核心总结 before ## 正文")
    lines.insert(summary + 1, SUMMARY_START)
    body += 1
    lines.insert(body, SUMMARY_END)
    lines.insert(body + 2, BODY_START)
    lines.append(BODY_END)
    return "\n".join(lines).rstrip() + "\n"


def replace_marker_block(existing: str, generated: str, start: str, end: str) -> str:
    start_existing = existing.find(start)
    end_existing = existing.find(end)
    start_generated = generated.find(start)
    end_generated = generated.find(end)
    if min(start_existing, end_existing, start_generated, end_generated) < 0 or end_existing < start_existing or end_generated < start_generated:
        raise ValueError("generated marker block is incomplete")
    replacement = generated[start_generated : end_generated + len(end)]
    return existing[:start_existing] + replacement + existing[end_existing + len(end) :]


def merge_note(existing: str | None, generated: str) -> tuple[str, str]:
    if existing is None:
        return generated, "created"
    if not all(marker in existing for marker in (SUMMARY_START, SUMMARY_END, BODY_START, BODY_END)):
        raise ValueError("existing note has no Codex generated markers")
    merged = replace_marker_block(existing, generated, SUMMARY_START, SUMMARY_END)
    merged = replace_marker_block(merged, generated, BODY_START, BODY_END)
    return merged, "updated"


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        handle.write(text)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def safe_target(root: Path, relative: str) -> Path:
    target = (root / Path(relative)).resolve()
    if not is_inside(target, root):
        raise ValueError(f"target escapes configured root: {relative}")
    return target


def read_generated_content(content_root: Path, item: dict[str, Any]) -> str:
    content_path = safe_target(content_root, item["note_relative"])
    if not content_path.is_file():
        raise ValueError(f"generated Markdown is missing: {content_path}")
    return inject_markers(content_path.read_text(encoding="utf-8"))


def validate_source_timestamps(markdown: str, item: dict[str, Any]) -> list[str]:
    if LINK_PATTERN is None:
        return ["validate_note.py could not provide its timestamp link pattern"]
    allowed = set(item.get("srt_timestamps", []))
    expected_target = item["media_link"]
    errors: list[str] = []
    for match in LINK_PATTERN.finditer(markdown):
        filename, raw_seconds, _label = match.groups()
        seconds = int(raw_seconds)
        if filename != expected_target:
            errors.append(f"timestamp link target '{filename}' does not match '{expected_target}'")
        if seconds not in allowed:
            errors.append(f"#t={seconds} is not an SRT start timestamp for {item['video_path']}")
    return errors


def commit(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest).expanduser().resolve()
    content_root = Path(args.content_dir).expanduser().resolve()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        vault_root = Path(manifest["vault_root"]).expanduser().resolve()
        notes_root = safe_target(vault_root, manifest["notes_folder"])
        media_root = safe_target(notes_root, manifest["media_folder"])
        if not vault_root.is_dir():
            raise ValueError(f"Vault directory does not exist: {vault_root}")
        if validate is None:
            raise ValueError("validate_note.py could not be imported")

        prepared: list[dict[str, Any]] = []
        report: dict[str, list[dict[str, Any]]] = {
            "created": [],
            "updated": [],
            "skipped": [],
            "conflicts": [],
        }
        for item in manifest.get("items", []):
            if item.get("status") != "ready":
                bucket = "conflicts" if item.get("status") == "conflict" else "skipped"
                report[bucket].append({"video": item.get("video_path"), "reason": item.get("reason")})
                continue
            source = Path(item["video_path"]).expanduser().resolve()
            note_target = safe_target(notes_root, item["note_relative"])
            media_target = safe_target(media_root, item["media_relative"])
            generated = read_generated_content(content_root, item)
            errors = validate(generated, require_template=True, allow_generated_markers=True)
            errors.extend(validate_source_timestamps(generated, item))
            if errors:
                raise ValueError(f"invalid generated note for {item['video_path']}: {'; '.join(errors)}")
            existing = note_target.read_text(encoding="utf-8") if note_target.exists() else None
            try:
                merged, note_action = merge_note(existing, generated)
            except ValueError as exc:
                report["conflicts"].append({"video": item["video_path"], "target": str(note_target), "reason": str(exc)})
                continue
            if os.path.lexists(media_target):
                if not media_target.is_symlink() or media_target.resolve() != source:
                    report["conflicts"].append({"video": item["video_path"], "target": str(media_target), "reason": "media target exists and is not the expected symlink"})
                    continue
            prepared.append({"item": item, "source": source, "note_target": note_target, "media_target": media_target, "merged": merged, "note_action": note_action})

        if report["conflicts"] and args.fail_on_conflict:
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 1

        created_links: list[Path] = []
        try:
            for entry in prepared:
                entry["media_target"].parent.mkdir(parents=True, exist_ok=True)
                if not os.path.lexists(entry["media_target"]):
                    os.symlink(str(entry["source"]), str(entry["media_target"]))
                    created_links.append(entry["media_target"])
                write_text_atomic(entry["note_target"], entry["merged"])
                report[entry["note_action"]].append({"video": entry["item"]["video_path"], "note": str(entry["note_target"]), "media": str(entry["media_target"])})
        except OSError:
            for link in reversed(created_links):
                if link.is_symlink():
                    link.unlink()
            raise
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return fail(str(exc))

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["conflicts"] else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    configure_parser = subparsers.add_parser("configure")
    configure_parser.add_argument("--vault", required=True)
    configure_parser.add_argument("--config", default=str(default_config_path()))
    configure_parser.add_argument("--notes-folder", default=DEFAULT_NOTES_FOLDER)
    configure_parser.add_argument("--media-folder", default=DEFAULT_MEDIA_FOLDER)
    configure_parser.add_argument("--subtitle-language", default=DEFAULT_SUBTITLE_LANGUAGE)
    configure_parser.set_defaults(handler=configure)

    scan_parser = subparsers.add_parser("scan")
    scan_parser.add_argument("video")
    scan_parser.add_argument("--config", default=str(default_config_path()))
    scan_parser.add_argument("--output")
    scan_parser.set_defaults(handler=scan)

    commit_parser = subparsers.add_parser("commit")
    commit_parser.add_argument("--manifest", required=True)
    commit_parser.add_argument("--content-dir", required=True)
    commit_parser.add_argument("--fail-on-conflict", action="store_true")
    commit_parser.set_defaults(handler=commit)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
