"""add streak state and revival tables

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    conn.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS streak_state (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            current_streak INTEGER NOT NULL DEFAULT 0,
            last_day VARCHAR(10) NOT NULL DEFAULT '',
            payload_balance INTEGER NOT NULL DEFAULT 0,
            missing_days INTEGER NOT NULL DEFAULT 0,
            updated_at DATETIME NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS streak_revivals (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            missed_date VARCHAR(10) NOT NULL,
            streak_after INTEGER NOT NULL DEFAULT 0,
            revived_at DATETIME NOT NULL DEFAULT (datetime('now'))
        )
        """
    )

    conn.exec_driver_sql(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_streak_state_user "
        "ON streak_state(user_id)"
    )
    conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS idx_streak_revivals_user "
        "ON streak_revivals(user_id)"
    )


def downgrade() -> None:
    op.drop_table("streak_revivals")
    op.drop_table("streak_state")
