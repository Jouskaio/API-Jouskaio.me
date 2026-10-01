"""Application factory.

Run with: ``uvicorn jouskaio_api.main:create_app --factory``
"""

import logging
from collections.abc import Mapping
from typing import Literal

from fastapi import APIRouter, Depends, FastAPI, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from jouskaio_api import APP_NAME, __version__
from jouskaio_api.core.config import Settings
from jouskaio_api.core.errors import ConfigurationError
from jouskaio_api.core.http import error_responses, register_http_layer
from jouskaio_api.core.jobs import JobRegistry
from jouskaio_api.core.logging_setup import configure_logging
from jouskaio_api.core.module import (
    HealthReport,
    HealthStatus,
    Module,
    ModuleContext,
    ModuleFactory,
)
from jouskaio_api.core.security import make_bearer_dependency
from jouskaio_api.modules import MODULE_FACTORIES

logger = logging.getLogger(__name__)

API_PREFIX = "/api/v1"
"""Every route lives under this prefix, documentation included. A breaking change of the
contract goes to /api/v2, served side by side until clients have moved."""

API_DESCRIPTION = """
One modular REST API for my apps, services and personal infrastructure. Each capability is
a **module** mounted under `/api/v1/<module>` and enabled by configuration.

**Authentication.** Every route except `GET /api/v1/health` requires the header
`Authorization: Bearer <token>` (the value of `JOUSKAIO_API_TOKEN`). Click *Authorize* to
set it once; it is kept across page reloads.

**Errors.** Every error has the same body, `{"error": "<Type>", "detail": "<message>"}`:
`400` invalid request, `401` missing or wrong token, `404` unknown resource, `409` conflict
with the current state, `422` malformed request (FastAPI validation format), `500`
unexpected error, `502` a dependency failed, `503` a module is unhealthy.

**Long actions.** They answer `202 Accepted` with a resource to poll until its `status` is
`succeeded` or `failed`.

**Tracing.** Every response carries an `X-Request-ID` header (yours if you send a valid
one, a generated one otherwise). It is also written in every log line of the request.
"""


class Liveness(BaseModel):
    status: Literal["ok"] = "ok"


def _load_modules(context: ModuleContext, factories: Mapping[str, ModuleFactory]) -> list[Module]:
    unknown = [name for name in context.settings.enabled_modules if name not in factories]
    if unknown:
        raise ConfigurationError(
            f"Unknown module(s): {', '.join(unknown)}. Available: {', '.join(sorted(factories))}"
        )
    return [factories[name](context) for name in context.settings.enabled_modules]


def _check(module: Module) -> HealthStatus:
    try:
        return module.healthcheck()
    except Exception:
        logger.exception("healthcheck of module %s crashed", module.name)
        return HealthStatus(name=module.name, ok=False, detail="healthcheck crashed")


def create_app(
    settings: Settings | None = None,
    factories: Mapping[str, ModuleFactory] | None = None,
) -> FastAPI:
    settings = settings or Settings()
    configure_logging(settings.log_level)

    context = ModuleContext(settings=settings, jobs=JobRegistry())
    modules = _load_modules(context, MODULE_FACTORIES if factories is None else factories)

    app = FastAPI(
        title=APP_NAME,
        version=__version__,
        description=API_DESCRIPTION,
        openapi_tags=[
            {"name": "health", "description": "Liveness of the API and health of its modules."},
            *({"name": m.name, "description": m.description} for m in modules),
        ],
        docs_url=f"{API_PREFIX}/docs" if settings.enable_docs else None,
        openapi_url=f"{API_PREFIX}/openapi.json" if settings.enable_docs else None,
        redoc_url=None,
        # Keep the token entered in "Authorize" across page reloads (handy with --reload).
        swagger_ui_parameters={"persistAuthorization": True},
    )
    register_http_layer(app)

    public = APIRouter(prefix=API_PREFIX, tags=["health"], responses=error_responses(500))

    @public.get(
        "/health",
        response_model=Liveness,
        summary="Liveness probe",
        response_description="The process is up.",
    )
    def liveness() -> Liveness:
        """Public, no token needed: answers as long as the process runs. Used by the Docker
        healthcheck. It does not check the modules: see `GET /health/modules`."""
        return Liveness()

    api = APIRouter(
        prefix=API_PREFIX,
        dependencies=[Depends(make_bearer_dependency(settings.api_token))],
        responses=error_responses(401, 500),
    )

    @api.get(
        "/health/modules",
        tags=["health"],
        response_model=HealthReport,
        summary="Health of every module",
        response_description="Every module is healthy.",
        responses={
            503: {"model": HealthReport, "description": "At least one module is unhealthy."}
        },
    )
    def modules_health(response: Response) -> HealthReport:
        """Checks each enabled module (folders reachable, OCR engine...). Answers `503` with
        the same body when any module is unhealthy, so a monitoring probe can use it."""
        statuses = [_check(module) for module in modules]
        report = HealthReport(ok=all(s.ok for s in statuses), modules=statuses)
        if not report.ok:
            response.status_code = 503
        return report

    for module in modules:
        api.include_router(
            module.router(),
            prefix=f"/{module.name.replace('_', '-')}",
            tags=[module.name],
        )
    app.include_router(public)
    app.include_router(api)

    if settings.enable_docs:

        @app.get("/", include_in_schema=False)
        def home() -> RedirectResponse:
            return RedirectResponse(f"{API_PREFIX}/docs")

    logger.info("%s started with modules: %s", APP_NAME, [m.name for m in modules])
    return app
