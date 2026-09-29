"""초기 스키마 — 계정·수강·문서·조각·사용량. 설계 §3.

Revision ID: 0001
Revises:
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

UPGRADE = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE users (
    id            BIGSERIAL PRIMARY KEY,
    username      VARCHAR(64) NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    daily_quota   INTEGER NOT NULL DEFAULT 50 CHECK (daily_quota >= 0)
);

CREATE TABLE enrollments (
    user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    course_code VARCHAR(32) NOT NULL CHECK (course_code = upper(course_code)),
    PRIMARY KEY (user_id, course_code)
);

CREATE TABLE documents (
    id          BIGSERIAL PRIMARY KEY,
    scope       VARCHAR(16) NOT NULL CHECK (scope IN ('major', 'academic')),
    course_code VARCHAR(32) CHECK (course_code = upper(course_code)),
    path        TEXT NOT NULL UNIQUE,
    sha256      CHAR(64) NOT NULL,
    CONSTRAINT documents_scope_course CHECK ((scope = 'major') = (course_code IS NOT NULL)),
    CONSTRAINT documents_id_scope UNIQUE (id, scope),
    CONSTRAINT documents_id_scope_course UNIQUE (id, scope, course_code)
);

CREATE TABLE chunks (
    id          BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL,
    page        INTEGER NOT NULL CHECK (page >= 1),
    section     TEXT,
    ord         INTEGER NOT NULL,
    text        TEXT NOT NULL,
    embedding   vector(1536) NOT NULL,
    scope       VARCHAR(16) NOT NULL,
    course_code VARCHAR(32),
    CONSTRAINT chunks_scope_course CHECK ((scope = 'major') = (course_code IS NOT NULL)),
    -- 조각의 스코프·과목은 소속 문서와 같아야 한다 (필터 우회 방지)
    CONSTRAINT chunks_doc_scope FOREIGN KEY (document_id, scope)
        REFERENCES documents (id, scope) ON DELETE CASCADE,
    CONSTRAINT chunks_doc_scope_course FOREIGN KEY (document_id, scope, course_code)
        REFERENCES documents (id, scope, course_code) ON DELETE CASCADE
);

CREATE INDEX chunks_document_id ON chunks (document_id);
CREATE INDEX chunks_major_hnsw ON chunks USING hnsw (embedding vector_cosine_ops) WHERE scope = 'major';
CREATE INDEX chunks_academic_hnsw ON chunks USING hnsw (embedding vector_cosine_ops) WHERE scope = 'academic';

CREATE TABLE usage_daily (
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    day     DATE NOT NULL,
    count   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, day)
);
"""

DOWNGRADE = "DROP TABLE usage_daily, chunks, documents, enrollments, users;"


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
