import os
from typing import Literal

from pydantic import Field, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env.local" if os.path.exists(".env.local") else ".env",
        env_file_encoding="utf-8",
    )

    ENV: Literal["stag", "prod", "local"] = Field(default="local")

    POSTGRES_HOST: str
    POSTGRES_PORT: int
    POSTGRES_DB: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_URI: str = ""
    REDIRECT_URI: str
    CLIENT_SECRET_FILE: str
    TOKEN_FILE: str
    PORT: int
    GMAIL_TOPIC_NAME: str

    @field_validator("POSTGRES_URI", mode="after")
    @classmethod
    def validate_db_uri(cls, _, info: ValidationInfo):
        password = info.data["POSTGRES_PASSWORD"]
        user = info.data["POSTGRES_USER"]
        host = info.data["POSTGRES_HOST"]
        port = info.data["POSTGRES_PORT"]
        db = info.data["POSTGRES_DB"]
        return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"


settings = Settings()
