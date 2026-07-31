from __future__ import annotations

from datetime import datetime, timezone
from typing import AsyncGenerator

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from server.config import ServerConfig


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    osu_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    avatar_url: Mapped[str] = mapped_column(String(512), nullable=False)
    osu_access_token: Mapped[str] = mapped_column(Text, nullable=False)
    osu_refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    daily_goal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    scores: Mapped[list[Score]] = relationship(
        "Score", back_populates="user", cascade="all, delete-orphan"
    )


class Score(Base):
    __tablename__ = "scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    beatmap_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    beatmap_title: Mapped[str] = mapped_column(String(256), nullable=False)
    beatmap_url: Mapped[str] = mapped_column(String(512), nullable=False)

    md5: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    mods: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="mcsu")
    accuracy: Mapped[float] = mapped_column(Float, nullable=False)
    max_combo: Mapped[int] = mapped_column(Integer, nullable=False)
    max_possible_combo: Mapped[int] = mapped_column(Integer, nullable=False)
    pp: Mapped[float] = mapped_column(Float, nullable=False)
    ap: Mapped[float] = mapped_column(Float, nullable=False)
    rank: Mapped[str] = mapped_column(String(8), nullable=False)

    density: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    aim: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    stars: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    ar: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    played_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    user: Mapped[User] = relationship("User", back_populates="scores")


_engine = None
_SessionLocal = None


async def init_db(config: ServerConfig):
    global _engine, _SessionLocal
    _engine = create_async_engine(config.database_url, echo=False)
    _SessionLocal = async_sessionmaker(_engine, expire_on_commit=False)
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    global _engine
    if _engine:
        await _engine.dispose()


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with _SessionLocal() as session:
        yield session
