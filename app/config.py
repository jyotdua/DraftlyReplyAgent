from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Draftly"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_base_url: str = "http://localhost:8000"

    database_url: str = "sqlite:///./data/draftly.db"
    encryption_key: str | None = None

    google_oauth_client_path: str = "./google-oauth-client.json"
    google_redirect_uri: str = "http://localhost:8000/api/auth/google/callback"
    google_gemini_api_key: str | None = Field(default=None, min_length=10)
    gmail_query: str = "is:unread category:primary"
    recent_sent_style_sample_count: int = 5
    gmail_fetch_limit: int = 10

    gmail_scopes: tuple[str, ...] = (
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/userinfo.email",
        "openid",
    )

    @property
    def resolved_oauth_client_path(self) -> Path:
        return Path(self.google_oauth_client_path).expanduser().resolve()

    @property
    def resolved_db_path(self) -> str:
        return self.database_url.replace("sqlite:///", "")

    @property
    def resolved_encryption_key(self) -> bytes:
        if self.encryption_key:
            return self.encryption_key.encode("utf-8")
        key_path = Path("./data/.draftly.key").resolve()
        if key_path.exists():
            return key_path.read_text(encoding="utf-8").strip().encode("utf-8")
        key = Fernet.generate_key()
        key_path.parent.mkdir(parents=True, exist_ok=True)
        key_path.write_text(key.decode("utf-8"), encoding="utf-8")
        return key


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    db_path = settings.resolved_db_path
    if db_path.startswith(".") or db_path.startswith("/"):
        Path(db_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    return settings
