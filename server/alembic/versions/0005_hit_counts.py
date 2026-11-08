"""add hit counts (300/100/50/miss) to scores

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = {c["name"] for c in insp.get_columns("scores")}

    additions = {
        "count300": sa.Column("count300", sa.Integer, nullable=False, server_default="0"),
        "count100": sa.Column("count100", sa.Integer, nullable=False, server_default="0"),
        "count50": sa.Column("count50", sa.Integer, nullable=False, server_default="0"),
        "count_miss": sa.Column("count_miss", sa.Integer, nullable=False, server_default="0"),
    }
    for name, col in additions.items():
        if name not in cols:
            op.add_column("scores", col)


def downgrade() -> None:
    for name in ("count300", "count100", "count50", "count_miss"):
        try:
            op.drop_column("scores", name)
        except Exception:
            pass
