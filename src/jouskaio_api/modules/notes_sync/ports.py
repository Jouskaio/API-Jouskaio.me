"""Ports: what the sync service needs, independent of any library or filesystem layout."""

from collections.abc import Iterator
from pathlib import Path
from typing import Protocol

from jouskaio_api.modules.notes_sync.domain import ConvertedNote, SourceNote, VaultWrite
from jouskaio_api.modules.notes_sync.schemas import SyncRecord


class NoteSource(Protocol):
    def iter_notes(self) -> Iterator[SourceNote]: ...


class NoteConverter(Protocol):
    @property
    def suffixes(self) -> frozenset[str]: ...

    @property
    def fingerprint(self) -> str:
        """Identifies the processing a successful conversion applies (e.g. with OCR or not).

        A note whose stored pipeline differs from this value is converted again, so enabling
        OCR later, or recovering from a degraded conversion, reprocesses existing notes.
        """
        ...

    def convert(self, note: SourceNote) -> ConvertedNote: ...


class TextExtractor(Protocol):
    def extract(self, pdf: Path) -> str: ...


class HandwritingRecognizer(Protocol):
    @property
    def fingerprint(self) -> str: ...

    def recognize(self, pdf: Path) -> list[str]:
        """Text read on each page, in page order ('' for a page without handwriting)."""
        ...


class VaultWriter(Protocol):
    def exists(self, vault_path: str) -> bool: ...

    def publish(self, note: SourceNote, converted: ConvertedNote) -> VaultWrite: ...


class SyncStateStore(Protocol):
    def get(self, key: str) -> SyncRecord | None: ...

    def put(self, record: SyncRecord) -> None: ...

    def all(self) -> list[SyncRecord]: ...
