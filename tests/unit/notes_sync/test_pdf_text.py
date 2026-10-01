import shutil
from pathlib import Path

import pytest

from jouskaio_api.core.errors import ExternalServiceError
from jouskaio_api.modules.notes_sync.adapters.pdf_text import NullTextExtractor, PdftotextExtractor


def build_minimal_pdf(text: str) -> bytes:
    """A one-page PDF with real (selectable) text and a valid xref table."""
    stream = f"BT /F1 18 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    trailer = f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
    out += (trailer + f"startxref\n{xref_at}\n%%EOF\n").encode()
    return bytes(out)


def test_null_extractor_returns_nothing(tmp_path: Path) -> None:
    assert NullTextExtractor().extract(tmp_path / "x.pdf") == ""


@pytest.mark.skipif(shutil.which("pdftotext") is None, reason="pdftotext is not installed")
def test_pdftotext_extracts_typed_text(tmp_path: Path) -> None:
    pdf = tmp_path / "typed.pdf"
    pdf.write_bytes(build_minimal_pdf("Hello Obsidian"))
    executable = shutil.which("pdftotext")
    assert executable is not None

    assert PdftotextExtractor(executable).extract(pdf) == "Hello Obsidian"


@pytest.mark.skipif(shutil.which("pdftotext") is None, reason="pdftotext is not installed")
def test_pdftotext_failure_is_an_external_service_error(tmp_path: Path) -> None:
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"not a pdf at all")
    executable = shutil.which("pdftotext")
    assert executable is not None

    with pytest.raises(ExternalServiceError):
        PdftotextExtractor(executable).extract(broken)
