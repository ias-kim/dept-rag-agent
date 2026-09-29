from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://dept_rag:dept_rag@localhost:5433/dept_rag"
    openai_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    chunk_max_chars: int = 800
    chunk_overlap: int = 100
    data_dir: Path = Path("data")


@lru_cache
def get_settings() -> Settings:
    return Settings()
