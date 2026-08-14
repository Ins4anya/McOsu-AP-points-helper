"""baseline schema: users and scores

Revision ID: 0001
Revises:
Create Date: 2026-08-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    conn.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            osu_id BIGINT NOT NULL UNIQUE,
            username VARCHAR(64) NOT NULL,
            avatar_url VARCHAR(512) NOT NULL,
            flag VARCHAR(32) NOT NULL DEFAULT '',
            osu_access_token TEXT NOT NULL,
            osu_refresh_token TEXT NOT NULL,
            daily_goal INTEGER NOT NULL DEFAULT 0,
            created_at DATETIME NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS scores (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            beatmap_id BIGINT NOT NULL,
            beatmap_title VARCHAR(256) NOT NULL,
            beatmap_url VARCHAR(512) NOT NULL,
            md5 VARCHAR(64) NOT NULL DEFAULT '',
            mods VARCHAR(64) NOT NULL,
            source VARCHAR(16) NOT NULL DEFAULT 'mcsu',
            accuracy FLOAT NOT NULL,
            max_combo INTEGER NOT NULL,
            max_possible_combo INTEGER NOT NULL,
            pp FLOAT NOT NULL,
            ap FLOAT NOT NULL,
            rank VARCHAR(8) NOT NULL,
            density FLOAT NOT NULL DEFAULT 0,
            aim FLOAT NOT NULL DEFAULT 0,
            stars FLOAT NOT NULL DEFAULT 0,
            ar FLOAT NOT NULL DEFAULT 0,
            played_at DATETIME NOT NULL,
            created_at DATETIME NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_scores_user_id ON scores(user_id)"
    )

    insp = sa.inspect(conn)
    if "users" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("users")}
        if "flag" not in cols:
            conn.exec_driver_sql(
                "ALTER TABLE users ADD COLUMN flag VARCHAR(32) NOT NULL DEFAULT ''"
            )


def downgrade() -> None:
    op.drop_table("scores")
    op.drop_table("users")