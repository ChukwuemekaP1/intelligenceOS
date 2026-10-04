from functools import lru_cache
from typing import Literal

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

    # PostgreSQL
    POSTGRES_SERVER: str = "postgres"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "intelligenceos"
    POSTGRES_PASSWORD: str = "intelligenceos_secret"
    POSTGRES_DB: str = "intelligenceos"
    DATABASE_URL: str | None = None

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"

    # LLM Provider Configuration
    LLM_PROVIDER: Literal["gemini", "mock"] = "gemini"
    GEMINI_API_KEY: SecretStr | None = None
    GEMINI_MODEL: str = "gemini-3.8-flash"

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: Literal["json", "console"] = "json"

    # =========================================================================
    # Phase 2: Object Storage (S3-Compatible / MinIO)
    # =========================================================================
    # Storage backend: 's3' (MinIO/S3), 'local' (disk), or 'mock' (in-memory tests)
    STORAGE_BACKEND: Literal["s3", "local", "mock"] = "s3"
    S3_ENDPOINT_URL: str = "http://minio:9000"
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: SecretStr = SecretStr("minioadmin")
    S3_BUCKET_NAME: str = "intelligenceos-sources"
    S3_REGION: str = "us-east-1"
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

    # =========================================================================
    # Phase 2: Embedding Provider Configuration
    # =========================================================================
    # Select between 'gemini' (live embeddings) or 'mock' (fast deterministic offline vectors)
    EMBEDDING_PROVIDER: Literal["gemini", "mock"] = "gemini"
    GEMINI_EMBEDDING_MODEL: str = "text-embedding-004"
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

    @property
    def async_database_url(self) -> str:
        if self.DATABASE_URL:
            # Ensure using asyncpg driver
            url = str(self.DATABASE_URL)
            if url.startswith("postgresql://"):
                return url.replace("postgresql://", "postgresql+asyncpg://", 1)
            return url
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
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
