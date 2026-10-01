"""Text extraction from PDF files (typed text only; handwriting is ink, not text)."""

import subprocess
from pathlib import Path

from jouskaio_api.core.errors import ExternalServiceError


class NullTextExtractor:
    def extract(self, pdf: Path) -> str:
        return ""


class PdftotextExtractor:
    """Uses poppler's ``pdftotext``."""

    def __init__(self, executable: str, timeout: float = 60.0) -> None:
        self._executable = executable
        self._timeout = timeout

    def extract(self, pdf: Path) -> str:
        try:
            proc = subprocess.run(  # noqa: S603 - executable resolved via shutil.which
                [self._executable, "-enc", "UTF-8", "-nopgbrk", str(pdf), "-"],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=self._timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ExternalServiceError(f"pdftotext timed out on {pdf.name}") from exc
        if proc.returncode != 0:
            raise ExternalServiceError(f"pdftotext failed: {proc.stderr.strip()[:200]}")
        return proc.stdout.strip()
