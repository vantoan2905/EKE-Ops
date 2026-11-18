"""Application settings loaded from environment variables or .env."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://eke_ops:eke_ops@localhost:5432/eke_ops"
    enable_demo_auth: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
