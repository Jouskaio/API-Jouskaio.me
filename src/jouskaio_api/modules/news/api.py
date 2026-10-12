"""HTTP layer of the module: thin, no business logic."""

import logging

from fastapi import APIRouter

from jouskaio_api.core.http import error_responses
from jouskaio_api.modules.news.schemas import NewsCard
from jouskaio_api.modules.news.store import JsonNewsStore

logger = logging.getLogger(__name__)


def build_router(store: JsonNewsStore) -> APIRouter:
    router = APIRouter()

    @router.get(
        "",
        response_model=NewsCard,
        summary="Get the news card",
        response_description="The card currently displayed on the homepage.",
    )
    def get_news() -> NewsCard:
        """The current news card. Until the first update, it is the card shipped with the API."""
        return store.get()

    @router.put(
        "",
        response_model=NewsCard,
        summary="Replace the news card",
        response_description="The card, as now stored.",
        responses=error_responses(502, e502="The card could not be saved on disk."),
    )
    def put_news(card: NewsCard) -> NewsCard:
        """Replace the date and the message of the card. The homepage shows the new card the
        next time it is regenerated (a few minutes at most)."""
        logger.info("news card updated date=%s", card.date)  # audit trail
        return store.put(card)

    return router
