"""Settings of the notes_sync module (``JOUSKAIO_NOTES_SYNC_*``).

Defaults match the mount points of the Docker image: /inbox, /vault and /data.
"""

from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class NotesSyncSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="JOUSKAIO_NOTES_SYNC_", env_file=".env", extra="ignore"
    )

    inbox_dir: Path = Path("/inbox")
    """Folder where Notability's Auto-Backup drops its exports (PDF / RTF)."""

    vault_dir: Path = Path("/vault")
    """Root of the Obsidian vault."""

    notes_subdir: str = "Notability"
    """Vault-relative folder receiving the generated Markdown notes."""

    attachments_subdir: str = "Attachments/Notability"
    """Vault-relative folder receiving the original PDF files."""

    state_file: Path = Path("/data/notes_sync_state.json")
    """Where the module remembers what it already synchronised."""

    min_file_age_seconds: int = Field(default=10, ge=0)
    """Ignore files modified more recently than this (upload possibly in progress)."""

    extract_pdf_text: bool = True
    """Copy the typed text of each PDF into the note so Obsidian can search it."""

    ocr_engine: Literal["none", "kraken"] = "none"
    """Handwriting recognition. 'kraken' needs the image built with the ``ocr`` extra."""

    ocr_model: Path = Path("/data/models/McCATMuS_nfd_nofix_V1.mlmodel")
    """Kraken recognition model (see scripts/fetch-ocr-model.sh)."""

    ocr_dpi: int = Field(default=200, ge=100, le=400)
    """Rendering resolution of the pages. Lower is faster but less accurate."""

    ocr_max_pages: int = Field(default=30, ge=1)
    """Pages recognised per note at most: bounds the time spent on a huge notebook."""

    ocr_threads: int = Field(default=1, ge=1)
    """CPU threads used by the OCR. Keep 1 on a small VM so the API stays responsive."""

    @field_validator("notes_subdir", "attachments_subdir")
    @classmethod
    def _must_stay_inside_vault(cls, value: str) -> str:
        path = PurePosixPath(value)
        if not value.strip() or path.is_absolute() or ".." in path.parts:
            raise ValueError("must be a non-empty relative path without '..'")
        return value
