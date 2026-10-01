"""JSON file remembering which notes were synchronised (and their content digest)."""

import threading
from pathlib import Path

from pydantic import BaseModel, ValidationError

from jouskaio_api.core.errors import DomainError
from jouskaio_api.modules.notes_sync.schemas import SyncRecord


class _StateFile(BaseModel):
    version: int = 1
    records: dict[str, SyncRecord] = {}


class JsonSyncStateStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._records = self._load()

    def get(self, key: str) -> SyncRecord | None:
        with self._lock:
            return self._records.get(key)

    def put(self, record: SyncRecord) -> None:
        with self._lock:
            self._records[record.key] = record
            self._save()

    def all(self) -> list[SyncRecord]:
        with self._lock:
            return sorted(self._records.values(), key=lambda r: r.key)

    def _load(self) -> dict[str, SyncRecord]:
        if not self._path.exists():
            return {}
        try:
            return _StateFile.model_validate_json(self._path.read_text("utf-8")).records
        except (OSError, ValidationError) as exc:
            raise DomainError(f"State file {self._path} is unreadable: {exc}") from exc

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_name(self._path.name + ".tmp")
        tmp.write_text(_StateFile(records=self._records).model_dump_json(indent=2), "utf-8")
        tmp.replace(self._path)
