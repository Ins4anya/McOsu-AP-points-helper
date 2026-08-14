"""add speed_mult and effective difficulty stats to scores

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = {c["name"] for c in insp.get_columns("scores")}

    additions = {
        "speed_mult": sa.Column("speed_mult", sa.Float, nullable=False, server_default="1.0"),
        "eff_cs": sa.Column("eff_cs", sa.Float, nullable=False, server_default="0.0"),
        "eff_ar": sa.Column("eff_ar", sa.Float, nullable=False, server_default="0.0"),
        "eff_od": sa.Column("eff_od", sa.Float, nullable=False, server_default="0.0"),
        "eff_hp": sa.Column("eff_hp", sa.Float, nullable=False, server_default="0.0"),
    }
    for name, col in additions.items():
        if name not in cols:
            op.add_column("scores", col)


def downgrade() -> None:
    for name in ("speed_mult", "eff_cs", "eff_ar", "eff_od", "eff_hp"):
        try:
            op.drop_column("scores", name)
        except Exception:
            pass