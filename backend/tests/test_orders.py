"""Разовые заявки на уборку (CleaningOrder): цена, назначение, фото, завершение, премия.

Этапы 2–3 docs/OPERATOR_RATING_PROPOSAL.md — новый слой поверх договоров, не замена им.
Ставки — пилотные значения из app/config.py: surface=150, standard=220, general=320 ₸/м².
"""
import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import select

from app import models as m
from app.services import orders as orders_svc
from tests.conftest import login

AS_OF = "2026-10-16"


@pytest.fixture()
def isolated_storage(tmp_path, monkeypatch):
    import app.routers.orders as orders_router

    monkeypatch.setattr(orders_router, "STORAGE_ROOT", tmp_path)
    return tmp_path


@pytest.fixture()
def p23_operator(db_session):
    p23 = db_session.scalar(select(m.Subcontractor).where(m.Subcontractor.code == "P23"))
    operator = m.Operator(code="OP-ORD-1", subcontractor_id=p23.id, active=True)
    db_session.add(operator)
    db_session.commit()
    return operator


@pytest.fixture()
def operator_login(db_session, p23_operator):
    from app.security import hash_password

    user = m.User(email="op-ord-1@test.local", role="operator", operator_id=p23_operator.id, password_hash=hash_password("test-password-123"))
    db_session.add(user)
    db_session.commit()
    return user


def _order_body(**overrides):
    body = {"city": "Алматы", "area_m2": "100", "quality": "standard", "team_mode": "duo"}
    body.update(overrides)
    return body


# ---------- цена и баллы ----------
def test_price_net_by_quality():
    assert orders_svc.price_net(Decimal("100"), "surface") == Decimal("15000.00")
    assert orders_svc.price_net(Decimal("100"), "standard") == Decimal("22000.00")
    assert orders_svc.price_net(Decimal("100"), "general") == Decimal("32000.00")


def test_order_base_points():
    order = m.CleaningOrder(area_m2=Decimal("200"), city="Алматы", quality="standard", team_mode="duo", price_net=Decimal(0), created_by_id=1)
    assert orders_svc.order_base_points(order) == 10  # 200 × 0.05


# ---------- создание заявки ----------
def test_manager_creates_order_with_computed_price(api, db_session):
    h = login(api, "manager@test.local")
    r = api.post("/api/v1/orders", json=_order_body(area_m2="50", quality="general"), headers=h)
    assert r.status_code == 201, r.text
    data = r.json()
    assert Decimal(data["price_net"]) == Decimal("16000.00")  # 50 × 320
    assert data["status"] == "new"


def test_custom_team_mode_requires_count(api):
    h = login(api, "manager@test.local")
    r = api.post("/api/v1/orders", json=_order_body(team_mode="custom"), headers=h)
    assert r.status_code == 422, r.text


def test_client_creates_order_for_own_company_only(api, db_session):
    modena = db_session.scalar(select(m.ClientCompany).where(m.ClientCompany.code == "modena"))
    sportline = db_session.scalar(select(m.ClientCompany).where(m.ClientCompany.code == "sportlain"))
    h = login(api, "modena@test.local")

    r = api.post("/api/v1/orders", json=_order_body(client_company_id=modena.id), headers=h)
    assert r.status_code == 201, r.text
    assert r.json()["client_company_id"] == modena.id

    r2 = api.post("/api/v1/orders", json=_order_body(client_company_id=sportline.id), headers=h)
    assert r2.status_code == 403


def test_subcontractor_cannot_create_order(api):
    h = login(api, "p23@test.local")
    assert api.post("/api/v1/orders", json=_order_body(), headers=h).status_code == 403


# ---------- видимость ----------
def test_client_sees_only_own_orders(api, db_session):
    modena = db_session.scalar(select(m.ClientCompany).where(m.ClientCompany.code == "modena"))
    manager = login(api, "manager@test.local")
    own = api.post("/api/v1/orders", json=_order_body(client_company_id=modena.id), headers=manager).json()
    api.post("/api/v1/orders", json=_order_body(), headers=manager)  # без клиента — не видна

    h = login(api, "modena@test.local")
    ids = {o["id"] for o in api.get("/api/v1/orders", headers=h).json()}
    assert ids == {own["id"]}


