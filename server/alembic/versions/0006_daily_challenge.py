"""add daily challenge bingo tables

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    conn.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS daily_challenge_maps (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            date VARCHAR(10) NOT NULL,
            slot INTEGER NOT NULL,
            beatmap_id BIGINT NOT NULL DEFAULT 0,
            beatmapset_id BIGINT NOT NULL DEFAULT 0,
            beatmap_title VARCHAR(256) NOT NULL,
            version VARCHAR(128) NOT NULL DEFAULT '',
            stars FLOAT NOT NULL DEFAULT 0,
            length INTEGER NOT NULL DEFAULT 0,
            beatmap_url VARCHAR(512) NOT NULL DEFAULT '',
            download_url VARCHAR(512) NOT NULL DEFAULT '',
            created_at DATETIME NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS challenge_completions (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            challenge_map_id INTEGER NOT NULL REFERENCES daily_challenge_maps(id),
            score_id INTEGER REFERENCES scores(id),
            bonus_ap INTEGER NOT NULL DEFAULT 0,
            completed_at DATETIME NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS challenge_bingos (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            date VARCHAR(10) NOT NULL,
            bonus_ap INTEGER NOT NULL DEFAULT 0,
            completed_at DATETIME NOT NULL DEFAULT (datetime('now'))
        )
        """
    )

    conn.exec_driver_sql(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_challenge_maps_date_slot "
        "ON daily_challenge_maps(date, slot)"
    )
    conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS idx_challenge_maps_date "
        "ON daily_challenge_maps(date)"
    )
    conn.exec_driver_sql(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_challenge_completions_user_map "
        "ON challenge_completions(user_id, challenge_map_id)"
    )
    conn.exec_driver_sql(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_challenge_bingos_user_date "
        "ON challenge_bingos(user_id, date)"
    )


def downgrade() -> None:
    op.drop_table("challenge_bingos")
    op.drop_table("challenge_completions")
    op.drop_table("daily_challenge_maps")
