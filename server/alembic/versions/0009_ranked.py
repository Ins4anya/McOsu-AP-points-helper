"""add ranked (ELO) state and challenge tables

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    conn.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS ranked_state (
            user_id INTEGER NOT NULL PRIMARY KEY REFERENCES users(id),
            elo INTEGER NOT NULL DEFAULT 100,
            rerolls_today INTEGER NOT NULL DEFAULT 0,
            reroll_date VARCHAR(10) NOT NULL DEFAULT '',
            updated_at DATETIME NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS ranked_challenge (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            beatmap_id BIGINT NOT NULL DEFAULT 0,
            beatmapset_id BIGINT NOT NULL DEFAULT 0,
            beatmap_title VARCHAR(256) NOT NULL,
            artist VARCHAR(256) NOT NULL DEFAULT '',
            version VARCHAR(128) NOT NULL DEFAULT '',
            stars FLOAT NOT NULL DEFAULT 0,
            length_sec INTEGER NOT NULL DEFAULT 0,
            download_url VARCHAR(512) NOT NULL DEFAULT '',
            issued_at DATETIME NOT NULL,
            deadline_at DATETIME NOT NULL,
            status VARCHAR(16) NOT NULL DEFAULT 'active',
            result_score_id INTEGER REFERENCES scores(id),
            mods VARCHAR(64) NOT NULL DEFAULT '',
            grade VARCHAR(8) NOT NULL DEFAULT '',
            accuracy FLOAT NOT NULL DEFAULT 0,
            elo_delta INTEGER NOT NULL DEFAULT 0,
            elo_after INTEGER NOT NULL DEFAULT 0,
            settled_at DATETIME,
            created_at DATETIME NOT NULL DEFAULT (datetime('now'))
        )
        """
    )

    conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS idx_ranked_state_elo ON ranked_state(elo)"
    )
    conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS idx_ranked_challenge_user_status "
        "ON ranked_challenge(user_id, status)"
    )
    # At most one active challenge per user.
    conn.exec_driver_sql(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_ranked_challenge_user_active "
        "ON ranked_challenge(user_id) WHERE status = 'active'"
    )
    # Composite index for Ranked settle_from_db (scores of one user by time).
    conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS idx_scores_user_played_at "
        "ON scores(user_id, played_at)"
    )


def downgrade() -> None:
    op.drop_table("ranked_challenge")
    op.drop_table("ranked_state")
