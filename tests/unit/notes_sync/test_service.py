from collections.abc import Iterator
from pathlib import Path

from jouskaio_api.core.errors import ConflictError
from jouskaio_api.modules.notes_sync.domain import ConvertedNote, SourceNote, VaultWrite
from jouskaio_api.modules.notes_sync.schemas import NoteOutcome, SyncRecord
from jouskaio_api.modules.notes_sync.service import NotesSyncService
from tests.unit.notes_sync.helpers import make_note


class FakeSource:
    def __init__(self, notes: list[SourceNote]) -> None:
        self.notes = notes

    def iter_notes(self) -> Iterator[SourceNote]:
        return iter(self.notes)


class FakeConverter:
    suffixes = frozenset({".pdf"})

    def __init__(self, explode_on: str | None = None, degraded: bool = False) -> None:
        self.explode_on = explode_on
        self.fingerprint = "fake/1"
        self.degraded = degraded
        self.calls = 0

    def convert(self, note: SourceNote) -> ConvertedNote:
        self.calls += 1
        if note.key == self.explode_on:
            raise RuntimeError("boom")
        pipeline = "fake/degraded" if self.degraded else self.fingerprint
        return ConvertedNote(title=note.stem, body="body", pipeline=pipeline)


class FakeVault:
    def __init__(self, conflicts: frozenset[str] = frozenset()) -> None:
        self.present: set[str] = set()
        self.conflicts = conflicts

    def exists(self, vault_path: str) -> bool:
        return vault_path in self.present

    def publish(self, note: SourceNote, converted: ConvertedNote) -> VaultWrite:
        if note.key in self.conflicts:
            raise ConflictError("already exists")
        path = f"{note.key}.md"
        created = path not in self.present
        self.present.add(path)
        return VaultWrite(path=path, created=created)


class FakeState:
    def __init__(self) -> None:
        self.records: dict[str, SyncRecord] = {}

    def get(self, key: str) -> SyncRecord | None:
        return self.records.get(key)

    def put(self, record: SyncRecord) -> None:
        self.records[record.key] = record

    def all(self) -> list[SyncRecord]:
        return list(self.records.values())


def outcomes(service: NotesSyncService) -> dict[str, NoteOutcome]:
    return {r.key: r.outcome for r in service.run().results}


def test_first_run_creates_then_second_run_skips(tmp_path: Path) -> None:
    note = make_note(tmp_path, "Maths/Algebra.pdf", b"v1")
    service = NotesSyncService(FakeSource([note]), [FakeConverter()], FakeVault(), FakeState())

    assert outcomes(service) == {"Maths/Algebra.pdf": NoteOutcome.CREATED}
    assert outcomes(service) == {"Maths/Algebra.pdf": NoteOutcome.SKIPPED}


def test_changed_content_updates_the_note(tmp_path: Path) -> None:
    note = make_note(tmp_path, "Maths/Algebra.pdf", b"v1")
    service = NotesSyncService(FakeSource([note]), [FakeConverter()], FakeVault(), FakeState())
    service.run()

    note.path.write_bytes(b"v2")
    assert outcomes(service) == {"Maths/Algebra.pdf": NoteOutcome.UPDATED}


def test_note_deleted_from_the_vault_is_published_again(tmp_path: Path) -> None:
    note = make_note(tmp_path, "Algebra.pdf", b"v1")
    vault = FakeVault()
    service = NotesSyncService(FakeSource([note]), [FakeConverter()], vault, FakeState())
    service.run()

    vault.present.clear()
    assert outcomes(service) == {"Algebra.pdf": NoteOutcome.CREATED}


def test_unsupported_format_is_reported_not_raised(tmp_path: Path) -> None:
    note = make_note(tmp_path, "Raw.note", b"zip")
    service = NotesSyncService(FakeSource([note]), [FakeConverter()], FakeVault(), FakeState())
    assert outcomes(service) == {"Raw.note": NoteOutcome.UNSUPPORTED}


def test_one_bad_note_never_stops_the_others(tmp_path: Path) -> None:
    notes = [
        make_note(tmp_path, "a.pdf", b"1"),
        make_note(tmp_path, "b.pdf", b"2"),
        make_note(tmp_path, "c.pdf", b"3"),
    ]
    service = NotesSyncService(
        FakeSource(notes),
        [FakeConverter(explode_on="b.pdf")],
        FakeVault(conflicts=frozenset({"c.pdf"})),
        FakeState(),
    )
    assert outcomes(service) == {
        "a.pdf": NoteOutcome.CREATED,
        "b.pdf": NoteOutcome.FAILED,
        "c.pdf": NoteOutcome.CONFLICT,
    }


def test_report_summary_counts_outcomes(tmp_path: Path) -> None:
    notes = [make_note(tmp_path, "a.pdf", b"1"), make_note(tmp_path, "x.note", b"2")]
    service = NotesSyncService(FakeSource(notes), [FakeConverter()], FakeVault(), FakeState())
    assert service.run().summary == {"created": 1, "unsupported": 1}


def test_a_new_pipeline_reprocesses_unchanged_notes_once(tmp_path: Path) -> None:
    """E.g. OCR enabled after the notes were first synchronised."""
    note = make_note(tmp_path, "Algebra.pdf", b"v1")
    converter = FakeConverter()
    service = NotesSyncService(FakeSource([note]), [converter], FakeVault(), FakeState())
    service.run()

    converter.fingerprint = "fake/2"
    assert outcomes(service) == {"Algebra.pdf": NoteOutcome.UPDATED}
    assert outcomes(service) == {"Algebra.pdf": NoteOutcome.SKIPPED}


def test_a_degraded_conversion_is_retried_on_the_next_run(tmp_path: Path) -> None:
    note = make_note(tmp_path, "Algebra.pdf", b"v1")
    converter = FakeConverter(degraded=True)
    state = FakeState()
    service = NotesSyncService(FakeSource([note]), [converter], FakeVault(), state)
    service.run()
    assert state.records["Algebra.pdf"].pipeline == "fake/degraded"

    converter.degraded = False
    assert outcomes(service) == {"Algebra.pdf": NoteOutcome.UPDATED}
    assert outcomes(service) == {"Algebra.pdf": NoteOutcome.SKIPPED}
    assert converter.calls == 2
