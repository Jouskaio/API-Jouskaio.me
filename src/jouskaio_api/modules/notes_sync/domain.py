"""Plain objects of the notes_sync domain."""

import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath


@dataclass(frozen=True, slots=True)
class SourceNote:
    """A file exported by Notability, as found in the inbox."""

    key: str
    """Stable identity: the inbox-relative POSIX path, Unicode NFC normalised."""

    path: Path
    modified_at: datetime

    @property
    def suffix(self) -> str:
        return self.path.suffix.lower()

    @property
    def stem(self) -> str:
        return PurePosixPath(self.key).stem

    def digest(self) -> str:
        """SHA-256 of the file content, read in chunks."""
        sha = hashlib.sha256()
        with self.path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                sha.update(chunk)
        return sha.hexdigest()


@dataclass(frozen=True, slots=True)
class ConvertedNote:
    """What a converter produces; the vault decides where and how to store it."""

    title: str
    body: str = ""
    attachment: Path | None = None
    """A file to store next to the note and embed in it (the original PDF)."""

    pipeline: str = ""
    """The processing actually applied; differs from the converter's fingerprint when an
    enrichment (text extraction, OCR) failed, so the note is retried on the next run."""


@dataclass(frozen=True, slots=True)
class VaultWrite:
    path: str
    """Vault-relative POSIX path of the Markdown note."""

    created: bool
