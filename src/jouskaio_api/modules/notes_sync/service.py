"""The synchronisation use case. Depends on ports only."""

import logging
from collections.abc import Callable, Iterable
from datetime import UTC, datetime

from jouskaio_api.core.errors import ConflictError, DomainError
from jouskaio_api.modules.notes_sync.domain import SourceNote
from jouskaio_api.modules.notes_sync.ports import (
    NoteConverter,
    NoteSource,
    SyncStateStore,
    VaultWriter,
)
from jouskaio_api.modules.notes_sync.schemas import (
    NoteOutcome,
    NoteResult,
    SyncRecord,
    SyncReport,
)

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class NotesSyncService:
    def __init__(
        self,
        source: NoteSource,
        converters: Iterable[NoteConverter],
        vault: VaultWriter,
        state: SyncStateStore,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._source = source
        self._converters = {suffix: c for c in converters for suffix in c.suffixes}
        self._vault = vault
        self._state = state
        self._clock = clock

    def run(self) -> SyncReport:
        """Synchronise every note. One failing note never stops the others."""
        started_at = self._clock()
        results = [self._sync_one(note) for note in self._source.iter_notes()]
        report = SyncReport.build(started_at, self._clock(), results)
        logger.info("notes sync finished: %s", report.summary)
        return report

    def list_synced(self) -> list[SyncRecord]:
        return self._state.all()

    def _sync_one(self, note: SourceNote) -> NoteResult:
        converter = self._converters.get(note.suffix)
        if converter is None:
            return NoteResult(
                key=note.key,
                outcome=NoteOutcome.UNSUPPORTED,
                detail=f"No converter for '{note.suffix}' (use PDF or RTF in Notability's backup)",
            )
        try:
            digest = note.digest()
            record = self._state.get(note.key)
            if (
                record
                and record.digest == digest
                and record.pipeline == converter.fingerprint
                and self._vault.exists(record.vault_path)
            ):
                return NoteResult(key=note.key, outcome=NoteOutcome.SKIPPED)

            converted = converter.convert(note)
            written = self._vault.publish(note, converted)
            self._state.put(
                SyncRecord(
                    key=note.key,
                    digest=digest,
                    vault_path=written.path,
                    synced_at=self._clock(),
                    pipeline=converted.pipeline,
                )
            )
        except ConflictError as exc:
            return NoteResult(key=note.key, outcome=NoteOutcome.CONFLICT, detail=str(exc))
        except DomainError as exc:
            return NoteResult(key=note.key, outcome=NoteOutcome.FAILED, detail=str(exc))
        except Exception:
            logger.exception("unexpected error while syncing %s", note.key)
            return NoteResult(
                key=note.key, outcome=NoteOutcome.FAILED, detail="Unexpected error, see logs"
            )
        outcome = NoteOutcome.CREATED if written.created else NoteOutcome.UPDATED
        return NoteResult(key=note.key, outcome=outcome, detail=written.path)
