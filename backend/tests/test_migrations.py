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
    assert {
        "users", "facility_objects", "shift_reports", "billing_acts", "dispute_sources",
        "operators", "cleaning_orders", "order_photos", "operator_bonus_records", "client_discounts",
    } <= tables
    with engine.begin() as c:  # server_default created_at работает и в SQLite — для каждой новой таблицы с ним
        c.execute(text("INSERT INTO users (email, role) VALUES ('x@test.local', 'executive')"))
        assert c.execute(text("SELECT created_at FROM users")).scalar() is not None
        c.execute(text("INSERT INTO operators (code, subcontractor_id, active) VALUES ('OP-1', 1, 1)"))
        assert c.execute(text("SELECT created_at FROM operators")).scalar() is not None
        c.execute(text(
            "INSERT INTO cleaning_orders (created_by_id, city, area_m2, quality, team_mode, price_net, status, assigned_by_auto_priority) "
            "VALUES (1, 'Алматы', 10, 'standard', 'duo', 1000, 'new', 0)"
        ))
        assert c.execute(text("SELECT created_at FROM cleaning_orders")).scalar() is not None
        c.execute(text(
            "INSERT INTO order_photos (order_id, operator_id, file_path, content_type, ai_review_status) "
            "VALUES (1, 1, 'x.jpg', 'image/jpeg', 'not_evaluated')"
        ))
        assert c.execute(text("SELECT uploaded_at FROM order_photos")).scalar() is not None
        c.execute(text(
            "INSERT INTO operator_bonus_records (operator_id, scope, period_start, period_end, points, rank, total_operators, bonus_amount) "
            "VALUES (1, 'quarter', '2026-01-01', '2026-03-31', 100, 1, 5, 50000)"
        ))
        assert c.execute(text("SELECT closed_at FROM operator_bonus_records")).scalar() is not None
        c.execute(text("INSERT INTO client_companies (code, name) VALUES ('t1', 'Тест ТОО')"))
        c.execute(text(
            "INSERT INTO operator_ratings (order_id, operator_id, rated_by_id, cleanliness, quality, promptness, courtesy, average) "
            "VALUES (1, 1, 1, 2, 2, 2, 2, 2.0)"
        ))
        assert c.execute(text("SELECT created_at FROM operator_ratings WHERE order_id = 1")).scalar() is not None
        c.execute(text(
            "INSERT INTO client_discounts (client_company_id, pct, source_rating_id, status) VALUES (1, 15, 1, 'available')"
        ))
        assert c.execute(text("SELECT created_at FROM client_discounts")).scalar() is not None
        # Откат 0011 возвращает shift_report_id в NOT NULL — очищаем тестовую строку с order_id,
        # иначе батч-пересборка таблицы на SQLite упадёт на реальных данных (ожидаемо: откат не
        # предназначен сохранять данные через смену схемы, это проверка именно отката схемы).
        c.execute(text("DELETE FROM client_discounts"))
        c.execute(text("DELETE FROM operator_ratings"))
    engine.dispose()
    _alembic(url, "downgrade", "base")
    assert set(inspect(create_engine(url)).get_table_names()) == {"alembic_version"}
