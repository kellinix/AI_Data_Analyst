from __future__ import annotations

from functools import lru_cache
from typing import Any, Literal

from pydantic import (
    AliasChoices,
    Field,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ────────────────────────────────────────────────────────────────
    app_name: str = "AI Dashboard Generator"
    app_version: str = "1.0.0"
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = False
    secret_key: str
    allowed_hosts: list[str] = ["*"]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    # ── CORS ───────────────────────────────────────────────────────────────
    cors_origins: list[str] = ["http://localhost:3000"]
    cors_allow_credentials: bool = True

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    # ── Database ───────────────────────────────────────────────────────────
    database_url_override: str = Field(default="", validation_alias="DATABASE_URL")
    sync_database_url_override: str = Field(default="", validation_alias="DATABASE_URL_SYNC")
    postgres_server: str = Field(
        default="localhost",
        validation_alias=AliasChoices("POSTGRES_SERVER", "POSTGRES_HOST"),
    )
    postgres_port: int = 5432
    postgres_user: str = "ai_dashboard_user"
    postgres_password: str
    postgres_db: str = "ai_dashboard"

    @property
    def database_url(self) -> str:
        if self.database_url_override:
            return self.database_url_override
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_server}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def sync_database_url(self) -> str:
        if self.sync_database_url_override:
            return self.sync_database_url_override
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_server}:{self.postgres_port}/{self.postgres_db}"
        )

    # ── Redis ──────────────────────────────────────────────────────────────
    redis_url_override: str = Field(default="", validation_alias="REDIS_URL")
    celery_broker_url_override: str = Field(default="", validation_alias="CELERY_BROKER_URL")
    celery_result_backend_override: str = Field(default="", validation_alias="CELERY_RESULT_BACKEND")
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = ""
    redis_db: int = 0

    @property
    def redis_url(self) -> str:
        if self.redis_url_override:
            return self.redis_url_override
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def celery_broker_url(self) -> str:
        if self.celery_broker_url_override:
            return self.celery_broker_url_override
        return self.redis_url

    @property
    def celery_result_backend(self) -> str:
        if self.celery_result_backend_override:
            return self.celery_result_backend_override
        return self.redis_url

    # ── OpenAI ─────────────────────────────────────────────────────────────
    openai_api_key: str
    openai_model: str = "gpt-4o"
    openai_embedding_model: str = "text-embedding-3-small"
    openai_max_tokens: int = 4096
    openai_temperature: float = 0.2

    # ── Supabase ───────────────────────────────────────────────────────────
    supabase_url: str = ""
    supabase_anon_key: str = Field(
        default="",
        validation_alias=AliasChoices("SUPABASE_ANON_KEY", "NEXT_PUBLIC_SUPABASE_ANON_KEY"),
    )
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""

    @model_validator(mode="after")
    def require_production_secrets(self) -> Settings:
        if self.is_production:
            missing = [
                name
                for name in (
                    "secret_key",
                    "openai_api_key",
                    "supabase_url",
                    "supabase_anon_key",
                    "supabase_service_role_key",
                    "supabase_jwt_secret",
                )
                if not getattr(self, name)
            ]
            if missing:
                raise ValueError(
                    "Missing required production settings: " + ", ".join(missing)
                )
        return self

    # ── Storage ────────────────────────────────────────────────────────────
    storage_backend: Literal["supabase", "s3", "local"] = "local"
    storage_bucket: str = "uploads"
    upload_dir: str = "/app/uploads"

    # S3-compatible
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "us-east-1"
    aws_s3_bucket: str = ""
    aws_endpoint_url: str = ""

    # ── File limits ────────────────────────────────────────────────────────
    max_upload_size_bytes: int = 512 * 1024 * 1024  # 512 MB
    allowed_file_extensions: list[str] = [
        ".csv", ".xlsx", ".xls", ".json", ".parquet", ".tsv"
    ]

    # ── Security ───────────────────────────────────────────────────────────
    access_token_expire_minutes: int = 60 * 24  # 24 hours
    algorithm: str = "HS256"

    # ── Rate limiting ──────────────────────────────────────────────────────
    rate_limit_per_minute: int = 100
    upload_rate_limit_per_minute: int = 10

    # ── Analysis engine ────────────────────────────────────────────────────
    max_sample_rows: int = 100_000      # rows sampled for AI context
    max_chart_columns: int = 20
    analysis_timeout_seconds: int = 300

    # AI-generated code execution is intentionally disabled unless an external
    # isolated sandbox provider is configured. Never run generated code locally.
    ai_code_execution_enabled: bool = False
    ai_code_execution_provider: Literal["disabled", "remote_http"] = "disabled"
    ai_code_execution_endpoint: str = ""
    ai_code_execution_api_key: str = ""
    ai_code_execution_timeout_seconds: int = 15
    ai_code_execution_max_repair_attempts: int = 2
    semantic_wrangling_enabled: bool = True
    semantic_wrangling_use_embeddings: bool = True
    semantic_wrangling_similarity_threshold: float = 0.91
    semantic_wrangling_max_columns: int = 6
    semantic_wrangling_max_unique_values: int = 80

    # ── Data retention ─────────────────────────────────────────────────────
    file_retention_days: int = 30
    analysis_retention_days: int = 90

    # ── Celery ─────────────────────────────────────────────────────────────
    celery_task_timeout: int = 600
    celery_max_retries: int = 3

    # ── Sentry ─────────────────────────────────────────────────────────────
    sentry_dsn: str = ""

    # ── Stripe ─────────────────────────────────────────────────────────────
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_pro_price_id: str = ""
    stripe_enterprise_price_id: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
