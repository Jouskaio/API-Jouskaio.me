import datetime as dt
from pathlib import Path

import pytest

from jouskaio_api.core.errors import DomainError, ExternalServiceError
from jouskaio_api.modules.news.schemas import NewsCard
from jouskaio_api.modules.news.store import JsonNewsStore

DEFAULT = NewsCard(date=dt.date(2023, 8, 1), message="default")
NEWS = NewsCard(date=dt.date(2026, 10, 11), message="new")


def test_serves_the_default_card_until_the_first_update(tmp_path: Path) -> None:
    store = JsonNewsStore(tmp_path / "news.json", DEFAULT)
    assert store.get() == DEFAULT
    assert not (tmp_path / "news.json").exists()


def test_an_update_is_kept_across_restarts(tmp_path: Path) -> None:
    path = tmp_path / "data" / "news.json"
    JsonNewsStore(path, DEFAULT).put(NEWS)
    assert JsonNewsStore(path, DEFAULT).get() == NEWS


def test_an_unreadable_file_fails_loudly_instead_of_resetting(tmp_path: Path) -> None:
    path = tmp_path / "news.json"
    path.write_text("not json", "utf-8")
    with pytest.raises(DomainError):
        JsonNewsStore(path, DEFAULT)


def test_an_unwritable_location_is_reported_as_an_external_failure(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("", "utf-8")
    store = JsonNewsStore(blocker / "news.json", DEFAULT)
    with pytest.raises(ExternalServiceError):
        store.put(NEWS)
    assert store.get() == NEWS
