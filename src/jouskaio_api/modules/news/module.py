"""Composition root of the module: wires the store into the router."""

import datetime as dt
import os

from fastapi import APIRouter

from jouskaio_api.core.module import HealthStatus, ModuleContext
from jouskaio_api.modules.news.api import build_router
from jouskaio_api.modules.news.config import NewsSettings
from jouskaio_api.modules.news.schemas import NewsCard
from jouskaio_api.modules.news.store import JsonNewsStore

DEFAULT_CARD = NewsCard(
    date=dt.date(2023, 8, 1),
    message=(
        "My blog is finally created and you can now check last articles :) "
        "I'm currently working on my first project presentation."
    ),
)
"""Shown until the first update: the card that was hard-coded in the homepage."""


class NewsModule:
    def __init__(self, store: JsonNewsStore, settings: NewsSettings) -> None:
        self._store = store
        self._settings = settings

    @property
    def name(self) -> str:
        return "news"

    @property
    def description(self) -> str:
        return "The news card of the portfolio homepage: one date and one short message."

    def router(self) -> APIRouter:
        return build_router(self._store)

    def healthcheck(self) -> HealthStatus:
        folder = self._settings.state_file.parent
        if folder.is_dir() and not os.access(folder, os.W_OK):
            return HealthStatus(name=self.name, ok=False, detail=f"folder not writable: {folder}")
        return HealthStatus(name=self.name, ok=True)


def build_module(context: ModuleContext, settings: NewsSettings | None = None) -> NewsModule:
    cfg = settings or NewsSettings()
    return NewsModule(JsonNewsStore(cfg.state_file, DEFAULT_CARD), cfg)
