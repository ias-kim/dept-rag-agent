from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


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
    classify_model: str = "claude-haiku-4-5-20251001"
    classify_max_tokens: int = 16  # 라벨 한 단어만 받는다. 늘리면 설명이 붙어 형식 오류(→both)가 는다
    router_mode: str = "workflow"  # "baseline" | "workflow" — app/core/pipeline.py MODES
    jwt_secret: str = ""  # 32자 이상. 비거나 짧으면 토큰 발급·검증을 모두 거부한다 (app/core/security.py)
    jwt_ttl_hours: int = 12
    default_daily_quota: int = 50
    login_max_attempts_per_account: int = 5  # (IP, 아이디)별 — 창 안에서 이만큼 시도하면 429
    login_max_attempts_per_ip: int = 20  # IP별 — 아이디를 바꿔 가며 뿌리는 시도까지 막는다
    login_window_minutes: int = 15
    # 빌드된 화면 위치. 없으면 API만 뜬다(app/main.py). 컨테이너는 FRONTEND_DIST_DIR로 덮어쓴다
    frontend_dist_dir: Path = REPO_ROOT / "frontend" / "dist"


@lru_cache
def get_settings() -> Settings:
    return Settings()
