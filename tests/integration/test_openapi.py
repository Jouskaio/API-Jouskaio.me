"""The documentation is part of the contract: every case a client can meet is documented."""

from typing import Any

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from jouskaio_api.core.config import Settings
from jouskaio_api.core.module import HealthStatus, ModuleContext
from jouskaio_api.main import create_app
from jouskaio_api.modules.notes_sync import build_module
from jouskaio_api.modules.notes_sync.config import NotesSyncSettings

ERROR_REF = "#/components/schemas/ErrorResponse"
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


@pytest.fixture
def spec(core_settings: Settings, notes_settings: NotesSyncSettings) -> dict[str, Any]:
    def factory(context: ModuleContext) -> object:
        return build_module(context, notes_settings)

    app = create_app(core_settings, {"notes_sync": factory})  # type: ignore[dict-item]
    return app.openapi()


def operations(spec: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    return [
        (method.upper(), path, operation)
        for path, item in spec["paths"].items()
        for method, operation in item.items()
        if method in HTTP_METHODS
    ]


def test_every_operation_has_a_summary_and_a_description(spec: dict[str, Any]) -> None:
    for method, path, operation in operations(spec):
        assert operation.get("summary"), f"{method} {path}"
        assert operation.get("description"), f"{method} {path}"


def test_every_protected_operation_documents_401_and_500(spec: dict[str, Any]) -> None:
    for method, path, operation in operations(spec):
        codes = operation["responses"]
        assert "500" in codes, f"{method} {path}"
        if path != "/api/v1/health":
            assert "401" in codes, f"{method} {path}"
            assert operation.get("security"), f"{method} {path} is not marked as secured"


def test_documented_errors_use_the_shared_error_body(spec: dict[str, Any]) -> None:
    for method, path, operation in operations(spec):
        for code, response in operation["responses"].items():
            if code.startswith(("4", "5")) and code not in {"422", "503"}:
                schema = response["content"]["application/json"]["schema"]
                assert schema["$ref"] == ERROR_REF, f"{method} {path} {code}"


@pytest.mark.parametrize(
    ("method", "path", "codes"),
    [
        ("GET", "/api/v1/health", {"200"}),
        ("GET", "/api/v1/health/modules", {"200", "503"}),
        ("POST", "/api/v1/notes-sync/runs", {"202", "409"}),
        ("GET", "/api/v1/notes-sync/runs", {"200"}),
        ("GET", "/api/v1/notes-sync/runs/{job_id}", {"200", "404"}),
        ("GET", "/api/v1/notes-sync/notes", {"200"}),
    ],
)
def test_each_route_documents_its_specific_cases(
    spec: dict[str, Any], method: str, path: str, codes: set[str]
) -> None:
    documented = set(spec["paths"][path][method.lower()]["responses"])
    assert codes <= documented, documented


def test_enums_document_each_value(spec: dict[str, Any]) -> None:
    schemas = spec["components"]["schemas"]
    for name in ("NoteOutcome", "JobStatus"):
        description = schemas[name]["description"]
        for value in schemas[name]["enum"]:
            assert f"`{value}`" in description, f"{name}.{value} is not documented"


def test_modules_get_a_documented_section(spec: dict[str, Any]) -> None:
    tags = {tag["name"]: tag["description"] for tag in spec["tags"]}
    assert set(tags) == {"health", "notes_sync"}
    assert all(tags.values())


# --- The documented bodies are the ones actually returned -------------------------------


def test_401_uses_the_shared_error_body(core_settings: Settings) -> None:
    settings = core_settings.model_copy(update={"enabled_modules": []})
    client = TestClient(create_app(settings, {}))
    response = client.get("/api/v1/health/modules")
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.json() == {"error": "AuthenticationError", "detail": "Invalid or missing token"}


class CrashingModule:
    name = "crashing"
    description = "Fails on purpose."

    def router(self) -> APIRouter:
        router = APIRouter()

        @router.get("/boom")
        def boom() -> None:
            raise RuntimeError("secret internal detail")

        return router

    def healthcheck(self) -> HealthStatus:
        return HealthStatus(name=self.name, ok=True)


def test_500_uses_the_shared_error_body_and_leaks_nothing(core_settings: Settings) -> None:
    settings = core_settings.model_copy(update={"enabled_modules": ["crashing"]})
    app = create_app(settings, {"crashing": lambda _: CrashingModule()})
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/api/v1/crashing/boom", headers={"Authorization": f"Bearer {'t' * 32}"})

    assert response.status_code == 500
    assert response.json() == {
        "error": "InternalServerError",
        "detail": "Unexpected error, see the server logs",
    }
