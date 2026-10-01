"""Composition root of the module: wires adapters into the service."""

import logging
import os
import shutil

from fastapi import APIRouter

from jouskaio_api.core.errors import ConfigurationError
from jouskaio_api.core.jobs import JobRegistry
from jouskaio_api.core.module import HealthStatus, ModuleContext
from jouskaio_api.modules.notes_sync.adapters.converters import PdfConverter, RtfConverter
from jouskaio_api.modules.notes_sync.adapters.handwriting import (
    NullRecognizer,
    build_kraken_recognizer,
    missing_ocr_packages,
)
from jouskaio_api.modules.notes_sync.adapters.inbox import FolderInboxSource
from jouskaio_api.modules.notes_sync.adapters.pdf_text import NullTextExtractor, PdftotextExtractor
from jouskaio_api.modules.notes_sync.adapters.state import JsonSyncStateStore
from jouskaio_api.modules.notes_sync.adapters.vault import ObsidianVault
from jouskaio_api.modules.notes_sync.api import build_router
from jouskaio_api.modules.notes_sync.config import NotesSyncSettings
from jouskaio_api.modules.notes_sync.ports import (
    HandwritingRecognizer,
    NoteConverter,
    TextExtractor,
)
from jouskaio_api.modules.notes_sync.service import NotesSyncService

logger = logging.getLogger(__name__)


class NotesSyncModule:
    def __init__(
        self,
        service: NotesSyncService,
        jobs: JobRegistry,
        settings: NotesSyncSettings,
        ocr: HandwritingRecognizer,
    ) -> None:
        self._service = service
        self._jobs = jobs
        self._settings = settings
        self._ocr = ocr

    @property
    def name(self) -> str:
        return "notes_sync"

    @property
    def description(self) -> str:
        return (
            "One-way synchronisation of Notability exports (PDF, RTF) into an Obsidian vault, "
            "with optional local handwriting OCR."
        )

    def router(self) -> APIRouter:
        return build_router(self._service, self._jobs)

    def healthcheck(self) -> HealthStatus:
        inbox, vault = self._settings.inbox_dir, self._settings.vault_dir
        if not (inbox.is_dir() and os.access(inbox, os.R_OK)):
            return HealthStatus(name=self.name, ok=False, detail=f"inbox not readable: {inbox}")
        if not (vault.is_dir() and os.access(vault, os.W_OK)):
            return HealthStatus(name=self.name, ok=False, detail=f"vault not writable: {vault}")
        ocr = self._ocr.fingerprint
        return HealthStatus(name=self.name, ok=True, detail="" if ocr == "none" else f"ocr={ocr}")


def build_recognizer(cfg: NotesSyncSettings) -> HandwritingRecognizer:
    """OCR is an explicit opt-in: when it cannot work, fail at startup rather than silently."""
    if cfg.ocr_engine == "none":
        return NullRecognizer()
    if missing := missing_ocr_packages():
        raise ConfigurationError(
            f"OCR engine 'kraken' needs the 'ocr' extra (missing: {', '.join(missing)}). "
            "Build the image with WITH_OCR=true, or run `uv sync --extra ocr`."
        )
    if not cfg.ocr_model.is_file():
        raise ConfigurationError(
            f"OCR model not found: {cfg.ocr_model}. Download it with scripts/fetch-ocr-model.sh"
        )
    logger.info("handwriting OCR enabled with kraken (%s)", cfg.ocr_model.name)
    return build_kraken_recognizer(cfg.ocr_model, cfg.ocr_dpi, cfg.ocr_max_pages, cfg.ocr_threads)


def build_module(
    context: ModuleContext, settings: NotesSyncSettings | None = None
) -> NotesSyncModule:
    cfg = settings or NotesSyncSettings()

    extractor: TextExtractor = NullTextExtractor()
    if cfg.extract_pdf_text:
        pdftotext = shutil.which("pdftotext")
        if pdftotext:
            extractor = PdftotextExtractor(pdftotext)
        else:
            logger.warning("pdftotext not found: PDF text extraction disabled")

    recognizer = build_recognizer(cfg)
    converters: list[NoteConverter] = [PdfConverter(extractor, recognizer)]
    pandoc = shutil.which("pandoc")
    if pandoc:
        converters.append(RtfConverter(pandoc))
    else:
        logger.warning("pandoc not found: RTF notes will be reported as unsupported")

    service = NotesSyncService(
        source=FolderInboxSource(cfg.inbox_dir, min_age_seconds=cfg.min_file_age_seconds),
        converters=converters,
        vault=ObsidianVault(cfg.vault_dir, cfg.notes_subdir, cfg.attachments_subdir),
        state=JsonSyncStateStore(cfg.state_file),
    )
    return NotesSyncModule(service, context.jobs, cfg, recognizer)
