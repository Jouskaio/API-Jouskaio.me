"""Handwriting recognition (HTR) of Notability PDFs: local, CPU only, sized for a small VM.

Each page is rendered to an image (pypdfium2). Kraken then finds the text lines on it with
its bundled ``blla`` segmentation model, and reads them with a recognition model that is
downloaded once (McCATMuS by default, see the README).

Frugality choices: one torch thread, no worker process, models loaded on first use and kept
for the following notes, a cap on the number of pages per note.

kraken, torch and pypdfium2 come with the optional ``ocr`` extra. They are imported lazily,
so the application runs, and its tests pass, without them.
"""

import importlib.util
import logging
import threading
import unicodedata
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Protocol

from jouskaio_api.core.errors import ExternalServiceError

logger = logging.getLogger(__name__)

OCR_PACKAGES = ("kraken", "pypdfium2", "torch")

PageImage = Any
"""A PIL image. Typed loosely so this module imports without the ``ocr`` extra."""


def missing_ocr_packages() -> list[str]:
    return [name for name in OCR_PACKAGES if importlib.util.find_spec(name) is None]


class NullRecognizer:
    """Used when OCR is disabled."""

    fingerprint = "none"

    def recognize(self, pdf: Path) -> list[str]:
        return []


class PageRenderer(Protocol):
    def render(self, pdf: Path, max_pages: int) -> Iterator[PageImage]: ...


class LineReader(Protocol):
    def read_lines(self, image: PageImage) -> list[str]: ...


class PdfiumRenderer:
    """Renders PDF pages to grayscale images, one at a time to keep memory flat."""

    def __init__(self, dpi: int) -> None:
        self._scale = dpi / 72  # PDF user space is 72 points per inch

    def render(self, pdf: Path, max_pages: int) -> Iterator[PageImage]:
        import pypdfium2 as pdfium

        document = pdfium.PdfDocument(pdf)
        try:
            total = len(document)
            if total > max_pages:
                logger.warning(
                    "%s has %d pages, OCR limited to the first %d", pdf.name, total, max_pages
                )
            for index in range(min(total, max_pages)):
                page = document[index]
                try:
                    yield page.render(scale=self._scale).to_pil().convert("L")
                finally:
                    page.close()
        finally:
            document.close()


class KrakenLineReader:
    """Segments a page into lines then reads each line. Not re-entrant, hence the lock."""

    def __init__(self, model: Path, threads: int = 1) -> None:
        self._model = model
        self._threads = threads
        self._lock = threading.Lock()
        self._models: tuple[Any, Any] | None = None

    def read_lines(self, image: PageImage) -> list[str]:
        from kraken.configs import RecognitionInferenceConfig, SegmentationInferenceConfig

        with self._lock:
            segmenter, recognizer = self._load()
            segmentation = segmenter.predict(
                image, SegmentationInferenceConfig(num_threads=self._threads)
            )
            if not segmentation.lines:
                return []
            # num_line_workers=0: extract lines in-process instead of forking a pool, which
            # would multiply memory use and breaks when called from a server thread.
            config = RecognitionInferenceConfig(num_threads=self._threads, num_line_workers=0)
            return [
                str(record.prediction) for record in recognizer.predict(image, segmentation, config)
            ]

    def _load(self) -> tuple[Any, Any]:
        if self._models is None:
            import torch
            from kraken.tasks import RecognitionTaskModel, SegmentationTaskModel

            torch.set_num_threads(self._threads)
            logger.info("loading kraken models (recognition: %s)", self._model.name)
            self._models = (
                SegmentationTaskModel.load_model(),  # bundled blla model
                RecognitionTaskModel.load_model(str(self._model)),
            )
        return self._models


def _clean(lines: list[str]) -> str:
    # Models trained on NFD text (such as McCATMuS) output decomposed accents, which
    # Obsidian's search would not match against what you type: normalise to NFC.
    kept = (unicodedata.normalize("NFC", line).strip() for line in lines)
    return "\n".join(line for line in kept if line)


class KrakenRecognizer:
    def __init__(
        self,
        reader: LineReader,
        renderer: PageRenderer,
        max_pages: int,
        fingerprint: str,
    ) -> None:
        self._reader = reader
        self._renderer = renderer
        self._max_pages = max_pages
        self._fingerprint = fingerprint

    @property
    def fingerprint(self) -> str:
        return self._fingerprint

    def recognize(self, pdf: Path) -> list[str]:
        try:
            return [
                _clean(self._reader.read_lines(image))
                for image in self._renderer.render(pdf, self._max_pages)
            ]
        except Exception as exc:  # kraken, torch and pdfium raise unrelated exception types
            raise ExternalServiceError(f"handwriting recognition failed on {pdf.name}") from exc


def build_kraken_recognizer(
    model: Path, dpi: int, max_pages: int, threads: int
) -> KrakenRecognizer:
    return KrakenRecognizer(
        reader=KrakenLineReader(model, threads),
        renderer=PdfiumRenderer(dpi),
        max_pages=max_pages,
        fingerprint=f"kraken:{model.name}",
    )
