"""add score_key for reliable per-user dedup

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-14

"""
from typing import Sequence, Union
import hashlib

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _score_key(md5: str, mods: str, max_combo: int, accuracy: float, pp: float) -> str:
    payload = f"{md5}|{mods}|{max_combo}|{round(accuracy, 4)}|{round(pp, 1)}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def upgrade() -> None:
    conn = op.get_bind()

    insp = sa.inspect(conn)
    cols = {c["name"] for c in insp.get_columns("scores")}
    if "score_key" not in cols:
        op.add_column(
            "scores",
            sa.Column("score_key", sa.String(40), nullable=False, server_default=""),
        )

    rows = conn.exec_driver_sql(
        "SELECT id, md5, mods, max_combo, accuracy, pp "
        "FROM scores WHERE score_key = '' OR score_key IS NULL"
    ).fetchall()
    for row in rows:
        key = _score_key(
            row[1] or "", row[2] or "NM", row[3] or 0, row[4] or 0.0, row[5] or 0.0
        )
        conn.exec_driver_sql(
            "UPDATE scores SET score_key = ? WHERE id = ?", (key, row[0])
        )

    conn.exec_driver_sql(
        """DELETE FROM scores WHERE id NOT IN (
            SELECT MIN(id) FROM scores
            WHERE score_key IS NOT NULL AND score_key != ''
            GROUP BY user_id, score_key
        )"""
    )

    op.create_index(
        "uq_scores_user_score_key", "scores", ["user_id", "score_key"], unique=True
    )
    op.create_index("idx_scores_played_at", "scores", ["played_at"], unique=False)
    op.create_index("idx_scores_ap", "scores", ["ap"], unique=False)


def downgrade() -> None:
    op.drop_index("uq_scores_user_score_key", table_name="scores")
    op.drop_index("idx_scores_played_at", table_name="scores")
    op.drop_index("idx_scores_ap", table_name="scores")
    op.drop_column("scores", "score_key")