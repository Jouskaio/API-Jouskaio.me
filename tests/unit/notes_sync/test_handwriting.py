import os
import unicodedata
from collections.abc import Iterator
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import pytest

from jouskaio_api.core.errors import ExternalServiceError
from jouskaio_api.modules.notes_sync.adapters.handwriting import (
    KrakenRecognizer,
    NullRecognizer,
    PdfiumRenderer,
    build_kraken_recognizer,
    missing_ocr_packages,
)
from tests.unit.notes_sync.test_pdf_text import build_minimal_pdf


class FakeRenderer:
    def __init__(self, pages: int) -> None:
        self.pages = pages
        self.max_pages_seen: int | None = None

    def render(self, pdf: Path, max_pages: int) -> Iterator[Any]:
        self.max_pages_seen = max_pages
        yield from range(min(self.pages, max_pages))


class FakeReader:
    def __init__(self, lines_per_page: dict[int, list[str]], explode: bool = False) -> None:
        self.lines_per_page = lines_per_page
        self.explode = explode

    def read_lines(self, image: Any) -> list[str]:
        if self.explode:
            raise RuntimeError("torch exploded")
        return self.lines_per_page.get(image, [])


def recognizer(reader: FakeReader, renderer: FakeRenderer, max_pages: int = 30) -> KrakenRecognizer:
    return KrakenRecognizer(reader, renderer, max_pages=max_pages, fingerprint="kraken:test")


def test_null_recognizer_reads_nothing(tmp_path: Path) -> None:
    assert NullRecognizer().recognize(tmp_path / "x.pdf") == []
    assert NullRecognizer().fingerprint == "none"


def test_recognizer_returns_one_text_per_page_in_order(tmp_path: Path) -> None:
    reader = FakeReader({0: ["Café meeting on Monday", "  ", "review"], 2: ["page three"]})

    pages = recognizer(reader, FakeRenderer(pages=3)).recognize(tmp_path / "n.pdf")

    assert pages == ["Café meeting on Monday\nreview", "", "page three"]


def test_recognizer_normalises_decomposed_accents(tmp_path: Path) -> None:
    decomposed = unicodedata.normalize("NFD", "naïve café")
    (page,) = recognizer(FakeReader({0: [decomposed]}), FakeRenderer(1)).recognize(tmp_path / "n")
    assert page == unicodedata.normalize("NFC", "naïve café")


def test_recognizer_caps_the_number_of_pages(tmp_path: Path) -> None:
    renderer = FakeRenderer(pages=50)
    pages = recognizer(FakeReader({}), renderer, max_pages=2).recognize(tmp_path / "n.pdf")
    assert renderer.max_pages_seen == 2
    assert len(pages) == 2


def test_any_engine_failure_becomes_an_external_service_error(tmp_path: Path) -> None:
    with pytest.raises(ExternalServiceError) as caught:
        recognizer(FakeReader({}, explode=True), FakeRenderer(1)).recognize(tmp_path / "n.pdf")
    assert isinstance(caught.value.__cause__, RuntimeError)


def test_pdfium_renders_grayscale_pages_at_the_requested_dpi(tmp_path: Path) -> None:
    pdf = tmp_path / "note.pdf"
    pdf.write_bytes(build_minimal_pdf("Hello"))

    (image,) = PdfiumRenderer(dpi=100).render(pdf, max_pages=5)

    assert image.mode == "L"
    assert image.size == (850, 1100)  # US Letter, 8.5 x 11 in at 100 dpi


def test_unreadable_pdf_is_an_external_service_error(tmp_path: Path) -> None:
    pdf = tmp_path / "broken.pdf"
    pdf.write_bytes(b"not a pdf")
    engine = KrakenRecognizer(FakeReader({}), PdfiumRenderer(100), 5, "kraken:test")

    with pytest.raises(ExternalServiceError):
        engine.recognize(pdf)


# --- Real engine: runs only where the `ocr` extra and a model are available -------------

MODEL = Path(os.environ.get("JOUSKAIO_TEST_OCR_MODEL", "data/models/McCATMuS_nfd_nofix_V1.mlmodel"))


@pytest.mark.slow
@pytest.mark.skipif(
    bool(missing_ocr_packages()) or not MODEL.is_file(),
    reason="needs the `ocr` extra and a Kraken model (scripts/fetch-ocr-model.sh)",
)
def test_kraken_reads_a_rendered_page(tmp_path: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    expected = ["Remember to review chapter three", "Meeting on Monday with the team"]
    page = Image.new("L", (1654, 2339), 255)  # A4 at 200 dpi: the segmenter expects a page
    draw = ImageDraw.Draw(page)
    for index, line in enumerate(expected):
        draw.text((150, 250 + index * 120), line, fill=0, font=ImageFont.load_default(48))
    pdf = tmp_path / "note.pdf"
    page.save(pdf, resolution=200)

    (text,) = build_kraken_recognizer(MODEL, dpi=200, max_pages=5, threads=1).recognize(pdf)

    assert SequenceMatcher(None, text, "\n".join(expected)).ratio() > 0.8, text
