"""RLS-политики db/rls.sql на настоящем PostgreSQL.

Запуск: PG_TEST_ADMIN_URL=postgresql+psycopg://postgres@localhost:5432/postgres pytest tests/test_rls.py
Тест создаёт отдельную базу, накатывает заглушку Supabase (auth.uid(), роли anon/authenticated),
миграции Alembic и сидинг, затем выполняет запросы от имени роли authenticated с JWT-claims —
так же, как их выполняет PostgREST в Supabase.
"""
import copy
import datetime as dt
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.orm import sessionmaker

from app import models as m
from app.services.importer import import_contracts
from tests.conftest import AS_OF, create_users

ADMIN_URL = os.getenv("PG_TEST_ADMIN_URL")
BACKEND = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(not ADMIN_URL, reason="задайте PG_TEST_ADMIN_URL для тестов RLS")

DB_NAME = "icgroup_rls_test"


@pytest.fixture(scope="module")
def pg(raw):
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {DB_NAME} WITH (FORCE)"))
        c.execute(text(f"CREATE DATABASE {DB_NAME}"))
    admin.dispose()
    url = make_url(ADMIN_URL).set(database=DB_NAME)
    url_str = url.render_as_string(hide_password=False)

    engine = create_engine(url_str)
    with engine.begin() as c:
        c.exec_driver_sql((BACKEND / "db" / "local_supabase_stub.sql").read_text(encoding="utf-8"))
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND,
        env={**os.environ, "DATABASE_URL": url_str},
        check=True,
        capture_output=True,
    )
    with engine.begin() as c:
        # В Supabase у anon есть табличные привилегии — повторяем, чтобы проверить, что режет именно RLS.
        c.execute(text("GRANT USAGE ON SCHEMA public TO anon; GRANT SELECT ON ALL TABLES IN SCHEMA public TO anon"))

    db = sessionmaker(bind=engine, expire_on_commit=False)()
    import_contracts(db, copy.deepcopy(raw), as_of=AS_OF)
    users = create_users(db, with_auth_ids=True)
    modena = users["modena@test.local"].client_company_id
    p24 = users["p24@test.local"].subcontractor_id
    db.add_all(
        [
            m.BillingAct(kind="client_avr", period_month=dt.date(2026, 9, 1), client_company_id=modena),
            m.BillingAct(kind="subcontractor_act", period_month=dt.date(2026, 9, 1), subcontractor_id=p24),
        ]
    )
    db.commit()
    db.close()
    yield engine, {email: u for email, u in users.items()}
    engine.dispose()


def run_as(engine, auth_id, sql, params=None, role="authenticated"):
    """Выполнить SQL от имени пользователя Supabase; транзакция откатывается."""
    with engine.connect() as c:
        tx = c.begin()
        try:
            c.execute(text(f"SET LOCAL ROLE {role}"))
            claims = json.dumps({"sub": str(auth_id), "role": role}) if auth_id else ""
            c.execute(text("SELECT set_config('request.jwt.claims', :c, true)"), {"c": claims})
            result = c.execute(text(sql), params or {})
            return result.fetchall() if result.returns_rows else result.rowcount
        finally:
            tx.rollback()


def count(engine, auth_id, table, role="authenticated"):
    return run_as(engine, auth_id, f"SELECT count(*) FROM public.{table}", role=role)[0][0]


TABLES = ["client_companies", "contracts", "contract_addenda", "facility_objects", "disputed_conditions",
          "shift_schedules", "billing_acts", "subcontractors"]

EXPECTED = {
    "boss@test.local": [8, 8, 3, 81, 11, 12, 2, 3],
    "manager@test.local": [8, 8, 3, 81, 11, 12, 2, 3],
    "modena@test.local": [1, 1, 1, 24, 3, 2, 1, 1],
    "sportline@test.local": [1, 1, 0, 8, 2, 3, 0, 1],
    # facility_objects субподрядчику закрыта — объекты только через вью без цен (миграция 0003)
    "p23@test.local": [0, 0, 0, 0, 0, 6, 0, 1],
    "p24@test.local": [0, 0, 0, 0, 0, 5, 1, 1],
}


@pytest.mark.parametrize("email", list(EXPECTED))
def test_visibility_matrix(pg, email):
    engine, users = pg
    got = [count(engine, users[email].auth_user_id, t) for t in TABLES]
    assert dict(zip(TABLES, got)) == dict(zip(TABLES, EXPECTED[email]))


def test_client_sees_only_own_rows(pg):
    engine, users = pg
    uid = users["modena@test.local"].auth_user_id
    company = users["modena@test.local"].client_company_id
    rows = run_as(engine, uid, "SELECT DISTINCT client_company_id FROM public.facility_objects")
    assert rows == [(company,)]
    disputes = run_as(engine, uid, "SELECT id FROM public.disputed_conditions ORDER BY id")
    assert [r[0] for r in disputes] == ["Q-05", "Q-08", "Q-11"]
    files = {r[0] for r in run_as(engine, uid, "SELECT file FROM public.document_source_references")}
    assert files and all("Модена" in f or f.startswith("04_") for f in files)


