"""API and persistence models of the news module."""

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field


class NewsCard(BaseModel):
    """The news card displayed on the portfolio homepage."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        json_schema_extra={
            "examples": [
                {"date": "2026-10-11", "message": "Rebuilding my portfolio, step by step."}
            ]
        },
    )

    date: dt.date = Field(description="Day the news was written.", examples=["2026-10-11"])
    message: str = Field(
        min_length=1,
        max_length=280,
        description="Text of the card, without surrounding quotation marks.",
        examples=["Rebuilding my portfolio, step by step."],
    )
