"""JSON file holding the current news card."""

import threading
from pathlib import Path

from pydantic import ValidationError

from jouskaio_api.core.errors import DomainError, ExternalServiceError
from jouskaio_api.modules.news.schemas import NewsCard


class JsonNewsStore:
    def __init__(self, path: Path, default: NewsCard) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._card = self._load(default)

    def get(self) -> NewsCard:
        with self._lock:
            return self._card

    def put(self, card: NewsCard) -> NewsCard:
        with self._lock:
            self._card = card
            self._save()
            return card

    def _load(self, default: NewsCard) -> NewsCard:
        if not self._path.exists():
            return default
        try:
            return NewsCard.model_validate_json(self._path.read_text("utf-8"))
        except (OSError, ValidationError) as exc:
            raise DomainError(f"News file {self._path} is unreadable: {exc}") from exc

    def _save(self) -> None:
        tmp = self._path.with_name(self._path.name + ".tmp")
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(self._card.model_dump_json(indent=2), "utf-8")
            tmp.replace(self._path)
        except OSError as exc:
            raise ExternalServiceError(f"News file {self._path} is not writable: {exc}") from exc
