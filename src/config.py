"""
Repository Intelligence Agent - Configuration Module
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Literal


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Neo4j Configuration
    neo4j_uri: str = Field(default="bolt://localhost:7687", env="NEO4J_URI")
    neo4j_user: str = Field(default="neo4j", env="NEO4J_USER")
    neo4j_password: str = Field(default="repoIntel2024!", env="NEO4J_PASSWORD")

    # LLM Configuration (Google Gemini)
    gemini_api_key: str | None = Field(default=None, env="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-2.0-flash-exp", env="GEMINI_MODEL")

    # Application Settings
    app_env: Literal["development", "production"] = Field(
        default="development", env="APP_ENV"
    )
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    temp_repo_dir: str = Field(default="./temp_repos", env="TEMP_REPO_DIR")
    max_file_size_mb: int = Field(default=10, env="MAX_FILE_SIZE_MB")

    # Embedding Configuration
    embedding_model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2", env="EMBEDDING_MODEL"
    )
    embedding_dimension: int = Field(default=384, env="EMBEDDING_DIMENSION")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Global settings instance
settings = Settings()
