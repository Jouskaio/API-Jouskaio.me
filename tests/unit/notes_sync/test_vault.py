from datetime import UTC, datetime
from pathlib import Path

import pytest

from jouskaio_api.core.errors import ConflictError
from jouskaio_api.modules.notes_sync.adapters.vault import BEGIN, END, ObsidianVault
from jouskaio_api.modules.notes_sync.domain import ConvertedNote
from tests.unit.notes_sync.helpers import make_note


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def vault(tmp_path: Path, clock: Clock) -> ObsidianVault:
    root = tmp_path / "vault"
    root.mkdir()
    return ObsidianVault(root, "Notability", "Attachments/Notability", clock)


def test_creates_note_and_embeds_the_copied_pdf(tmp_path: Path, vault: ObsidianVault) -> None:
    source = make_note(tmp_path / "inbox", "Maths/Algebra.pdf", b"%PDF-fake")
    written = vault.publish(
        source, ConvertedNote(title="Algebra", body="## Text\n\nhello", attachment=source.path)
    )

    assert written.created
    assert written.path == "Notability/Maths/Algebra.md"
    text = (tmp_path / "vault" / written.path).read_text("utf-8")
    assert 'notability_source: "Maths/Algebra.pdf"' in text
    assert "![[Attachments/Notability/Maths/Algebra.pdf]]" in text
    assert "hello" in text
    copied = tmp_path / "vault" / "Attachments/Notability/Maths/Algebra.pdf"
    assert copied.read_bytes() == b"%PDF-fake"


def test_update_replaces_only_the_managed_block(tmp_path: Path, vault: ObsidianVault) -> None:
    source = make_note(tmp_path / "inbox", "Lecture.rtf", b"x")
    first = vault.publish(source, ConvertedNote(title="Lecture", body="old body"))
    note_file = tmp_path / "vault" / first.path
    note_file.write_text(
        note_file.read_text("utf-8").replace(BEGIN, "MY INTRO\n\n" + BEGIN) + "\nMY OWN THOUGHTS\n",
        "utf-8",
    )

    second = vault.publish(source, ConvertedNote(title="Lecture", body="new body"))

    text = note_file.read_text("utf-8")
    assert not second.created
    assert "new body" in text
    assert "old body" not in text
    assert "MY INTRO" in text
    assert "MY OWN THOUGHTS" in text


def test_update_refreshes_the_sync_timestamp(
    tmp_path: Path, vault: ObsidianVault, clock: Clock
) -> None:
    source = make_note(tmp_path / "inbox", "Lecture.rtf", b"x")
    path = vault.publish(source, ConvertedNote(title="Lecture", body="a")).path
    clock.now = datetime(2026, 10, 1, 8, 30, tzinfo=UTC)
    vault.publish(source, ConvertedNote(title="Lecture", body="b"))

    text = (tmp_path / "vault" / path).read_text("utf-8")
    assert "notability_synced_at: 2026-10-01T08:30:00+00:00" in text
    assert "2026-09-30" not in text


def test_existing_unmanaged_note_is_a_conflict_and_left_untouched(
    tmp_path: Path, vault: ObsidianVault
) -> None:
    mine = tmp_path / "vault" / "Notability" / "Lecture.md"
    mine.parent.mkdir(parents=True)
    mine.write_text("my own note", "utf-8")
    source = make_note(tmp_path / "inbox", "Lecture.rtf", b"x")

    with pytest.raises(ConflictError):
        vault.publish(source, ConvertedNote(title="Lecture", body="b"))
    assert mine.read_text("utf-8") == "my own note"


def test_note_managed_by_another_source_is_a_conflict(tmp_path: Path, vault: ObsidianVault) -> None:
    pdf = make_note(tmp_path / "inbox", "Lecture.pdf", b"x")
    rtf = make_note(tmp_path / "inbox", "Lecture.rtf", b"y")
    vault.publish(pdf, ConvertedNote(title="Lecture", body="from pdf"))

    with pytest.raises(ConflictError):
        vault.publish(rtf, ConvertedNote(title="Lecture", body="from rtf"))


def test_deleted_markers_prevent_overwriting(tmp_path: Path, vault: ObsidianVault) -> None:
    source = make_note(tmp_path / "inbox", "Lecture.rtf", b"x")
    path = tmp_path / "vault" / vault.publish(source, ConvertedNote(title="c", body="a")).path
    path.write_text(path.read_text("utf-8").replace(END, ""), "utf-8")

    with pytest.raises(ConflictError):
        vault.publish(source, ConvertedNote(title="c", body="b"))


def test_hostile_names_stay_inside_the_vault(tmp_path: Path, vault: ObsidianVault) -> None:
    source = make_note(tmp_path / "inbox", "a/b.pdf", b"x")
    hostile = type(source)(
        key="../../etc/pa:ss#w[d]?.pdf", path=source.path, modified_at=source.modified_at
    )

    written = vault.publish(hostile, ConvertedNote(title="t", body="b", attachment=source.path))

    root = (tmp_path / "vault").resolve()
    produced = [p for p in root.rglob("*") if p.is_file()]
    assert produced
    assert all(p.resolve().is_relative_to(root) for p in produced)
    assert not any(ch in written.path for ch in "#[]?:")
    assert not (tmp_path / "etc").exists()


def test_exists_reflects_the_filesystem(tmp_path: Path, vault: ObsidianVault) -> None:
    source = make_note(tmp_path / "inbox", "Lecture.rtf", b"x")
    path = vault.publish(source, ConvertedNote(title="c", body="a")).path
    assert vault.exists(path)
    (tmp_path / "vault" / path).unlink()
    assert not vault.exists(path)
