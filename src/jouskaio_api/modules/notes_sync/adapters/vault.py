"""Writes notes into an Obsidian vault without ever clobbering the user's own edits.

Each generated note holds one *managed block* delimited by HTML comments. On update only
that block is replaced: anything the user writes above or below it is preserved. A file
that exists but is not managed by the same source is reported as a conflict, never
overwritten.
"""

import json
import re
import shutil
import unicodedata
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from jouskaio_api.core.errors import ConflictError, DomainError
from jouskaio_api.modules.notes_sync.domain import ConvertedNote, SourceNote, VaultWrite

BEGIN = "<!-- notability:begin -->"
END = "<!-- notability:end -->"

# Characters that are illegal on some OS or that Obsidian forbids in note names.
_FORBIDDEN = re.compile(r'[\\/:*?"<>|#^\[\]]')
_SOURCE_LINE = re.compile(r"^notability_source: (.+)$", re.MULTILINE)
_SYNCED_LINE = re.compile(r"^notability_synced_at: .*$", re.MULTILINE)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _safe_part(part: str) -> str:
    cleaned = _FORBIDDEN.sub("-", unicodedata.normalize("NFC", part)).strip().rstrip(".")
    return cleaned or "untitled"


def _split_frontmatter(text: str) -> tuple[str, str]:
    if text.startswith("---\n"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[: end + 4], text[end + 4 :]
    return "", text


def _source_of(frontmatter: str) -> object:
    match = _SOURCE_LINE.search(frontmatter)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, "utf-8")
    tmp.replace(path)


def _atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_name(destination.name + ".tmp")
    shutil.copy2(source, tmp)
    tmp.replace(destination)


class ObsidianVault:
    def __init__(
        self,
        root: Path,
        notes_subdir: str,
        attachments_subdir: str,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._root = root.resolve()
        self._notes_root = self._root / notes_subdir
        self._attachments_root = self._root / attachments_subdir
        self._clock = clock

    def exists(self, vault_path: str) -> bool:
        return self._confine(self._root / vault_path).is_file()

    def publish(self, note: SourceNote, converted: ConvertedNote) -> VaultWrite:
        relative = PurePosixPath(note.key)
        folders = [_safe_part(part) for part in relative.parent.parts]
        stem = _safe_part(relative.stem)

        note_path = self._confine(self._notes_root.joinpath(*folders, f"{stem}.md"))
        embed: str | None = None
        if converted.attachment is not None:
            attachment_path = self._confine(
                self._attachments_root.joinpath(*folders, f"{stem}{note.suffix}")
            )
            _atomic_copy(converted.attachment, attachment_path)
            embed = f"![[{attachment_path.relative_to(self._root).as_posix()}]]"

        block = self._render_block(embed, converted.body)
        timestamp = self._clock().isoformat()
        created = not note_path.exists()
        if created:
            _atomic_write_text(note_path, self._render_new(note.key, timestamp, block))
        else:
            _atomic_write_text(
                note_path, self._render_update(note_path, note.key, timestamp, block)
            )
        return VaultWrite(path=note_path.relative_to(self._root).as_posix(), created=created)

    def _confine(self, path: Path) -> Path:
        resolved = path.resolve()
        if not resolved.is_relative_to(self._root):
            raise DomainError(f"Refusing to touch a path outside the vault: {path}")
        return resolved

    @staticmethod
    def _render_block(embed: str | None, body: str) -> str:
        content = "\n\n".join(part for part in (embed, body) if part)
        return f"{BEGIN}\n{content}\n{END}" if content else f"{BEGIN}\n{END}"

    @staticmethod
    def _render_new(key: str, timestamp: str, block: str) -> str:
        return (
            "---\n"
            f"notability_source: {json.dumps(key, ensure_ascii=False)}\n"
            f"notability_synced_at: {timestamp}\n"
            "tags:\n"
            "  - notability\n"
            "---\n\n"
            f"{block}\n"
        )

    @staticmethod
    def _render_update(note_path: Path, key: str, timestamp: str, block: str) -> str:
        existing = note_path.read_text("utf-8")
        frontmatter, rest = _split_frontmatter(existing)
        if _source_of(frontmatter) != key:
            raise ConflictError(
                f"{note_path.name} already exists and is not managed by this source"
            )
        try:
            start = rest.index(BEGIN)
            stop = rest.index(END, start) + len(END)
        except ValueError as exc:
            raise ConflictError(
                f"{note_path.name}: managed block markers are missing, refusing to overwrite"
            ) from exc
        frontmatter = _SYNCED_LINE.sub(lambda _: f"notability_synced_at: {timestamp}", frontmatter)
        return frontmatter + rest[:start] + block + rest[stop:]
