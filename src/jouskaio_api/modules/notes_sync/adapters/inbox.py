"""Reads the files that Notability's Auto-Backup writes into a folder."""

import unicodedata
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path

from jouskaio_api.core.errors import ExternalServiceError
from jouskaio_api.modules.notes_sync.domain import SourceNote


def _utcnow() -> datetime:
    return datetime.now(UTC)


class FolderInboxSource:
    """Yields every regular, non-hidden file under ``root`` that is old enough.

    Files modified less than ``min_age_seconds`` ago are skipped: they may still be
    being uploaded (WebDAV) and will be picked up by the next run.
    """

    def __init__(
        self,
        root: Path,
        min_age_seconds: int = 10,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._root = root
        self._min_age = min_age_seconds
        self._clock = clock

    def iter_notes(self) -> Iterator[SourceNote]:
        if not self._root.is_dir():
            raise ExternalServiceError(f"Inbox directory not found: {self._root}")
        now = self._clock()
        for path in sorted(self._root.rglob("*")):
            relative = path.relative_to(self._root)
            if path.is_symlink() or not path.is_file():
                continue
            if any(part.startswith(".") for part in relative.parts):
                continue
            modified_at = datetime.fromtimestamp(path.stat().st_mtime, UTC)
            if (now - modified_at).total_seconds() < self._min_age:
                continue
            # iPadOS/macOS may hand us NFD file names; normalise so keys stay stable.
            key = unicodedata.normalize("NFC", relative.as_posix())
            yield SourceNote(key=key, path=path, modified_at=modified_at)
