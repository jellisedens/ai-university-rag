from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    database_url: str = "postgresql+asyncpg://rag_user:rag_password@localhost:5432/rag_db"
    database_url_sync: str = "postgresql://rag_user:rag_password@localhost:5432/rag_db"

    # JWT Authentication
    secret_key: str = "CHANGE-ME-IN-PRODUCTION"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # File uploads
    upload_dir: str = "/app/uploads"
    max_upload_size_mb: int = 50

    # OpenAI
    openai_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    chat_model: str = "gpt-4o-mini"

    # RAG settings
    chunk_size: int = 800
    chunk_overlap: int = 150
    top_k_results: int = 8

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()