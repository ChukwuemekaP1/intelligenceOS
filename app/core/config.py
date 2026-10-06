from functools import lru_cache
from typing import Literal
from urllib.parse import quote_plus

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    ENVIRONMENT: Literal["development", "production", "testing"] = "development"
    DEBUG: bool = False
    PROJECT_NAME: str = "IntelligenceOS"
    API_V1_STR: str = "/api/v1"

    # Security
    SECRET_KEY: str = "dev-secret-key-32-characters-minimum-for-intelligence-os"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    CORS_ORIGINS: list[str] | str = ["*"]

    # PostgreSQL
    POSTGRES_SERVER: str = "postgres"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "intelligenceos"
    POSTGRES_PASSWORD: str = "intelligenceos_secret"
    POSTGRES_DB: str = "intelligenceos"
    DATABASE_URL: str | None = None

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"
    REDIS_CONNECT_TIMEOUT: float = 15.0
    REDIS_SOCKET_TIMEOUT: float = 15.0
    # Set to "none" only for private Redis instances with self-signed TLS certificates.
    # Never use in production without understanding the security implications.
    REDIS_SSL_CERT_REQS: str = "required"

    # LLM Provider Configuration
    LLM_PROVIDER: Literal["gemini", "mock"] = "gemini"
    GEMINI_API_KEY: SecretStr | None = None
    GEMINI_MODEL: str = "gemini-3.5-flash-lite"

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: Literal["json", "console"] = "json"

    # =========================================================================
    # Object Storage (Supabase Storage)
    # =========================================================================
    # Storage backend: 'supabase' (Supabase Storage), 'local' (disk), or 'mock' (in-memory tests)
    STORAGE_BACKEND: Literal["supabase", "local", "mock"] = "supabase"
    SUPABASE_URL: str | None = None
    SUPABASE_SERVICE_ROLE_KEY: SecretStr | None = None
    SUPABASE_STORAGE_BUCKET: str = "IntellegnceOS(Files)"
    SUPABASE_ANON_KEY: SecretStr | None = None
    LOCAL_STORAGE_DIR: str = "./storage_data"
    MAX_UPLOAD_SIZE_BYTES: int = 20 * 1024 * 1024  # 20 MB limit

    # =========================================================================
    # Phase 2: Vector Storage (Qdrant)
    # =========================================================================
    QDRANT_HOST: str = "qdrant"
    QDRANT_PORT: int = 6333
    QDRANT_URL: str | None = None
    QDRANT_API_KEY: SecretStr | None = None
    QDRANT_COLLECTION: str = "intelligenceos_chunks"
    QDRANT_TIMEOUT: float = 15.0

    # =========================================================================
    # Phase 2: Embedding Provider Configuration
    # =========================================================================
    # Select between 'gemini' (live embeddings) or 'mock' (fast deterministic offline vectors)
    EMBEDDING_PROVIDER: Literal["gemini", "mock"] = "gemini"
    GEMINI_EMBEDDING_MODEL: str = "gemini-embedding-001"
    EMBEDDING_DIMENSION: int = 768

    # =========================================================================
    # Phase 2: Background Ingestion Queue (Redis)
    INGESTION_QUEUE_NAME: str = "intelligenceos:jobs:ingestion"

    # =========================================================================
    # Phase 3: RAG Retrieval, Reranking & Generation
    # =========================================================================
    RAG_INITIAL_TOP_K: int = 20
    RAG_FINAL_TOP_K: int = 5
    RAG_SIMILARITY_THRESHOLD: float | None = 0.0
    RAG_ENABLE_RERANKING: bool = True
    RAG_RETRIEVAL_MODE: Literal["semantic", "hybrid"] = "hybrid"
    RERANKER_TYPE: Literal["local", "none", "external"] = "local"
    RERANKER_API_KEY: SecretStr | None = None
    RERANKER_ENDPOINT: str | None = None
    RERANKER_MODEL: str | None = None
    RAG_MAX_CONTEXT_CHARS: int = 16000

    # Phase 4: Agent & Tool Orchestration Layer
    AGENT_MAX_STEPS: int = 6
    AGENT_TIMEOUT_SECONDS: float = 30.0
    AGENT_SQL_ROW_LIMIT: int = 50
    AGENT_SQL_TIMEOUT_SECONDS: float = 5.0
    WEB_SEARCH_PROVIDER: str = "mock"
    WEB_SEARCH_MAX_RESULTS: int = 5

    # Worker stale-job detection
    # Sources stuck in PROCESSING for longer than this are eligible for failure marking
    WORKER_STALE_THRESHOLD_SECONDS: int = 600   # 10 minutes
    WORKER_STALE_SCAN_INTERVAL_SECONDS: int = 120  # scan every 2 minutes

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: object) -> list[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        if isinstance(v, list):
            return [str(origin).strip() for origin in v]
        return ["*"]

    @property
    def async_database_url(self) -> str:
        if self.DATABASE_URL:
            # Ensure using asyncpg driver and handle sslmode query param
            url = str(self.DATABASE_URL)
            if url.startswith("postgres://"):
                url = url.replace("postgres://", "postgresql+asyncpg://", 1)
            elif url.startswith("postgresql://"):
                url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
            if "sslmode=" in url:
                url = url.replace("sslmode=", "ssl=")
            return url
        encoded_user = quote_plus(self.POSTGRES_USER)
        encoded_password = quote_plus(self.POSTGRES_PASSWORD)
        return (
            f"postgresql+asyncpg://{encoded_user}:{encoded_password}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError(
                "SECRET_KEY must be at least 32 characters long for production security"
            )
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
