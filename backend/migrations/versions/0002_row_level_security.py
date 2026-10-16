"""row level security (только PostgreSQL / Supabase)

Revision ID: 0002
Revises: 0001
"""
from pathlib import Path
from typing import Sequence, Union

from alembic import context, op

revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
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
        return  # SQLite и др.: RLS нет, доступ ограничивает API (app/access.py)
    # Скрипт из нескольких команд с $$-блоками — выполняем драйвером без параметров.
    with bind.connection.dbapi_connection.cursor() as cur:
        cur.execute(sql)


def upgrade() -> None:
    _run("rls.sql")


def downgrade() -> None:
    _run("rls_down.sql")
