import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any


def _read_setting(key: str, default: Any = None) -> Any:
    value = os.getenv(key)
    if value is None:
        if default is None:
            raise KeyError(f"Variável de ambiente obrigatória não definida: {key}")
        return default
    return value


@dataclass(frozen=True)
class AppSettings:
    openai_api_key: str | None
    pinecone_api_key: str | None
    index_name: str | None
    database_url: str
    jwt_secret_key: str
    jwt_algorithm: str
    jwt_access_token_expire_minutes: int
    google_client_id: str

    @classmethod
    def load(cls) -> "AppSettings":
        return cls(
            openai_api_key=_read_setting("OPENAI_API_KEY"),
            pinecone_api_key=_read_setting("PINECONE_API_KEY"),
            index_name=_read_setting("INDEX_NAME"),
            database_url=_read_setting(
                "DATABASE_URL",
                "postgresql+psycopg2://postgres:postgres@db:5432/allercheck",
            ),
            jwt_secret_key=_read_setting("JWT_SECRET_KEY", "change-this-secret-in-production"),
            jwt_algorithm=_read_setting("JWT_ALGORITHM", "HS256"),
            jwt_access_token_expire_minutes=int(
                _read_setting("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", 60)
            ),
            google_client_id=_read_setting("GOOGLE_CLIENT_ID", ""),
        )


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    settings = AppSettings.load()

    if settings.openai_api_key:
        os.environ["OPENAI_API_KEY"] = settings.openai_api_key
    if settings.pinecone_api_key:
        os.environ["PINECONE_API_KEY"] = settings.pinecone_api_key

    return settings
