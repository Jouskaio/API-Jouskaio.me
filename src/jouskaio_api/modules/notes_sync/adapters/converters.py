"""Converters turning an exported Notability file into Markdown content."""

import logging
import subprocess

from jouskaio_api.core.errors import ExternalServiceError
from jouskaio_api.modules.notes_sync.adapters.handwriting import NullRecognizer
from jouskaio_api.modules.notes_sync.domain import ConvertedNote, SourceNote
from jouskaio_api.modules.notes_sync.ports import HandwritingRecognizer, TextExtractor

logger = logging.getLogger(__name__)


class RtfConverter:
    """RTF (typed notes) -> GitHub-flavoured Markdown, through pandoc."""

    suffixes = frozenset({".rtf"})
    fingerprint = "rtf"

    def __init__(self, pandoc: str, timeout: float = 30.0) -> None:
        self._pandoc = pandoc
        self._timeout = timeout

    def convert(self, note: SourceNote) -> ConvertedNote:
        try:
            proc = subprocess.run(  # noqa: S603 - executable resolved via shutil.which
                [self._pandoc, "--from=rtf", "--to=gfm", "--wrap=none", str(note.path)],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=self._timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ExternalServiceError(f"pandoc timed out on {note.key}") from exc
        if proc.returncode != 0:
            raise ExternalServiceError(f"pandoc failed on {note.key}: {proc.stderr.strip()[:200]}")
        return ConvertedNote(title=note.stem, body=proc.stdout.strip(), pipeline=self.fingerprint)


class PdfConverter:
    """PDF -> the original file as an attachment, plus its typed text and its handwriting.

    Text and handwriting are enrichments: when they fail the PDF still syncs. A failed OCR
    is recorded as a degraded pipeline, so the next run tries the note again.
    """

    suffixes = frozenset({".pdf"})

    def __init__(
        self,
        extractor: TextExtractor,
        recognizer: HandwritingRecognizer | None = None,
    ) -> None:
        self._extractor = extractor
        self._recognizer = recognizer or NullRecognizer()

    @property
    def fingerprint(self) -> str:
        return self._pipeline(self._recognizer.fingerprint)

    def convert(self, note: SourceNote) -> ConvertedNote:
        try:
            text = self._extractor.extract(note.path)
        except ExternalServiceError as exc:
            logger.warning("text extraction failed for %s: %s", note.key, exc)
            text = ""
        ocr = self._recognizer.fingerprint
        try:
            pages = self._recognizer.recognize(note.path)
        except ExternalServiceError as exc:
            logger.warning("handwriting recognition failed for %s: %s", note.key, exc.__cause__)
            pages, ocr = [], "failed"
        sections = [f"## Text\n\n{text}" if text else "", _handwriting_section(pages)]
        return ConvertedNote(
            title=note.stem,
            body="\n\n".join(section for section in sections if section),
            attachment=note.path,
            pipeline=self._pipeline(ocr),
        )

    @staticmethod
    def _pipeline(ocr: str) -> str:
        return f"pdf;ocr={ocr}"


def _handwriting_section(pages: list[str]) -> str:
    if not any(pages):
        return ""
    if len(pages) == 1:
        content = pages[0]
    else:
        content = "\n\n".join(
            f"### Page {number}\n\n{page}" for number, page in enumerate(pages, 1) if page
        )
    return f"## Handwriting (OCR)\n\n*Automatic transcription, may contain errors.*\n\n{content}"
