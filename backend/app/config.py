from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Agent Forge"
    environment: str = "development"
    database_url: str = "sqlite:///./agent_forge.db"
    langgraph_checkpoint_url: str | None = None
    secret_key: str = "development-only-change-me"
    session_ttl_minutes: int = 60 * 24
    frontend_origin: str = "http://localhost:5173"
    allow_registration: bool = True
    secure_cookies: bool = False
    containerized: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_prefix="AF_", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
