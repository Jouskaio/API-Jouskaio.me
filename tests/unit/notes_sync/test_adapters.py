import os
import shutil
import unicodedata
from datetime import UTC, datetime
from pathlib import Path

import pytest

from jouskaio_api.core.errors import DomainError, ExternalServiceError
from jouskaio_api.modules.notes_sync.adapters.converters import PdfConverter, RtfConverter
from jouskaio_api.modules.notes_sync.adapters.inbox import FolderInboxSource
from jouskaio_api.modules.notes_sync.adapters.state import JsonSyncStateStore
from jouskaio_api.modules.notes_sync.schemas import SyncRecord
from tests.unit.notes_sync.helpers import make_note

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)


def set_mtime(path: Path, when: datetime) -> None:
    os.utime(path, (when.timestamp(), when.timestamp()))


def test_inbox_yields_visible_regular_files_only(tmp_path: Path) -> None:
    make_note(tmp_path, "Maths/Algebra.pdf", b"1")
    make_note(tmp_path, "Notes.rtf", b"2")
    make_note(tmp_path, ".DS_Store", b"x")
    make_note(tmp_path, ".hidden/secret.pdf", b"x")
    (tmp_path / "link.pdf").symlink_to(tmp_path / "Notes.rtf")
    for path in tmp_path.rglob("*"):
        if path.is_file():
            set_mtime(path, datetime(2026, 1, 1, tzinfo=UTC))

    keys = [n.key for n in FolderInboxSource(tmp_path, 10, lambda: NOW).iter_notes()]

    assert keys == ["Maths/Algebra.pdf", "Notes.rtf"]


def test_inbox_skips_files_that_may_still_be_uploading(tmp_path: Path) -> None:
    fresh = make_note(tmp_path, "fresh.pdf", b"1")
    old = make_note(tmp_path, "old.pdf", b"2")
    set_mtime(fresh.path, NOW)
    set_mtime(old.path, datetime(2026, 9, 30, 11, 0, tzinfo=UTC))

    keys = [n.key for n in FolderInboxSource(tmp_path, 10, lambda: NOW).iter_notes()]

    assert keys == ["old.pdf"]


def test_inbox_normalises_unicode_keys(tmp_path: Path) -> None:
    decomposed = unicodedata.normalize("NFD", "Résumé.pdf")
    make_note(tmp_path, decomposed, b"1")
    set_mtime(tmp_path / decomposed, datetime(2026, 1, 1, tzinfo=UTC))

    (note,) = FolderInboxSource(tmp_path, 0, lambda: NOW).iter_notes()

    assert note.key == unicodedata.normalize("NFC", "Résumé.pdf")


def test_missing_inbox_is_an_external_service_error(tmp_path: Path) -> None:
    with pytest.raises(ExternalServiceError):
        list(FolderInboxSource(tmp_path / "nope").iter_notes())


def test_state_store_round_trips_and_survives_restart(tmp_path: Path) -> None:
    path = tmp_path / "data" / "state.json"
    record = SyncRecord(key="a.pdf", digest="abc", vault_path="Notability/a.md", synced_at=NOW)

    JsonSyncStateStore(path).put(record)

    assert JsonSyncStateStore(path).get("a.pdf") == record
    assert JsonSyncStateStore(path).all() == [record]


def test_corrupted_state_file_fails_fast(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text("{not json", "utf-8")
    with pytest.raises(DomainError):
        JsonSyncStateStore(path)


class FixedExtractor:
    def __init__(self, text: str = "", error: bool = False) -> None:
        self.text, self.error = text, error

    def extract(self, pdf: Path) -> str:
        if self.error:
            raise ExternalServiceError("no poppler")
        return self.text


def test_pdf_converter_attaches_the_pdf_and_adds_extracted_text(tmp_path: Path) -> None:
    note = make_note(tmp_path, "Lecture.pdf", b"x")
    converted = PdfConverter(FixedExtractor("typed words")).convert(note)
    assert converted.attachment == note.path
    assert "typed words" in converted.body


def test_pdf_converter_still_syncs_when_text_extraction_fails(tmp_path: Path) -> None:
    note = make_note(tmp_path, "Lecture.pdf", b"x")
    converted = PdfConverter(FixedExtractor(error=True)).convert(note)
    assert converted.attachment == note.path
    assert converted.body == ""


@pytest.mark.skipif(shutil.which("pandoc") is None, reason="pandoc is not installed")
def test_rtf_converter_produces_markdown(tmp_path: Path) -> None:
    note = make_note(tmp_path, "Notes.rtf", rb"{\rtf1\ansi Hello \b World\b0 !}")
    pandoc = shutil.which("pandoc")
    assert pandoc is not None

    converted = RtfConverter(pandoc).convert(note)

    assert converted.body == "Hello **World**!"
    assert converted.attachment is None


class FixedRecognizer:
    fingerprint = "fake"

    def __init__(self, pages: list[str] | None = None, error: bool = False) -> None:
        self.pages, self.error = pages or [], error

    def recognize(self, pdf: Path) -> list[str]:
        if self.error:
            raise ExternalServiceError("ocr down") from RuntimeError("torch")
        return self.pages


def test_pdf_converter_adds_handwriting_and_records_the_ocr_pipeline(tmp_path: Path) -> None:
    note = make_note(tmp_path, "Lecture.pdf", b"x")
    converter = PdfConverter(FixedExtractor("typed"), FixedRecognizer(["handwritten café notes"]))

    converted = converter.convert(note)

    assert converted.body.startswith("## Text\n\ntyped\n\n## Handwriting (OCR)")
    assert converted.body.endswith("handwritten café notes")
    assert "### Page" not in converted.body
    assert converted.pipeline == converter.fingerprint == "pdf;ocr=fake"


def test_pdf_converter_titles_pages_of_multi_page_notes(tmp_path: Path) -> None:
    note = make_note(tmp_path, "Lecture.pdf", b"x")
    converted = PdfConverter(FixedExtractor(), FixedRecognizer(["one", "", "three"])).convert(note)
    assert "### Page 1\n\none\n\n### Page 3\n\nthree" in converted.body
    assert "Page 2" not in converted.body


def test_pdf_converter_without_handwriting_adds_no_ocr_section(tmp_path: Path) -> None:
    note = make_note(tmp_path, "Lecture.pdf", b"x")
    converted = PdfConverter(FixedExtractor(), FixedRecognizer(["", ""])).convert(note)
    assert converted.body == ""


def test_failed_ocr_still_syncs_but_records_a_degraded_pipeline(tmp_path: Path) -> None:
    note = make_note(tmp_path, "Lecture.pdf", b"x")
    converter = PdfConverter(FixedExtractor("typed"), FixedRecognizer(error=True))

    converted = converter.convert(note)

    assert converted.attachment == note.path
    assert converted.body == "## Text\n\ntyped"
    assert converted.pipeline == "pdf;ocr=failed" != converter.fingerprint
