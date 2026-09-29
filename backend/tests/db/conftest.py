import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from tests.db._guard import assert_safe_test_db

BACKEND = Path(__file__).resolve().parents[2]
DEFAULT_URL = "postgresql+psycopg://dept_rag:dept_rag@localhost:5433/dept_rag_test"
TABLES = "users, enrollments, documents, chunks, usage_daily"


@pytest.fixture(scope="session")
def db_url() -> str:
    url = make_url(os.environ.get("TEST_DATABASE_URL", DEFAULT_URL))
    assert_safe_test_db(url.database)
    admin = sa.create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            try:
                conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{url.database}"')
            except sa.exc.DBAPIError as exc:
                pytest.fail(f"DROP DATABASE 실패 (사용 중인 연결이 있나?): {exc.__class__.__name__}")
            conn.exec_driver_sql(f'CREATE DATABASE "{url.database}"')
    except sa.exc.OperationalError as exc:
        pytest.fail(f"테스트 DB 연결 실패 → `make db-up` 후 다시 실행 ({exc.__class__.__name__})")
    finally:
        admin.dispose()
    rendered = url.render_as_string(hide_password=False)
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", rendered.replace("%", "%%"))
    command.upgrade(cfg, "head")
    return rendered


@pytest.fixture(scope="session")
def engine(db_url):
    eng = sa.create_engine(db_url)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        yield s
        s.rollback()
    with engine.begin() as conn:
        conn.exec_driver_sql(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE")
