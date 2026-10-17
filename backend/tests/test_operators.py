"""Пилот рейтинга операторов: баллы за смену, оценки клиента/менеджера, рейтинг квартала.

Формула (вариант 2, docs/OPERATOR_RATING_PROPOSAL.md):
  shift_base          = часы × вес статуса (done=1, partial=0.5) × OPERATOR_POINTS_PER_HOUR (10)
  rating_adjustment    = (средний балл 1–10 − 5) × OPERATOR_POINTS_PER_RATING_UNIT (20)
"""
import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import select

from app import models as m
from app.services import operator_rating as opr
from tests.conftest import login

AS_OF = "2026-10-16"


@pytest.fixture()
def p23_operator(db_session):
    p23 = db_session.scalar(select(m.Subcontractor).where(m.Subcontractor.code == "P23"))
    operator = m.Operator(code="OP-001", subcontractor_id=p23.id, display_name="Оператор А15")
    db_session.add(operator)
    db_session.commit()
    return operator


@pytest.fixture()
def operator_login(db_session, p23_operator):
    user = m.User(email="op001@test.local", role="operator", operator_id=p23_operator.id)
    from app.security import hash_password

    user.password_hash = hash_password("test-password-123")
    db_session.add(user)
    db_session.commit()
    return user


def _schedule_id(db, code="P23"):
    return db.scalar(
        select(m.ShiftSchedule.id)
        .join(m.Subcontractor)
        .where(m.Subcontractor.code == code)
        .order_by(m.ShiftSchedule.id)
        .limit(1)
    )


