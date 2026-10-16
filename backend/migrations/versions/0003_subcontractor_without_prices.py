"""субподрядчик видит объекты без цен клиента (только PostgreSQL / Supabase)

Revision ID: 0003
Revises: 0002
"""
from pathlib import Path
from typing import Sequence, Union

from alembic import context, op

revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
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
        return  # в API то же правило — FacilityObjectForSubcontractor
    with bind.connection.dbapi_connection.cursor() as cur:
        cur.execute(sql)


def upgrade() -> None:
    _run("rls_0003_subcontractor_view.sql")


def downgrade() -> None:
    _run("rls_0003_down.sql")
