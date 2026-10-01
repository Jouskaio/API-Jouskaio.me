"""Application-wide settings. Module-specific settings live in each module."""

from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Loaded from ``JOUSKAIO_*`` environment variables (and a local ``.env`` file)."""

    model_config = SettingsConfigDict(env_prefix="JOUSKAIO_", env_file=".env", extra="ignore")

    api_token: SecretStr = Field(min_length=32, description="Bearer token required by the API")
    enabled_modules: Annotated[list[str], NoDecode] = ["notes_sync"]
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    enable_docs: bool = False

    @field_validator("enabled_modules", mode="before")
    @classmethod
    def _split_comma_separated(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value
