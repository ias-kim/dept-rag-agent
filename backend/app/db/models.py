"""ORM 모델 — DB 구조의 SoT는 migrations/. 제약(CHECK·FK)은 마이그레이션에만 있다."""

from datetime import date

from pgvector.sqlalchemy import Vector
from sqlalchemy import Date, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

EMBEDDING_DIM = 1536
SCOPES = ("major", "academic")


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64))
    password_hash: Mapped[str] = mapped_column(Text)
    daily_quota: Mapped[int] = mapped_column(Integer, default=50)


class Enrollment(Base):
    __tablename__ = "enrollments"
    user_id: Mapped[int] = mapped_column(primary_key=True)
    course_code: Mapped[str] = mapped_column(String(32), primary_key=True)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    scope: Mapped[str] = mapped_column(String(16))
    course_code: Mapped[str | None] = mapped_column(String(32))
    path: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))


class Chunk(Base):
    __tablename__ = "chunks"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column()
    page: Mapped[int] = mapped_column()
    section: Mapped[str | None] = mapped_column(Text)
    ord: Mapped[int] = mapped_column()
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
    scope: Mapped[str] = mapped_column(String(16))
    course_code: Mapped[str | None] = mapped_column(String(32))


class UsageDaily(Base):
    __tablename__ = "usage_daily"
    user_id: Mapped[int] = mapped_column(primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)
