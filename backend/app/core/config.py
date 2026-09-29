from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://dept_rag:dept_rag@localhost:5433/dept_rag"
    openai_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    chunk_max_chars: int = 800
    chunk_overlap: int = 100  # fixed 전략에서만 사용
    chunk_strategy: str = "structure"  # "fixed" | "structure" — docs/generated/chunk-comparison.md 참고
    data_dir: Path = Path("data")
    anthropic_api_key: str = ""
    generation_model: str = "claude-sonnet-5-5"
    generation_effort: str = "medium"
    generation_max_tokens: int = 4096
    search_k: int = 5
    search_min_score: float = 0.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
