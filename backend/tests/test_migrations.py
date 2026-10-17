"""Миграции Alembic накатываются и откатываются на SQLite (на Postgres — в test_rls.py)."""
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

BACKEND = Path(__file__).resolve().parents[1]


def _alembic(url, *args):
    subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND,
        env={**os.environ, "DATABASE_URL": url},
        check=True,
        capture_output=True,
    )


def test_sqlite_upgrade_downgrade(tmp_path):
    url = f"sqlite:///{tmp_path / 'm.db'}"
    _alembic(url, "upgrade", "head")  # 0002 и 0003 на SQLite — no-op
    engine = create_engine(url)
    tables = set(inspect(engine).get_table_names())
    assert {"users", "facility_objects", "shift_reports", "billing_acts", "dispute_sources", "operators"} <= tables
    with engine.begin() as c:  # server_default created_at работает и в SQLite — для каждой новой таблицы с ним
        c.execute(text("INSERT INTO users (email, role) VALUES ('x@test.local', 'executive')"))
        assert c.execute(text("SELECT created_at FROM users")).scalar() is not None
        c.execute(text("INSERT INTO operators (code, subcontractor_id, active) VALUES ('OP-1', 1, 1)"))
        assert c.execute(text("SELECT created_at FROM operators")).scalar() is not None
    engine.dispose()
    _alembic(url, "downgrade", "base")
    assert set(inspect(create_engine(url)).get_table_names()) == {"alembic_version"}
