from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables and .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Personalized Holiday Management Agent"
    app_env: str = "dev"

    llm_model: str = "llama3.2:3b"
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = "ollama"
    llm_temperature: float = Field(default=0.2, ge=0.0, le=2.0)

    max_round_messages: int = Field(default=10, ge=4, le=40)
    request_timeout_seconds: float = Field(default=20.0, ge=2.0, le=120.0)

    user_agent: str = "holiday-agent/1.0 (local dev)"


@lru_cache
def get_settings() -> Settings:
    """Cache settings so all modules share the same configuration."""

    return Settings()
