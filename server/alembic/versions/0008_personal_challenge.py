"""add personal daily challenge and local beatmap library

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    conn.exec_driver_sql(
        "ALTER TABLE users ADD COLUMN use_local_challenge BOOLEAN NOT NULL DEFAULT 0"
    )
    conn.exec_driver_sql(
        "ALTER TABLE daily_challenge_maps ADD COLUMN user_id INTEGER NOT NULL DEFAULT 0"
    )
    conn.exec_driver_sql("DROP INDEX IF EXISTS uq_challenge_maps_date_slot")
    conn.exec_driver_sql(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_challenge_maps_owner_date_slot "
        "ON daily_challenge_maps(user_id, date, slot)"
    )
    conn.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS user_local_beatmaps (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            beatmap_id BIGINT NOT NULL,
            beatmapset_id BIGINT NOT NULL DEFAULT 0,
            updated_at DATETIME NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.exec_driver_sql(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_user_local_beatmaps_user_map "
        "ON user_local_beatmaps(user_id, beatmap_id)"
    )


def downgrade() -> None:
    op.drop_table("user_local_beatmaps")
    op.execute("DROP INDEX IF EXISTS uq_challenge_maps_owner_date_slot")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_challenge_maps_date_slot "
        "ON daily_challenge_maps(date, slot)"
    )
    with op.batch_alter_table("daily_challenge_maps") as batch:
        batch.drop_column("user_id")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("use_local_challenge")
