"""Environment-driven settings. Fails fast on missing/invalid config instead of a raw traceback."""

import sys

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mongo_uri: str = Field(alias="MONGO_URI")
    mongo_db_name: str = Field(default="docintel_cons_cons", alias="MONGO_DB_NAME")
    groq_api_keys_raw: str = Field(alias="GROQ_API_KEYS")
    # Groq retires models without notice (llama-3.3-70b-versatile was removed and every
    # extraction started failing with a 404) - so the model is configuration, not a constant.
    groq_model: str = Field(default="openai/gpt-oss-120b", alias="GROQ_MODEL")
    environment: str = Field(default="development", alias="NODE_ENV")
    model_type: str = Field(default="consignor_consignee", alias="MODEL_TYPE")
    jwt_secret: str = Field(alias="JWT_SECRET")
    port: int = Field(default=9000, alias="PORT")
    frontend_origin: str = Field(default="http://localhost:6001", alias="FRONTEND_ORIGIN")
    admin_origin: str = Field(default="http://localhost:7000", alias="ADMIN_ORIGIN")

    # /docs, /redoc and /openapi.json are OFF unless this is explicitly true (an API map is
    # useful to attackers); turn it on only for local development.
    enable_docs: bool = Field(default=False, alias="ENABLE_DOCS")

    # Re-queue documents left in "processing" by a restart (background task at startup).
    recover_interrupted_uploads: bool = Field(default=True, alias="RECOVER_INTERRUPTED_UPLOADS")

    admin_1_email: str = Field(default="", alias="ADMIN_1_EMAIL")
    admin_1_password: str = Field(default="", alias="ADMIN_1_PASSWORD")
    admin_1_username: str = Field(default="", alias="ADMIN_1_USERNAME")
    admin_2_email: str = Field(default="", alias="ADMIN_2_EMAIL")
    admin_2_password: str = Field(default="", alias="ADMIN_2_PASSWORD")
    admin_2_username: str = Field(default="", alias="ADMIN_2_USERNAME")

    # Cap on the STORED bytes of all chat attachments together (MB). Blank = 75.
    chat_files_max_total_mb: int = Field(default=75, alias="CHAT_FILES_MAX_TOTAL_MB")

    @field_validator("chat_files_max_total_mb", mode="before")
    @classmethod
    def _clean_chat_cap(cls, value: object) -> object:
        if value is None or (isinstance(value, str) and not value.strip()):
            return 75
        text = str(value).strip()
        if not text.isascii() or not text.isdigit() or not 1 <= int(text) <= 100000:
            raise ValueError("CHAT_FILES_MAX_TOTAL_MB must be a whole number from 1 to 100000.")
        return int(text)

    @field_validator("jwt_secret")
    @classmethod
    def _jwt_secret_min_length(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters")
        return v

    @property
    def groq_api_keys(self) -> list[str]:
        return [k.strip() for k in self.groq_api_keys_raw.split(",") if k.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def cors_origins(self) -> list[str]:
        return [self.frontend_origin, self.admin_origin]


def _load_settings() -> Settings:
    try:
        return Settings()  # type: ignore[call-arg]
    except Exception as exc:  # noqa: BLE001 - deliberate fail-fast boundary
        print(f"FATAL: invalid configuration - {exc}", file=sys.stderr)
        sys.exit(1)


settings = _load_settings()
