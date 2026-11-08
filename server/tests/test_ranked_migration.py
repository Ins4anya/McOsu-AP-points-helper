"""Tests for the 0009 ranked migration (upgrade/downgrade + constraints)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

SERVER_DIR = Path(__file__).resolve().parents[1]


def _alembic_cfg(db_path: Path) -> Config:
    cfg = Config(str(SERVER_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")
    return cfg


def _table_names(db_path: Path) -> set[str]:
    conn = sqlite3.connect(str(db_path))
    try:
        return {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    finally:
        conn.close()


def test_migration_0009_upgrade_and_downgrade(tmp_path):
    db_path = tmp_path / "ranked_mig.db"
    cfg = _alembic_cfg(db_path)

    command.upgrade(cfg, "head")
    tables = _table_names(db_path)
    assert "ranked_state" in tables
    assert "ranked_challenge" in tables

    command.downgrade(cfg, "0008")
    tables = _table_names(db_path)
    assert "ranked_state" not in tables
    assert "ranked_challenge" not in tables


def test_one_active_challenge_per_user(tmp_path):
    db_path = tmp_path / "ranked_mig.db"
    cfg = _alembic_cfg(db_path)
    command.upgrade(cfg, "head")

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO users "
            "(osu_id, username, avatar_url, osu_access_token, osu_refresh_token) "
            "VALUES (1, 'u', '', '', '')"
        )
        uid = conn.execute("SELECT id FROM users WHERE osu_id = 1").fetchone()[0]

        conn.execute("INSERT INTO ranked_state (user_id) VALUES (?)", (uid,))
        elo = conn.execute(
            "SELECT elo FROM ranked_state WHERE user_id = ?", (uid,)
        ).fetchone()[0]
        assert elo == 100  # default ELO

        def insert_active(bid: int, title: str) -> None:
            conn.execute(
                "INSERT INTO ranked_challenge "
                "(user_id, beatmap_id, beatmap_title, issued_at, deadline_at, status) "
                "VALUES (?, ?, ?, '2026-01-01 00:00:00', '2026-01-01 00:10:00', 'active')",
                (uid, bid, title),
            )

        insert_active(1, "map A")
        conn.commit()

        # A second active challenge for the same user must fail.
        with pytest.raises(sqlite3.IntegrityError):
            insert_active(2, "map B")
    finally:
        conn.close()


def test_schema_matches_models(tmp_path):
    """After ``upgrade head``, tables/columns/indexes match the ORM models."""
    from sqlalchemy import create_engine, inspect

    from server.database import RankedChallenge, RankedState

    db_path = tmp_path / "ranked_mig.db"
    command.upgrade(_alembic_cfg(db_path), "head")

    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    insp = inspect(engine)

    # Tables and columns.
    for model in (RankedState, RankedChallenge):
        table = model.__tablename__
        db_cols = {c["name"] for c in insp.get_columns(table)}
        model_cols = {c.name for c in model.__table__.columns}
        assert model_cols == db_cols, table

    # Indexes: name, uniqueness and column set must match the model.
    for model in (RankedState, RankedChallenge):
        db_indexes = {i["name"]: i for i in insp.get_indexes(model.__tablename__)}
        for idx in model.__table__.indexes:
            assert idx.name in db_indexes, idx.name
            db = db_indexes[idx.name]
            assert bool(db["unique"]) == bool(idx.unique), idx.name
            assert set(db["column_names"]) == {c.name for c in idx.columns}, idx.name

    # The partial unique index must actually be partial, on status='active'.
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE type='index' AND name='uq_ranked_challenge_user_active'"
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert "WHERE status = 'active'" in row[0]

    # Composite (user_id, played_at) index for ranked settle_from_db.
    scores_indexes = {i["name"] for i in insp.get_indexes("scores")}
    assert "idx_scores_user_played_at" in scores_indexes
