from pathlib import Path

import pytest
from pydantic import SecretStr

from jouskaio_api.core.config import Settings
from jouskaio_api.modules.notes_sync.config import NotesSyncSettings


@pytest.fixture
def core_settings() -> Settings:
    return Settings(
        _env_file=None,
        api_token=SecretStr("t" * 32),
        enabled_modules=["notes_sync"],
    )


@pytest.fixture
def dirs(tmp_path: Path) -> dict[str, Path]:
    inbox, vault = tmp_path / "inbox", tmp_path / "vault"
    inbox.mkdir()
    vault.mkdir()
    return {"inbox": inbox, "vault": vault, "state": tmp_path / "state.json"}


@pytest.fixture
def notes_settings(dirs: dict[str, Path]) -> NotesSyncSettings:
    return NotesSyncSettings(
        _env_file=None,
        inbox_dir=dirs["inbox"],
        vault_dir=dirs["vault"],
        state_file=dirs["state"],
        min_file_age_seconds=0,
        extract_pdf_text=False,
    )
