"""
backend/config.py

Loads and validates environment configuration for the Automated Data Analyst
backend. Secrets (PostgreSQL credentials, Gemini API key) live only in the
local .env file and are never exposed to the frontend beyond what a given
endpoint explicitly needs (e.g. connection status, not the raw password).
"""
from __future__ import annotations

from pathlib import Path
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- PostgreSQL ---
    database_host: str = "localhost"
    database_port: int = 5432
    database_user: str = "postgres"
    database_password: str = ""
    database_name: str = ""

    # --- Groq (optional) ---
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"

    # --- Gemini (optional fallback) ---
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    # --- App ---
    app_env: str = "development"
    app_username: str = "analyst"
    app_password: str = ""
    database_query_role: str = ""
    debug: bool = False
    upload_max_mb: int = 500
    allowed_origins: str = "http://localhost:8000,http://127.0.0.1:8000,http://localhost:5500,http://127.0.0.1:5500"
    upload_retention_hours: int = 24

    # --- Paths ---
    upload_dir: Path = BASE_DIR / "data" / "uploads"
    cleaned_dir: Path = BASE_DIR / "data" / "cleaned"
    exports_dir: Path = BASE_DIR / "data" / "exports"
    reports_dir: Path = BASE_DIR / "reports"

    @property
    def cors_origins(self) -> list[str]:
        return [
            o.strip()
            for o in self.allowed_origins.split(",")
            if o.strip() and o.strip().lower() != "null"
        ]

    @property
    def ai_enabled(self) -> bool:
        return bool(self.groq_api_key.strip() or self.gemini_api_key.strip())

    @property
    def ai_model(self) -> str:
        if self.groq_api_key.strip():
            return self.groq_model
        return self.gemini_model

    @property
    def has_database_name(self) -> bool:
        return bool(self.database_name.strip())

    def ensure_directories(self) -> None:
        for path in (self.upload_dir, self.cleaned_dir, self.exports_dir, self.reports_dir):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings
