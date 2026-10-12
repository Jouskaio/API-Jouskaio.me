"""Settings of the news module (``JOUSKAIO_NEWS_*``).

The default matches the mount point of the Docker image: /data.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class NewsSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="JOUSKAIO_NEWS_", env_file=".env", extra="ignore")

    state_file: Path = Path("/data/news.json")
    """Where the module keeps the current news card."""