def _report(api, headers, db, operator_id, status="done", hours="5", work_date="2026-09-05", schedule_id=None):
    body = {
        "schedule_id": schedule_id or _schedule_id(db),
        "work_date": work_date,
        "operator_code": f"CODE-{operator_id}",  # уникальность smена+дата+код — код здесь произвольный ярлык
        "operator_id": operator_id,
        "status": status,
        "hours": hours,
    }
    r = api.post("/shift-reports", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ---------- модели данных ----------
def test_operator_role_requires_operator_id(db_session, p23_operator):
    user = m.User(email="bad@test.local", role="operator")
    db_session.add(user)
    with pytest.raises(Exception):
        db_session.commit()


def test_operator_code_unique(db_session, p23_operator):
    p23 = p23_operator.subcontractor_id
    db_session.add(m.Operator(code=p23_operator.code, subcontractor_id=p23))
    with pytest.raises(Exception):
        db_session.commit()


# ---------- формула баллов ----------
def test_shift_base_points_formula(db_session, p23_operator):
    done = m.ShiftReport(schedule_id=1, work_date=dt.date(2026, 9, 1), operator_code="x", status="done", hours=Decimal("5"))
    partial = m.ShiftReport(schedule_id=1, work_date=dt.date(2026, 9, 1), operator_code="x", status="partial", hours=Decimal("5"))
    missed = m.ShiftReport(schedule_id=1, work_date=dt.date(2026, 9, 1), operator_code="x", status="missed", hours=Decimal("5"))
    assert opr.shift_base_points(done) == 50  # 5ч × 1.0 × 10
    assert opr.shift_base_points(partial) == 25  # 5ч × 0.5 × 10
    assert opr.shift_base_points(missed) == 0


def test_rating_adjustment_points():
    class FakeRating:
        average = Decimal("10")

    assert opr.rating_adjustment_points(FakeRating()) == 100  # (10-5)×20
    FakeRating.average = Decimal("1")
    assert opr.rating_adjustment_points(FakeRating()) == -80  # (1-5)×20
    FakeRating.average = Decimal("5")
    assert opr.rating_adjustment_points(FakeRating()) == 0


def test_rating_needs_comment_threshold():
    assert opr.rating_needs_comment(10, 10, 10, 10) is False
    assert opr.rating_needs_comment(10, 10, 10, 5) is True  # один критерий ниже порога (6)
    assert opr.rating_needs_comment(6, 6, 6, 6) is False


@pytest.mark.parametrize("rank,total,expected", [(1, 10, 50000), (3, 10, 25000), (7, 10, 10000), (10, 10, 0), (1, 1, 50000)])
def test_bonus_tiers(rank, total, expected):
    assert opr.bonus_for_rank(rank, total) == Decimal(expected)


def test_quarter_bounds_covers_as_of():
    for d in [dt.date(2026, 1, 1), dt.date(2026, 4, 15), dt.date(2026, 9, 30), dt.date(2026, 12, 31)]:
        start, end = opr.quarter_bounds(d)
        assert start <= d <= end and start.month in (1, 4, 7, 10) and start.day == 1


# ---------- API: создание оператора, отметка смены начисляет баллы ----------
def test_create_operator_and_shift_grants_base_points(api, db_session):
    h = login(api, "manager@test.local")
    p23 = db_session.scalar(select(m.Subcontractor).where(m.Subcontractor.code == "P23"))
    r = api.post("/api/v1/operators", json={"code": "OP-900", "subcontractor_id": p23.id, "display_name": "Тест"}, headers=h)
    assert r.status_code == 201, r.text
    operator_id = r.json()["id"]
    assert api.post("/api/v1/operators", json={"code": "OP-900", "subcontractor_id": p23.id}, headers=h).status_code == 409

    report_id = _report(api, h, db_session, operator_id, status="done", hours="5")
    entries = db_session.scalars(select(m.OperatorPointsEntry).where(m.OperatorPointsEntry.operator_id == operator_id)).all()
    assert len(entries) == 1 and entries[0].points == 50 and entries[0].reason == "shift_base"

    # пропущенная смена баллов не даёт
    missed_id = _report(api, h, db_session, operator_id, status="missed", hours="5", work_date="2026-09-06")
    entries = db_session.scalars(select(m.OperatorPointsEntry).where(m.OperatorPointsEntry.operator_id == operator_id)).all()
    assert len(entries) == 1  # запись не добавилась


def test_operator_from_wrong_subcontractor_rejected(api, db_session):
    h = login(api, "manager@test.local")
    p24 = db_session.scalar(select(m.Subcontractor).where(m.Subcontractor.code == "P24"))
    other = m.Operator(code="OP-999", subcontractor_id=p24.id)
    db_session.add(other)
    db_session.commit()
    body = {
        "schedule_id": _schedule_id(db_session, "P23"),
        "work_date": "2026-09-05",
        "operator_code": "OP-999",
        "operator_id": other.id,
        "status": "done",
        "hours": "5",
    }
    r = api.post("/shift-reports", json=body, headers=h)
    assert r.status_code == 422


# ---------- оценка смены ----------
def test_rate_shift_requires_comment_on_low_score(api, db_session):
    h = login(api, "manager@test.local")
    p23 = db_session.scalar(select(m.Subcontractor).where(m.Subcontractor.code == "P23"))
    operator = db_session.scalar(select(m.Operator).where(m.Operator.code == "OP-900")) or m.Operator(code="OP-901", subcontractor_id=p23.id)
    db_session.add(operator)
    db_session.commit()
    report_id = _report(api, h, db_session, operator.id)

    low = {"cleanliness": 10, "quality": 10, "promptness": 10, "courtesy": 3}
    r = api.post(f"/api/v1/shift-reports/{report_id}/rating", json=low, headers=h)
    assert r.status_code == 422, r.text

    low["comment"] = "Оператор нагрубил администратору объекта"
    r = api.post(f"/api/v1/shift-reports/{report_id}/rating", json=low, headers=h)
    assert r.status_code == 201, r.text
    assert Decimal(r.json()["average"]) == Decimal("8.2")

    # повторно эту смену не оценить
    assert api.post(f"/api/v1/shift-reports/{report_id}/rating", json=low, headers=h).status_code == 409

    entries = db_session.scalars(
        select(m.OperatorPointsEntry).where(m.OperatorPointsEntry.operator_id == operator.id, m.OperatorPointsEntry.reason == "rating_adjustment")
    ).all()
    assert len(entries) == 1 and entries[0].points == round((Decimal("8.2") - 5) * 20)


def test_rate_shift_without_operator_rejected(api, db_session):
    h = login(api, "manager@test.local")
    schedule_id = _schedule_id(db_session)
    body = {"schedule_id": schedule_id, "work_date": "2026-09-05", "operator_code": "OP-002", "status": "done", "hours": "4"}
    report_id = api.post("/shift-reports", json=body, headers=h).json()["id"]
    r = api.post(f"/api/v1/shift-reports/{report_id}/rating", json={"cleanliness": 9, "quality": 9, "promptness": 9, "courtesy": 9}, headers=h)
    assert r.status_code == 422 and "operator_id" in r.json()["detail"]


def test_client_can_only_rate_own_object(api, db_session):
    p23 = db_session.scalar(select(m.Subcontractor).where(m.Subcontractor.code == "P23"))
    operator = m.Operator(code="OP-910", subcontractor_id=p23.id)
    db_session.add(operator)
    db_session.commit()
    manager = login(api, "manager@test.local")
    report_id = _report(api, manager, db_session, operator.id)  # объект Модены (modena-01)

    modena = login(api, "modena@test.local")
    good = {"cleanliness": 9, "quality": 9, "promptness": 9, "courtesy": 9}
    assert api.post(f"/api/v1/shift-reports/{report_id}/rating", json=good, headers=modena).status_code == 201

    operator2 = m.Operator(code="OP-911", subcontractor_id=p23.id)
    db_session.add(operator2)
    db_session.commit()
    sportline_schedule = db_session.scalar(
        select(m.ShiftSchedule.id)
        .join(m.FacilityObject)
        .join(m.Contract)
        .where(m.Contract.number == "SL-2023/114")
        .order_by(m.ShiftSchedule.id)
        .limit(1)
    )
    r2 = api.post(
        "/shift-reports",
        json={"schedule_id": sportline_schedule, "work_date": "2026-09-05", "operator_code": "OP-911", "operator_id": operator2.id, "status": "done", "hours": "3"},
        headers=manager,
    )
    assert r2.status_code == 201
    forbidden = api.post(f"/api/v1/shift-reports/{r2.json()['id']}/rating", json=good, headers=modena)
    assert forbidden.status_code == 403


def test_subcontractor_role_cannot_rate(api, db_session):
    p23 = db_session.scalar(select(m.Subcontractor).where(m.Subcontractor.code == "P23"))
    operator = m.Operator(code="OP-920", subcontractor_id=p23.id)
    db_session.add(operator)
    db_session.commit()
    manager = login(api, "manager@test.local")
    report_id = _report(api, manager, db_session, operator.id)
    p23_user = login(api, "p23@test.local")
    good = {"cleanliness": 9, "quality": 9, "promptness": 9, "courtesy": 9}
    assert api.post(f"/api/v1/shift-reports/{report_id}/rating", json=good, headers=p23_user).status_code == 403


# ---------- рейтинг и премия ----------
def test_ranking_orders_by_points_and_pays_bonus(api, db_session):
    h = login(api, "manager@test.local")
    p23 = db_session.scalar(select(m.Subcontractor).where(m.Subcontractor.code == "P23"))
    top = m.Operator(code="OP-A", subcontractor_id=p23.id)
    low = m.Operator(code="OP-B", subcontractor_id=p23.id)
    db_session.add_all([top, low])
    db_session.commit()

    r1 = _report(api, h, db_session, top.id, hours="10")  # 100 баллов
    api.post(f"/api/v1/shift-reports/{r1}/rating", json={"cleanliness": 10, "quality": 10, "promptness": 10, "courtesy": 10}, headers=h)
    r2 = _report(api, h, db_session, low.id, hours="1")  # 10 баллов, без оценки

    out = api.get("/api/v1/operators/ranking", params={"as_of": AS_OF}, headers=h)
    assert out.status_code == 200, out.text
    data = out.json()
    codes = [row["operator"]["code"] for row in data["rows"]]
    assert codes.index("OP-A") < codes.index("OP-B")
    top_row = next(row for row in data["rows"] if row["operator"]["code"] == "OP-A")
    assert top_row["points"] == 100 + 100  # 100 база + 100 за максимальную оценку
    assert top_row["rank"] == 1 and Decimal(top_row["bonus"]) == Decimal(50000)
    assert data["quarter_start"] == "2026-10-01" and data["quarter_end"] == "2026-12-31"


def test_ranking_staff_only(api):
    assert api.get("/api/v1/operators/ranking", headers=login(api, "modena@test.local")).status_code == 403
    assert api.get("/api/v1/operators/ranking", headers=login(api, "p23@test.local")).status_code == 403


# ---------- видимость роли operator ----------
def test_operator_sees_only_own_rows(api, db_session, p23_operator, operator_login):
    manager = login(api, "manager@test.local")
    report_id = _report(api, manager, db_session, p23_operator.id)
    api.post(f"/api/v1/shift-reports/{report_id}/rating", json={"cleanliness": 9, "quality": 9, "promptness": 9, "courtesy": 9}, headers=manager)

    other_sub = db_session.scalar(select(m.Subcontractor).where(m.Subcontractor.code == "P24"))
    other_op = m.Operator(code="OP-930", subcontractor_id=other_sub.id)
    db_session.add(other_op)
    db_session.commit()

    h = login(api, "op001@test.local")
    assert [o["id"] for o in api.get("/api/v1/operators", headers=h).json()] == [p23_operator.id]
    reports = api.get("/shift-reports", headers=h).json()
    assert {r["id"] for r in reports} == {report_id}
    assert api.get("/objects", headers=h).json() == []
    assert api.get("/api/v1/operators/ranking", headers=h).status_code == 403
