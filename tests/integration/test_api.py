import os
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from jouskaio_api.core.config import Settings
from jouskaio_api.core.errors import ConfigurationError
from jouskaio_api.core.jobs import JobRegistry
from jouskaio_api.core.module import ModuleContext
from jouskaio_api.main import create_app
from jouskaio_api.modules.notes_sync import build_module
from jouskaio_api.modules.notes_sync import module as notes_sync_module
from jouskaio_api.modules.notes_sync.config import NotesSyncSettings

AUTH = {"Authorization": f"Bearer {'t' * 32}"}
LONG_AGO = datetime(2026, 1, 1, tzinfo=UTC).timestamp()


@pytest.fixture
def client(core_settings: Settings, notes_settings: NotesSyncSettings) -> TestClient:
    def factory(context: ModuleContext) -> object:
        return build_module(context, notes_settings)

    app = create_app(core_settings, {"notes_sync": factory})  # type: ignore[dict-item]
    return TestClient(app)


def drop(inbox: Path, key: str, content: bytes) -> None:
    path = inbox / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    os.utime(path, (LONG_AGO, LONG_AGO))


def test_liveness_is_public_but_the_api_requires_a_token(client: TestClient) -> None:
    assert client.get("/api/v1/health").json() == {"status": "ok"}
    assert client.get("/api/v1/health/modules").status_code == 401
    bad = client.get("/api/v1/health/modules", headers={"Authorization": "Bearer wrong"})
    assert bad.status_code == 401
    assert client.get("/api/v1/notes-sync/runs").status_code == 401


def test_every_route_lives_under_api_v1(client: TestClient) -> None:
    paths = client.app.openapi()["paths"]  # type: ignore[attr-defined]
    assert "/api/v1/health" in paths
    assert all(path.startswith("/api/v1/") for path in paths), list(paths)


def test_docs_are_served_under_api_v1_when_enabled(
    core_settings: Settings, notes_settings: NotesSyncSettings
) -> None:
    def factory(context: ModuleContext) -> object:
        return build_module(context, notes_settings)

    settings = core_settings.model_copy(update={"enable_docs": True})
    docs = TestClient(create_app(settings, {"notes_sync": factory}))  # type: ignore[dict-item]

    assert docs.get("/api/v1/docs").status_code == 200
    spec = docs.get("/api/v1/openapi.json").json()
    assert spec["info"]["title"] == "API Jouskaio.me"
    assert "/api/v1/notes-sync/runs" in spec["paths"]
    home = docs.get("/", follow_redirects=False)
    assert home.headers["location"] == "/api/v1/docs"


def test_docs_are_hidden_by_default(client: TestClient) -> None:
    assert client.get("/api/v1/docs").status_code == 404
    assert client.get("/api/v1/openapi.json").status_code == 404
    assert client.get("/").status_code == 404


def test_aggregated_health_reports_each_module(client: TestClient) -> None:
    response = client.get("/api/v1/health/modules", headers=AUTH)
    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "modules": [{"name": "notes_sync", "ok": True, "detail": ""}],
    }


def test_health_is_503_when_the_vault_is_missing(client: TestClient, dirs: dict[str, Path]) -> None:
    shutil.rmtree(dirs["vault"])
    response = client.get("/api/v1/health/modules", headers=AUTH)
    assert response.status_code == 503
    assert response.json()["ok"] is False


def test_full_sync_flow(client: TestClient, dirs: dict[str, Path]) -> None:
    drop(dirs["inbox"], "Maths/Algebra.pdf", b"%PDF-1.4 fake")
    drop(dirs["inbox"], "Raw.note", b"proprietary")

    started = client.post("/api/v1/notes-sync/runs", headers=AUTH)
    assert started.status_code == 202
    run_id = started.json()["id"]

    run = client.get(f"/api/v1/notes-sync/runs/{run_id}", headers=AUTH).json()
    assert run["status"] == "succeeded"
    assert run["report"]["summary"] == {"created": 1, "unsupported": 1}
    assert (dirs["vault"] / "Notability/Maths/Algebra.md").is_file()
    assert (dirs["vault"] / "Attachments/Notability/Maths/Algebra.pdf").is_file()

    notes = client.get("/api/v1/notes-sync/notes", headers=AUTH).json()
    assert [n["key"] for n in notes] == ["Maths/Algebra.pdf"]

    again = client.post("/api/v1/notes-sync/runs", headers=AUTH).json()["id"]
    second = client.get(f"/api/v1/notes-sync/runs/{again}", headers=AUTH).json()
    assert second["report"]["summary"] == {"skipped": 1, "unsupported": 1}


@pytest.mark.skipif(shutil.which("pandoc") is None, reason="pandoc is not installed")
def test_rtf_note_is_converted_to_markdown(client: TestClient, dirs: dict[str, Path]) -> None:
    drop(dirs["inbox"], "Journal.rtf", rb"{\rtf1\ansi Dear \i diary\i0 }")

    run_id = client.post("/api/v1/notes-sync/runs", headers=AUTH).json()["id"]
    client.get(f"/api/v1/notes-sync/runs/{run_id}", headers=AUTH)

    text = (dirs["vault"] / "Notability/Journal.md").read_text("utf-8")
    assert "Dear *diary*" in text


def test_unknown_run_is_404(client: TestClient) -> None:
    response = client.get("/api/v1/notes-sync/runs/unknown", headers=AUTH)
    assert response.status_code == 404
    assert response.json()["error"] == "NotFoundError"


def test_unknown_module_fails_fast(core_settings: Settings) -> None:
    settings = core_settings.model_copy(update={"enabled_modules": ["does_not_exist"]})
    with pytest.raises(ConfigurationError):
        create_app(settings, {})


def test_request_id_is_echoed(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"X-Request-ID": "abc-123"})
    assert response.headers["X-Request-ID"] == "abc-123"
    hostile = client.get("/api/v1/health", headers={"X-Request-ID": "bad id\nwith newline"})
    assert hostile.headers["X-Request-ID"] != "bad id\nwith newline"


def test_ocr_opt_in_fails_fast_when_the_extra_is_missing(
    notes_settings: NotesSyncSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(notes_sync_module, "missing_ocr_packages", lambda: ["kraken"])
    settings = notes_settings.model_copy(update={"ocr_engine": "kraken"})
    with pytest.raises(ConfigurationError, match="ocr' extra"):
        notes_sync_module.build_recognizer(settings)


def test_ocr_opt_in_fails_fast_when_the_model_is_missing(
    notes_settings: NotesSyncSettings, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(notes_sync_module, "missing_ocr_packages", list)
    settings = notes_settings.model_copy(
        update={"ocr_engine": "kraken", "ocr_model": tmp_path / "absent.mlmodel"}
    )
    with pytest.raises(ConfigurationError, match="model not found"):
        notes_sync_module.build_recognizer(settings)


def test_health_reports_the_active_ocr_engine(
    core_settings: Settings,
    notes_settings: NotesSyncSettings,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    model = tmp_path / "model.mlmodel"
    model.write_bytes(b"weights are only loaded on first use")
    monkeypatch.setattr(notes_sync_module, "missing_ocr_packages", list)
    settings = notes_settings.model_copy(update={"ocr_engine": "kraken", "ocr_model": model})

    health = build_module(ModuleContext(core_settings, JobRegistry()), settings).healthcheck()

    assert health.detail == "ocr=kraken:model.mlmodel"
