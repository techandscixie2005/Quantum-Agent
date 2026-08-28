"""Validated, server-only application configuration."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables.

    Secrets use :class:`SecretStr` so routine repr/logging cannot disclose
    credentials.  PostgreSQL is the production authority; SQLite is accepted
    only to support deterministic local and unit-test databases.
    """

    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        env_prefix="",
        case_sensitive=False,
        extra="ignore",
        validate_default=True,
    )

    environment: Literal["development", "test", "production"] = "development"
    database_url: str = Field(
        default="postgresql+asyncpg://quantum_agent:quantum_agent@localhost:5432/quantum_agent",
        validation_alias="DATABASE_URL",
    )
    database_echo: bool = Field(default=False, validation_alias="DATABASE_ECHO")
    database_pool_size: int = Field(default=10, ge=1, le=100)
    database_max_overflow: int = Field(default=20, ge=0, le=200)
    database_pool_timeout_seconds: float = Field(default=30.0, gt=0, le=300)

    embedding_dimension: Literal[384] = Field(
        default=384,
        validation_alias="EMBEDDING_DIMENSION",
    )
    embedding_provider: Literal["disabled", "local_hashing", "openai_compatible"] = Field(
        default="local_hashing",
        validation_alias="EMBEDDING_PROVIDER",
    )
    embedding_base_url: str | None = Field(
        default=None,
        validation_alias="EMBEDDING_BASE_URL",
    )
    embedding_api_key: SecretStr | None = Field(
        default=None,
        validation_alias="EMBEDDING_API_KEY",
    )
    embedding_model: str | None = Field(
        default=None,
        validation_alias="EMBEDDING_MODEL",
    )

    neo4j_uri: str = Field(default="neo4j://localhost:7687", validation_alias="NEO4J_URI")
    neo4j_user: str = Field(default="neo4j", validation_alias="NEO4J_USER")
    neo4j_password: SecretStr | None = Field(default=None, validation_alias="NEO4J_PASSWORD")
    neo4j_database: str = Field(default="neo4j", validation_alias="NEO4J_DATABASE")

    ustc_base_url: str = Field(
        default="https://api.llm.ustc.edu.cn/v1",
        validation_alias="USTC_BASE_URL",
    )
    ustc_api: SecretStr | None = Field(default=None, validation_alias="USTC_API")
    ustc_model: str = Field(default="deepseek-v4-pro", validation_alias="USTC_MODEL")
    ustc_vision_model: str = Field(default="qwen3.8-chat", validation_alias="USTC_VISION_MODEL")
    ustc_quick_model: str = Field(
        default="deepseek-v4-flash-ascend1",
        validation_alias="USTC_MODEL_QUICK",
    )
    ustc_second_pass_model: str = Field(
        default="qwen3.8-reasoner",
        validation_alias="USTC_MODEL_VISION_REASONER",
    )
    ustc_long_context_model: str = Field(
        default="glm-5.2",
        validation_alias="USTC_MODEL_CODE",
    )
    # PRD V3.1 §6: the Coding Agent routes its code-generation calls to this
    # model.  Defaults to the long-context/code model alias already wired in
    # compose.yaml; override with ``USTC_MODEL_CODE`` if a dedicated coding
    # model becomes available.
    ustc_code_model: str = Field(
        default="glm-5.2",
        validation_alias="USTC_MODEL_CODE_AGENT",
    )
    # PRD V3.1 §3.3: server-side session vault for user-supplied API keys.
    # The key is encrypted at rest with Fernet; ``SESSION_VAULT_KEY`` is the
    # 32-byte urlsafe Fernet key.  When unset, the vault falls back to a
    # derivation from ``SESSION_SECRET`` (legacy var kept for compatibility),
    # and when neither is set the vault is disabled and the startup
    # ``USTC_API`` env key is used for all sessions (dev/deploy fallback).
    session_vault_key: SecretStr | None = Field(
        default=None, validation_alias="SESSION_VAULT_KEY"
    )
    session_secret: SecretStr | None = Field(
        default=None, validation_alias="SESSION_SECRET"
    )
    redis_url: str | None = Field(
        default=None,
        validation_alias="REDIS_URL",
    )
    session_ttl_seconds: int = Field(
        default=28_800,
        ge=60,
        le=86400,
        validation_alias="SESSION_TTL_SECONDS",
    )
    coding_sandbox_enabled: bool = Field(
        default=True,
        validation_alias="CODING_SANDBOX_ENABLED",
    )
    # PRD V3.1 §3: API-key login.  A student enters their 词元计划/一〇七杯
    # API key; the backend probes the USTC model service, mints an opaque
    # session, and stores the Fernet-encrypted key in the session vault.
    # ``login_course_email`` identifies the find-or-create demo student the
    # API-key login binds to (the seeded competition account).  The legacy
    # shared-secret demo-login has been removed.
    login_course_email: str = Field(
        default="demo-student@quantum-agent.local",
        validation_alias="LOGIN_COURSE_EMAIL",
    )
    ustc_embedding_route_model: str = Field(
        default="qwen3-embedding",
        validation_alias="USTC_MODEL_EMBEDDING",
    )
    ustc_rerank_model: str = Field(
        default="qwen3-reranker",
        validation_alias="USTC_MODEL_RERANK",
    )
    ustc_document_parser_model: str = Field(
        default="mineru",
        validation_alias="USTC_MODEL_MINERU",
    )
    ustc_ocr_model: str = Field(
        default="unlimited-ocr",
        validation_alias="USTC_MODEL_OCR",
    )

    attachment_storage_root: Path = Field(
        default=Path("var/attachments"),
        validation_alias="ATTACHMENT_STORAGE_ROOT",
    )
    attachment_max_bytes: int = Field(
        default=25 * 1024 * 1024,
        ge=1024,
        le=200 * 1024 * 1024,
        validation_alias="ATTACHMENT_MAX_BYTES",
    )
    attachment_max_image_pixels: int = Field(
        default=40_000_000,
        ge=1,
        le=200_000_000,
        validation_alias="ATTACHMENT_MAX_IMAGE_PIXELS",
    )
    attachment_max_image_dimension: int = Field(
        default=16_384,
        ge=1,
        le=65_535,
        validation_alias="ATTACHMENT_MAX_IMAGE_DIMENSION",
    )
    attachment_max_document_pages: int = Field(
        default=500,
        ge=1,
        le=5_000,
        validation_alias="ATTACHMENT_MAX_DOCUMENT_PAGES",
    )
    attachment_max_archive_entries: int = Field(
        default=5_000,
        ge=1,
        le=50_000,
        validation_alias="ATTACHMENT_MAX_ARCHIVE_ENTRIES",
    )
    attachment_max_archive_uncompressed_bytes: int = Field(
        default=250 * 1024 * 1024,
        ge=1024,
        le=2 * 1024 * 1024 * 1024,
        validation_alias="ATTACHMENT_MAX_ARCHIVE_UNCOMPRESSED_BYTES",
    )
    attachment_max_archive_compression_ratio: float = Field(
        default=100.0,
        ge=1,
        le=1000,
        validation_alias="ATTACHMENT_MAX_ARCHIVE_COMPRESSION_RATIO",
    )

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        """Normalize common PostgreSQL URLs to SQLAlchemy's async driver."""

        value = value.strip()
        if value.startswith("postgres://"):
            return "postgresql+asyncpg://" + value.removeprefix("postgres://")
        if value.startswith("postgresql://"):
            return "postgresql+asyncpg://" + value.removeprefix("postgresql://")
        accepted = ("postgresql+asyncpg://", "sqlite+aiosqlite://")
        if not value.startswith(accepted):
            raise ValueError("DATABASE_URL must use postgresql+asyncpg or sqlite+aiosqlite")
        return value

    @field_validator("neo4j_uri")
    @classmethod
    def validate_neo4j_uri(cls, value: str) -> str:
        value = value.strip()
        if not value.startswith(("neo4j://", "neo4j+s://", "bolt://", "bolt+s://")):
            raise ValueError("NEO4J_URI must use a Neo4j or Bolt URI scheme")
        return value

    @field_validator("ustc_base_url")
    @classmethod
    def normalize_ustc_base_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if not value.startswith(("https://", "http://")):
            raise ValueError("USTC_BASE_URL must be an HTTP(S) URL")
        return value

    @field_validator(
        "ustc_model",
        "ustc_vision_model",
        "ustc_quick_model",
        "ustc_second_pass_model",
        "ustc_long_context_model",
        "ustc_code_model",
        "ustc_embedding_route_model",
        "ustc_rerank_model",
        "ustc_document_parser_model",
        "ustc_ocr_model",
    )
    @classmethod
    def normalize_ustc_model_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("USTC model route names must not be blank")
        return normalized

    @model_validator(mode="after")
    def reject_sqlite_in_production(self) -> Self:
        if self.environment == "production" and self.database_url.startswith("sqlite"):
            raise ValueError("SQLite is test-only; production requires PostgreSQL")
        if self.embedding_provider == "openai_compatible":
            if (
                self.embedding_base_url is None
                or self.embedding_api_key is None
                or self.embedding_model is None
            ):
                raise ValueError(
                    "OpenAI-compatible embeddings require their own URL, API key, and model"
                )
            normalized_url = self.embedding_base_url.strip().rstrip("/")
            if not normalized_url.startswith(("https://", "http://")):
                raise ValueError("EMBEDDING_BASE_URL must be an HTTP(S) URL")
            self.embedding_base_url = normalized_url
            self.embedding_model = self.embedding_model.strip()
            if not self.embedding_model:
                raise ValueError("EMBEDDING_MODEL must not be blank")
        if self.attachment_max_archive_uncompressed_bytes < self.attachment_max_bytes:
            raise ValueError(
                "ATTACHMENT_MAX_ARCHIVE_UNCOMPRESSED_BYTES must be at least ATTACHMENT_MAX_BYTES"
            )
        # PRD V3.1 §3.3: derive the session vault key from SESSION_SECRET
        # when SESSION_VAULT_KEY is unset, so deployments that already set
        # SESSION_SECRET get a working vault without a new secret.  The vault
        # is disabled (None) only when neither is set (or both are empty).
        if (
            self.session_vault_key is None
            and self.session_secret is not None
            and self.session_secret.get_secret_value().strip()
        ):
            self.session_vault_key = self.session_secret
        if (
            self.session_vault_key is not None
            and not self.session_vault_key.get_secret_value().strip()
        ):
            self.session_vault_key = None
        return self

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite+aiosqlite://")

    @property
    def effective_redis_url(self) -> str | None:
        """Resolve the Redis URL for the session vault.

        ``REDIS_URL`` wins when set; otherwise build a ``redis://`` URL from
        the ``REDIS_HOST`` / ``REDIS_PORT`` / ``REDIS_PASSWORD`` vars already
        used by compose.  Returns None when no Redis configuration is present
        (the vault then falls back to its in-memory backend).
        """

        if self.redis_url is not None:
            return self.redis_url
        if self.redis_host is None:
            return None
        auth = (
            f":{self.redis_password.get_secret_value()}@"
            if self.redis_password is not None
            else ""
        )
        return f"redis://{auth}{self.redis_host}:{self.redis_port or 6379}/0"

    redis_host: str | None = Field(default=None, validation_alias="REDIS_HOST")
    redis_port: int | None = Field(default=None, validation_alias="REDIS_PORT")
    redis_password: SecretStr | None = Field(
        default=None, validation_alias="REDIS_PASSWORD"
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide validated settings object."""

    return Settings()
