"""add onfire_goal to users

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "users" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("users")}
        if "onfire_goal" not in cols:
            conn.exec_driver_sql(
                "ALTER TABLE users ADD COLUMN onfire_goal INTEGER NOT NULL DEFAULT 0"
            )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "users" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("users")}
        if "onfire_goal" in cols:
            conn.exec_driver_sql("ALTER TABLE users DROP COLUMN onfire_goal")