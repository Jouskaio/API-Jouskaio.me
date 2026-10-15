import pytest
from fastapi.testclient import TestClient

from jouskaio_api.core.config import Settings
from jouskaio_api.main import create_app


def test_swagger_does_not_keep_the_token_by_default(core_settings: Settings) -> None:
    assert core_settings.docs_persist_authorization is False


@pytest.mark.parametrize("persist", [False, True])
def test_swagger_keeps_the_token_only_when_asked(core_settings: Settings, persist: bool) -> None:
    settings = core_settings.model_copy(
        update={
            "enable_docs": True,
            "enabled_modules": [],
            "docs_persist_authorization": persist,
        }
    )

    page = TestClient(create_app(settings, {})).get("/api/v1/docs")

    assert page.status_code == 200
    assert f'"persistAuthorization": {str(persist).lower()}' in page.text
