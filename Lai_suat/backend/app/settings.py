from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    DB_PATH: str = "./data/rates.db"

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3001", "http://127.0.0.1:3001"]

    # API
    API_TITLE: str = "Interest Rates API"
    API_VERSION: str = "1.0.0"

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore"
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            # Split by comma and strip whitespace
            return [origin.strip() for origin in v.split(",")]
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
