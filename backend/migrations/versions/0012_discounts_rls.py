"""RLS для скидок клиенту за низкую оценку (только PostgreSQL / Supabase)

Revision ID: 0012
Revises: 0011
"""
from pathlib import Path
from typing import Sequence, Union

from alembic import context, op

revision: str = "0012"
down_revision: Union[str, Sequence[str], None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DB_DIR = Path(__file__).resolve().parents[2] / "db"


def _run(filename: str) -> None:
    sql = (DB_DIR / filename).read_text(encoding="utf-8")
    if context.is_offline_mode():
        op.execute(sql)
        return
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return  # в API то же правило — app/access.py
    with bind.connection.dbapi_connection.cursor() as cur:
        cur.execute(sql)


def upgrade() -> None:
    _run("rls_0012_discounts.sql")


def downgrade() -> None:
    _run("rls_0012_down.sql")