# ---------- назначение ----------
def test_manual_assign_changes_status(api, db_session, p23_operator):
    h = login(api, "manager@test.local")
    order = api.post("/api/v1/orders", json=_order_body(), headers=h).json()
    r = api.post(f"/api/v1/orders/{order['id']}/assign", json={"operator_id": p23_operator.id}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "assigned"
    assert r.json()["assigned_operator_id"] == p23_operator.id
    assert r.json()["assigned_by_auto_priority"] is False

    # повторно уже назначенную — 409
    assert api.post(f"/api/v1/orders/{order['id']}/assign", json={"operator_id": p23_operator.id}, headers=h).status_code == 409


def test_assign_requires_staff(api, p23_operator):
    manager = login(api, "manager@test.local")
    order = api.post("/api/v1/orders", json=_order_body(), headers=manager).json()
    p23 = login(api, "p23@test.local")
    r = api.post(f"/api/v1/orders/{order['id']}/assign", json={"operator_id": p23_operator.id}, headers=p23)
    assert r.status_code == 403


def test_auto_assign_picks_top_ranked_operator(api, db_session):
    h = login(api, "manager@test.local")
    p23 = db_session.scalar(select(m.Subcontractor).where(m.Subcontractor.code == "P23"))
    top = m.Operator(code="OP-TOP", subcontractor_id=p23.id, active=True)
    low = m.Operator(code="OP-LOW", subcontractor_id=p23.id, active=True)
    db_session.add_all([top, low])
    db_session.commit()
    db_session.add(m.OperatorPointsEntry(operator_id=top.id, points=100, reason="shift_base"))
    db_session.add(m.OperatorPointsEntry(operator_id=low.id, points=1, reason="shift_base"))
    db_session.commit()

    order = api.post("/api/v1/orders", json=_order_body(), headers=h).json()
    r = api.post(f"/api/v1/orders/{order['id']}/auto-assign", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["assigned_operator_id"] == top.id
    assert r.json()["assigned_by_auto_priority"] is True


def test_auto_assign_respects_preferred_city(api, db_session):
    h = login(api, "manager@test.local")
    p23 = db_session.scalar(select(m.Subcontractor).where(m.Subcontractor.code == "P23"))
    top = m.Operator(code="OP-TOP2", subcontractor_id=p23.id, active=True, preferred_city="Астана")
    second = m.Operator(code="OP-SECOND", subcontractor_id=p23.id, active=True)
    db_session.add_all([top, second])
    db_session.commit()
    db_session.add(m.OperatorPointsEntry(operator_id=top.id, points=100, reason="shift_base"))
    db_session.add(m.OperatorPointsEntry(operator_id=second.id, points=10, reason="shift_base"))
    db_session.commit()

    order = api.post("/api/v1/orders", json=_order_body(city="Алматы"), headers=h).json()
    r = api.post(f"/api/v1/orders/{order['id']}/auto-assign", headers=h)
    assert r.status_code == 200, r.text
    # top выбрал Астану, заявка в Алматы — должна достаться second, несмотря на меньший рейтинг
    assert r.json()["assigned_operator_id"] == second.id


def test_auto_assign_no_candidate(api, db_session):
    h = login(api, "manager@test.local")
    order = api.post("/api/v1/orders", json=_order_body(), headers=h).json()
    r = api.post(f"/api/v1/orders/{order['id']}/auto-assign", headers=h)
    assert r.status_code == 409


# ---------- завершение и баллы ----------
def test_complete_order_awards_points(api, db_session, p23_operator, operator_login):
    manager = login(api, "manager@test.local")
    order = api.post("/api/v1/orders", json=_order_body(area_m2="200"), headers=manager).json()
    api.post(f"/api/v1/orders/{order['id']}/assign", json={"operator_id": p23_operator.id}, headers=manager)

    other_op_header = login(api, "p23@test.local")
    assert api.post(f"/api/v1/orders/{order['id']}/complete", headers=other_op_header).status_code == 403

    h = login(api, "op-ord-1@test.local")
    r = api.post(f"/api/v1/orders/{order['id']}/complete", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "done"

    entries = db_session.scalars(
        select(m.OperatorPointsEntry).where(m.OperatorPointsEntry.operator_id == p23_operator.id, m.OperatorPointsEntry.reason == "order_base")
    ).all()
    assert len(entries) == 1 and entries[0].points == 10  # 200 × 0.05
    assert entries[0].order_id == order["id"]

    # повторно завершить уже готовую заявку нельзя
    assert api.post(f"/api/v1/orders/{order['id']}/complete", headers=h).status_code == 409


# ---------- фото ----------
def test_upload_photo_by_assigned_operator(api, db_session, p23_operator, operator_login, isolated_storage):
    manager = login(api, "manager@test.local")
    order = api.post("/api/v1/orders", json=_order_body(), headers=manager).json()
    api.post(f"/api/v1/orders/{order['id']}/assign", json={"operator_id": p23_operator.id}, headers=manager)

    h = login(api, "op-ord-1@test.local")
    r = api.post(
        f"/api/v1/orders/{order['id']}/photos",
        files={"file": ("after.jpg", b"\xff\xd8\xff\xe0fake", "image/jpeg")},
        headers=h,
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["ai_review_status"] == "not_evaluated"
    saved = isolated_storage / data["file_path"]
    assert saved.exists() and saved.read_bytes() == b"\xff\xd8\xff\xe0fake"

    photos = api.get(f"/api/v1/orders/{order['id']}/photos", headers=manager).json()
    assert len(photos) == 1 and photos[0]["id"] == data["id"]


def test_upload_photo_rejects_wrong_operator(api, db_session, p23_operator, operator_login, isolated_storage):
    manager = login(api, "manager@test.local")
    order = api.post("/api/v1/orders", json=_order_body(), headers=manager).json()
    api.post(f"/api/v1/orders/{order['id']}/assign", json={"operator_id": p23_operator.id}, headers=manager)

    other = login(api, "p24@test.local")
    r = api.post(
        f"/api/v1/orders/{order['id']}/photos",
        files={"file": ("after.jpg", b"fake", "image/jpeg")},
        headers=other,
    )
    assert r.status_code in (403, 404)


# ---------- премия: закрытие месяца/квартала ----------
def test_close_bonus_month_is_idempotent(api, db_session):
    h = login(api, "manager@test.local")
    p23 = db_session.scalar(select(m.Subcontractor).where(m.Subcontractor.code == "P23"))
    op = m.Operator(code="OP-BONUS", subcontractor_id=p23.id, active=True)
    db_session.add(op)
    db_session.commit()
    db_session.add(m.OperatorPointsEntry(operator_id=op.id, points=100, reason="shift_base"))
    db_session.commit()

    r1 = api.post("/api/v1/operators/bonus/close", json={"scope": "month", "as_of": AS_OF}, headers=h)
    assert r1.status_code == 200, r1.text
    row = next(x for x in r1.json() if x["operator_id"] == op.id)
    assert row["rank"] == 1 and Decimal(row["bonus_amount"]) == Decimal(50000)

    r2 = api.post("/api/v1/operators/bonus/close", json={"scope": "month", "as_of": AS_OF}, headers=h)
    assert r2.status_code == 200
    assert db_session.scalar(
        select(m.OperatorBonusRecord).where(m.OperatorBonusRecord.operator_id == op.id, m.OperatorBonusRecord.scope == "month")
    ) is not None
    count = len(
        db_session.scalars(
            select(m.OperatorBonusRecord).where(m.OperatorBonusRecord.operator_id == op.id, m.OperatorBonusRecord.scope == "month")
        ).all()
    )
    assert count == 1  # не задвоилось


def test_bonus_close_requires_staff(api):
    assert api.post("/api/v1/operators/bonus/close", json={"scope": "month"}, headers=login(api, "p23@test.local")).status_code == 403


def test_operator_sees_only_own_bonus(api, db_session, p23_operator, operator_login):
    manager = login(api, "manager@test.local")
    db_session.add(m.OperatorPointsEntry(operator_id=p23_operator.id, points=100, reason="shift_base"))
    db_session.commit()
    api.post("/api/v1/operators/bonus/close", json={"scope": "month", "as_of": AS_OF}, headers=manager)

    h = login(api, "op-ord-1@test.local")
    rows = api.get("/api/v1/operators/bonus", headers=h).json()
    assert {r["operator_id"] for r in rows} == {p23_operator.id}


# ---------- выбор района ----------
def test_top_operator_can_set_preferred_city(api, db_session):
    h = login(api, "manager@test.local")
    p23 = db_session.scalar(select(m.Subcontractor).where(m.Subcontractor.code == "P23"))
    top = m.Operator(code="OP-DISTRICT", subcontractor_id=p23.id, active=True)
    db_session.add(top)
    db_session.commit()
    from app.security import hash_password

    user = m.User(email="op-district@test.local", role="operator", operator_id=top.id, password_hash=hash_password("test-password-123"))
    db_session.add(user)
    db_session.add(m.OperatorPointsEntry(operator_id=top.id, points=500, reason="shift_base"))
    db_session.commit()

    oh = login(api, "op-district@test.local")
    r = api.patch(f"/api/v1/operators/{top.id}/preferred-city", json={"preferred_city": "Шымкент"}, headers=oh)
    assert r.status_code == 200, r.text
    assert r.json()["preferred_city"] == "Шымкент"


def test_low_ranked_operator_cannot_set_preferred_city(api, db_session):
    p23 = db_session.scalar(select(m.Subcontractor).where(m.Subcontractor.code == "P23"))
    top = m.Operator(code="OP-D-TOP", subcontractor_id=p23.id, active=True)
    low = m.Operator(code="OP-D-LOW", subcontractor_id=p23.id, active=True)
    db_session.add_all([top, low])
    db_session.commit()
    from app.security import hash_password

    user = m.User(email="op-d-low@test.local", role="operator", operator_id=low.id, password_hash=hash_password("test-password-123"))
    db_session.add(user)
    db_session.add(m.OperatorPointsEntry(operator_id=top.id, points=500, reason="shift_base"))
    db_session.add(m.OperatorPointsEntry(operator_id=low.id, points=1, reason="shift_base"))
    db_session.commit()

    oh = login(api, "op-d-low@test.local")
    r = api.patch(f"/api/v1/operators/{low.id}/preferred-city", json={"preferred_city": "Шымкент"}, headers=oh)
    assert r.status_code == 403


def test_staff_can_always_set_preferred_city(api, p23_operator):
    h = login(api, "manager@test.local")
    r = api.patch(f"/api/v1/operators/{p23_operator.id}/preferred-city", json={"preferred_city": "Караганда"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["preferred_city"] == "Караганда"
