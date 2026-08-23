from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
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
    flag: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    osu_access_token: Mapped[str] = mapped_column(Text, nullable=False)
    osu_refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    daily_goal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    onfire_goal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    scores: Mapped[list[Score]] = relationship(
        "Score", back_populates="user", cascade="all, delete-orphan"
    )


class Score(Base):
    __tablename__ = "scores"
    __table_args__ = (
        Index("uq_scores_user_score_key", "user_id", "score_key", unique=True),
        Index("idx_scores_played_at", "played_at"),
        Index("idx_scores_ap", "ap"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
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
    score_key: Mapped[str] = mapped_column(String(40), nullable=False, default="")

    density: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    aim: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    stars: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    ar: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    speed_mult: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    eff_cs: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    eff_ar: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    eff_od: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    eff_hp: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    played_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    user: Mapped[User] = relationship("User", back_populates="scores")


_engine = None
_SessionLocal = None


def _run_migrations(database_url: str):
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(Path(__file__).parent / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(cfg, "head")


async def init_db(config: ServerConfig):
    global _engine, _SessionLocal
    _engine = create_async_engine(config.database_url, echo=False)
    _SessionLocal = async_sessionmaker(_engine, expire_on_commit=False)
    _run_migrations(config.database_url)


async def close_db():
    global _engine
    if _engine:
        await _engine.dispose()


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with _SessionLocal() as session:
        yield session