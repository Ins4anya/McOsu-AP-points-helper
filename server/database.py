from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
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
    use_local_challenge: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
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
        Index("idx_scores_user_played_at", "user_id", "played_at"),
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
    count300: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    count100: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    count50: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    count_miss: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
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


class DailyChallengeMap(Base):
    __tablename__ = "daily_challenge_maps"
    __table_args__ = (
        Index("uq_challenge_maps_owner_date_slot", "user_id", "date", "slot", unique=True),
        Index("idx_challenge_maps_date", "date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    date: Mapped[str] = mapped_column(String(10), nullable=False)
    slot: Mapped[int] = mapped_column(Integer, nullable=False)
    beatmap_id: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    beatmapset_id: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    beatmap_title: Mapped[str] = mapped_column(String(256), nullable=False)
    version: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    stars: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    length: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    beatmap_url: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    download_url: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    completions: Mapped[list[ChallengeCompletion]] = relationship(
        "ChallengeCompletion", back_populates="challenge_map", cascade="all, delete-orphan"
    )


class UserLocalBeatmap(Base):
    __tablename__ = "user_local_beatmaps"
    __table_args__ = (
        Index("uq_user_local_beatmaps_user_map", "user_id", "beatmap_id", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    beatmap_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    beatmapset_id: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )


class ChallengeCompletion(Base):
    __tablename__ = "challenge_completions"
    __table_args__ = (
        Index("uq_challenge_completions_user_map", "user_id", "challenge_map_id", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    challenge_map_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("daily_challenge_maps.id"), nullable=False
    )
    score_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("scores.id"), nullable=True
    )
    bonus_ap: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    challenge_map: Mapped[DailyChallengeMap] = relationship(
        "DailyChallengeMap", back_populates="completions"
    )


class ChallengeBingo(Base):
    __tablename__ = "challenge_bingos"
    __table_args__ = (
        Index("uq_challenge_bingos_user_date", "user_id", "date", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    date: Mapped[str] = mapped_column(String(10), nullable=False)
    bonus_ap: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )


class StreakState(Base):
    __tablename__ = "streak_state"
    __table_args__ = (
        Index("uq_streak_state_user", "user_id", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    current_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_day: Mapped[str] = mapped_column(String(10), nullable=False, default="")
    payload_balance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    missing_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )


class StreakRevival(Base):
    __tablename__ = "streak_revivals"
    __table_args__ = (
        Index("idx_streak_revivals_user", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    missed_date: Mapped[str] = mapped_column(String(10), nullable=False)
    streak_after: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    revived_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )


class RankedState(Base):
    __tablename__ = "ranked_state"
    __table_args__ = (
        Index("idx_ranked_state_elo", "elo"),
    )

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), primary_key=True
    )
    elo: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    rerolls_today: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reroll_date: Mapped[str] = mapped_column(String(10), nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class RankedChallenge(Base):
    __tablename__ = "ranked_challenge"
    __table_args__ = (
        Index("idx_ranked_challenge_user_status", "user_id", "status"),
        # At most one active challenge per user (partial unique index).
        Index(
            "uq_ranked_challenge_user_active",
            "user_id",
            unique=True,
            sqlite_where=text("status = 'active'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    beatmap_id: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    beatmapset_id: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    beatmap_title: Mapped[str] = mapped_column(String(256), nullable=False)
    artist: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    version: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    stars: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    length_sec: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    download_url: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    issued_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    deadline_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    result_score_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("scores.id"), nullable=True
    )
    mods: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    grade: Mapped[str] = mapped_column(String(8), nullable=False, default="")
    accuracy: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    elo_delta: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    elo_after: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    settled_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )


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