VIEW = "public.subcontractor_facility_objects"


def test_subcontractor_sees_only_scheduled_objects(pg):
    engine, users = pg
    codes = run_as(engine, users["p23@test.local"].auth_user_id, f"SELECT code FROM {VIEW} ORDER BY code")
    assert [r[0] for r in codes] == ["kapri-02", "modena-01", "modena-02", "sportlain-01", "sportlain-03"]
    assert count(engine, users["p24@test.local"].auth_user_id, VIEW.split(".")[1]) == 4


def test_subcontractor_view_has_no_prices(pg):
    engine, users = pg
    with engine.connect() as c:
        cols = {r[0] for r in c.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'subcontractor_facility_objects'"
        ))}
    assert cols == {"id", "code", "city", "name", "area_m2", "external_area_m2", "facade_area_m2", "services", "subcontractor_id"}
    with pytest.raises(ProgrammingError, match="does not exist"):
        run_as(engine, users["p23@test.local"].auth_user_id, f"SELECT monthly_tariff FROM {VIEW}")
    # прямой запрос к таблице — пусто, обхода нет
    rows = run_as(engine, users["p23@test.local"].auth_user_id, "SELECT monthly_tariff FROM public.facility_objects")
    assert rows == []


def test_view_empty_for_other_roles(pg):
    engine, users = pg
    for email in ("boss@test.local", "modena@test.local"):
        assert count(engine, users[email].auth_user_id, "subcontractor_facility_objects") == 0
    assert count(engine, None, "subcontractor_facility_objects", role="anon") == 0


def test_anon_and_unknown_users_see_nothing(pg):
    engine, _ = pg
    assert count(engine, None, "facility_objects", role="anon") == 0
    assert count(engine, uuid.uuid4(), "facility_objects") == 0
    assert count(engine, uuid.uuid4(), "disputed_conditions") == 0


def _schedule_id(engine, code):
    with engine.connect() as c:
        return c.execute(text("SELECT s.id FROM shift_schedules s JOIN subcontractors x ON x.id = s.subcontractor_id WHERE x.code = :c ORDER BY s.id LIMIT 1"), {"c": code}).scalar()


INSERT_REPORT = (
    "INSERT INTO public.shift_reports (schedule_id, work_date, operator_code, status, reported_by_id) "
    "VALUES (:s, '2026-09-05', 'OP-1', 'done', :u)"
)


def test_subcontractor_writes_own_shift_reports_only(pg):
    engine, users = pg
    p23 = users["p23@test.local"]
    own, foreign = _schedule_id(engine, "P23"), _schedule_id(engine, "P24")
    assert run_as(engine, p23.auth_user_id, INSERT_REPORT, {"s": own, "u": p23.id}) == 1
    with pytest.raises(DBAPIError, match="row-level security"):
        run_as(engine, p23.auth_user_id, INSERT_REPORT, {"s": foreign, "u": p23.id})
    with pytest.raises(DBAPIError, match="row-level security"):  # чужой reported_by_id
        run_as(engine, p23.auth_user_id, INSERT_REPORT, {"s": own, "u": users["boss@test.local"].id})


def test_client_cannot_write(pg):
    engine, users = pg
    modena = users["modena@test.local"]
    with pytest.raises(DBAPIError, match="row-level security"):
        run_as(engine, modena.auth_user_id, INSERT_REPORT, {"s": _schedule_id(engine, "P23"), "u": modena.id})
    updated = run_as(engine, modena.auth_user_id, "UPDATE public.facility_objects SET monthly_tariff = 0")
    assert updated == 0
    assert run_as(engine, modena.auth_user_id, "DELETE FROM public.disputed_conditions") == 0


def test_manager_can_write(pg):
    engine, users = pg
    uid = users["manager@test.local"].auth_user_id
    assert run_as(engine, uid, "UPDATE public.disputed_conditions SET status = 'resolved' WHERE id = 'Q-11'") == 1


def test_users_table(pg):
    engine, users = pg
    modena = users["modena@test.local"]
    assert [r[0] for r in run_as(engine, modena.auth_user_id, "SELECT email FROM public.users")] == ["modena@test.local"]
    assert count(engine, users["manager@test.local"].auth_user_id, "users") == 6
    with pytest.raises(ProgrammingError, match="permission denied"):
        run_as(engine, users["boss@test.local"].auth_user_id, "SELECT password_hash FROM public.users")
    # менеджер не меняет пользователей, руководитель — может
    assert run_as(engine, users["manager@test.local"].auth_user_id, "UPDATE public.users SET role = 'manager' WHERE email = 'p23@test.local'") == 0
    assert run_as(engine, users["boss@test.local"].auth_user_id, "UPDATE public.users SET email = email WHERE email = 'p23@test.local'") == 1


def test_alembic_version_hidden(pg):
    engine, users = pg
    with pytest.raises(ProgrammingError, match="permission denied"):
        count(engine, users["boss@test.local"].auth_user_id, "alembic_version")
