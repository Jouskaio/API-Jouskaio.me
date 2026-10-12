from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from jouskaio_api.core.config import Settings
from jouskaio_api.core.module import ModuleContext
from jouskaio_api.main import create_app
from jouskaio_api.modules.news import build_module
from jouskaio_api.modules.news.config import NewsSettings
from jouskaio_api.modules.news.module import DEFAULT_CARD

AUTH = {"Authorization": f"Bearer {'t' * 32}"}
URL = "/api/v1/news"


@pytest.fixture
def client(core_settings: Settings, tmp_path: Path) -> TestClient:
    settings = NewsSettings(_env_file=None, state_file=tmp_path / "news.json")

    def factory(context: ModuleContext) -> object:
        return build_module(context, settings)

    news_only = core_settings.model_copy(update={"enabled_modules": ["news"]})
    return TestClient(create_app(news_only, {"news": factory}))  # type: ignore[dict-item]


def test_the_card_requires_a_token(client: TestClient) -> None:
    assert client.get(URL).status_code == 401
    assert client.put(URL, json={"date": "2026-10-11", "message": "x"}).status_code == 401


def test_get_returns_the_default_card_then_the_updated_one(client: TestClient) -> None:
    assert client.get(URL, headers=AUTH).json() == DEFAULT_CARD.model_dump(mode="json")

    new = {"date": "2026-10-11", "message": "  Rebuilding my portfolio.  "}
    response = client.put(URL, json=new, headers=AUTH)

    assert response.status_code == 200
    assert response.json() == {"date": "2026-10-11", "message": "Rebuilding my portfolio."}
    assert client.get(URL, headers=AUTH).json() == response.json()


@pytest.mark.parametrize(
    "body",
    [
        {"date": "11/10/2026", "message": "bad date"},
        {"date": "2026-10-11", "message": "   "},
        {"date": "2026-10-11", "message": "x" * 281},
        {"message": "no date"},
    ],
)
def test_put_rejects_an_invalid_card(client: TestClient, body: dict[str, str]) -> None:
    assert client.put(URL, json=body, headers=AUTH).status_code == 422
    assert client.get(URL, headers=AUTH).json() == DEFAULT_CARD.model_dump(mode="json")


def test_health_reports_the_module(client: TestClient) -> None:
    body = client.get("/api/v1/health/modules", headers=AUTH).json()
    assert body == {"ok": True, "modules": [{"name": "news", "ok": True, "detail": ""}]}
