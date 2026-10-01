"""The contract every module fulfils, plus what the core hands to it."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from fastapi import APIRouter
from pydantic import BaseModel, Field

from jouskaio_api.core.config import Settings
from jouskaio_api.core.jobs import JobRegistry


class HealthStatus(BaseModel, frozen=True):
    """Health of one module."""

    name: str = Field(description="Module name.", examples=["notes_sync"])
    ok: bool = Field(description="False when the module cannot work (e.g. a missing folder).")
    detail: str = Field(
        default="",
        description="Why the module is unhealthy, or extra information when it is healthy.",
        examples=["ocr=kraken:McCATMuS_nfd_nofix_V1.mlmodel"],
    )


class HealthReport(BaseModel):
    """Health of every enabled module."""

    ok: bool = Field(description="True only when every module is healthy.")
    modules: list[HealthStatus]


@dataclass(frozen=True, slots=True)
class ModuleContext:
    """Shared services a module may use. Keep it small."""

    settings: Settings
    jobs: JobRegistry


class Module(Protocol):
    """A self-contained capability mounted under ``/api/v1/<name>``."""

    @property
    def name(self) -> str:
        """snake_case identifier, also used in the URL (kebab-case) and as OpenAPI tag."""
        ...

    @property
    def description(self) -> str:
        """One or two sentences shown on the module's section in the API documentation."""
        ...

    def router(self) -> APIRouter: ...

    def healthcheck(self) -> HealthStatus: ...


ModuleFactory = Callable[[ModuleContext], Module]
