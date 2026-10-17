"""Скидка клиенту за честную низкую оценку заявки — см. docs/OPERATOR_RATING_PROPOSAL.md.

Низкая оценка (требует обязательного комментария — тот же порог, что у оценки смены) выдаёт
клиенту скидку. Потратить её можно только на заявку, назначенную оператору из нижних 30%
рейтинга квартала: оператор получает шанс поднять рейтинг, клиент — более низкую цену.
"""
from decimal import Decimal

import pytest
from sqlalchemy import select

from app import models as m
from app.services import discounts as discounts_svc
from tests.conftest import login

AS_OF = "2026-10-16"
GOOD = {"cleanliness": 9, "quality": 9, "promptness": 9, "courtesy": 9}
BAD = {"cleanliness": 2, "quality": 2, "promptness": 2, "courtesy": 2, "comment": "Оператор не приехал вовремя, качество низкое"}


@pytest.fixture()
def p23_operator(db_session):
    p23 = db_session.scalar(select(m.Subcontractor).where(m.Subcontractor.code == "P23"))
    operator = m.Operator(code="OP-DISC", subcontractor_id=p23.id, active=True)
    db_session.add(operator)
    db_session.commit()
    return operator


def _order_body(**overrides):
    body = {"city": "Алматы", "area_m2": "100", "quality": "standard", "team_mode": "duo"}
    body.update(overrides)
    return body


def _dummy_rating(db, operator_id, rated_by_id=1):
    """ClientDiscount.source_rating_id не может быть пустым — для тестов, где сама скидка не
    через API, нужна хоть какая-то реальная оценка, на которую она ссылается."""
    order = m.CleaningOrder(
        created_by_id=rated_by_id, city="Алматы", area_m2=Decimal("10"), quality="standard",
        team_mode="duo", price_net=Decimal("2200.00"), status="done", assigned_operator_id=operator_id,
    )
    db.add(order)
    db.commit()
    rating = m.OperatorRating(
        order_id=order.id, operator_id=operator_id, rated_by_id=rated_by_id,
        cleanliness=2, quality=2, promptness=2, courtesy=2, average=Decimal("2.0"),
        comment="тестовая низкая оценка",
    )
    db.add(rating)
    db.commit()
    return rating


def _done_order(api, db, manager_headers, operator_id, client_company_id=None):
    body = _order_body()
    if client_company_id is not None:
        body["client_company_id"] = client_company_id
    order = api.post("/api/v1/orders", json=body, headers=manager_headers).json()
    api.post(f"/api/v1/orders/{order['id']}/assign", json={"operator_id": operator_id}, headers=manager_headers)
    r = api.post(f"/api/v1/orders/{order['id']}/complete", headers=manager_headers)
    assert r.status_code == 200, r.text
    return r.json()


# ---------- формула / сервис ----------
def test_apply_to_order_reduces_price_and_marks_used():
    discount = m.ClientDiscount(client_company_id=1, pct=Decimal("15"), status="available")
    order = m.CleaningOrder(price_net=Decimal("22000.00"), city="Алматы", area_m2=Decimal("100"), quality="standard", team_mode="duo", created_by_id=1)
    discounts_svc.apply_to_order(discount, order)
    assert order.price_before_discount == Decimal("22000.00")
    assert order.price_net == Decimal("18700.00")  # 22000 × 0.85
    assert discount.status == "used" and discount.used_at is not None


def test_grant_requires_client_company_and_low_score():
    low = m.OperatorRating(operator_id=1, rated_by_id=1, cleanliness=2, quality=2, promptness=2, courtesy=2, average=Decimal("2"))
    high = m.OperatorRating(operator_id=1, rated_by_id=1, cleanliness=9, quality=9, promptness=9, courtesy=9, average=Decimal("9"))
    assert discounts_svc.grant_if_low_rating(low, None) is None  # нет клиента — некому начислить
    assert discounts_svc.grant_if_low_rating(high, 1) is None  # оценка не низкая
    granted = discounts_svc.grant_if_low_rating(low, 1)
    assert granted is not None and granted.client_company_id == 1 and granted.status == "available"


# ---------- API: оценка заявки выдаёт скидку ----------
def test_low_rating_on_order_grants_discount(api, db_session, p23_operator):
    manager = login(api, "manager@test.local")
    modena = db_session.scalar(select(m.ClientCompany).where(m.ClientCompany.code == "modena"))
    order = _done_order(api, db_session, manager, p23_operator.id, client_company_id=modena.id)

    client_h = login(api, "modena@test.local")
    r = api.post(f"/api/v1/orders/{order['id']}/rating", json=BAD, headers=client_h)
    assert r.status_code == 201, r.text

    discounts = db_session.scalars(select(m.ClientDiscount).where(m.ClientDiscount.client_company_id == modena.id)).all()
    assert len(discounts) == 1
    assert discounts[0].status == "available" and discounts[0].pct == Decimal("15.00")

    entries = db_session.scalars(
        select(m.OperatorPointsEntry).where(m.OperatorPointsEntry.operator_id == p23_operator.id, m.OperatorPointsEntry.reason == "rating_adjustment")
    ).all()
    assert len(entries) == 1 and entries[0].points < 0  # низкая оценка — штраф баллов


def test_high_rating_on_order_grants_no_discount(api, db_session, p23_operator):
    manager = login(api, "manager@test.local")
    modena = db_session.scalar(select(m.ClientCompany).where(m.ClientCompany.code == "modena"))
    order = _done_order(api, db_session, manager, p23_operator.id, client_company_id=modena.id)

    client_h = login(api, "modena@test.local")
    r = api.post(f"/api/v1/orders/{order['id']}/rating", json=GOOD, headers=client_h)
    assert r.status_code == 201, r.text
    assert db_session.scalars(select(m.ClientDiscount).where(m.ClientDiscount.client_company_id == modena.id)).all() == []


def test_order_without_client_grants_no_discount_even_on_low_score(api, db_session, p23_operator):
    manager = login(api, "manager@test.local")
    order = _done_order(api, db_session, manager, p23_operator.id, client_company_id=None)
    r = api.post(f"/api/v1/orders/{order['id']}/rating", json=BAD, headers=manager)
    assert r.status_code == 201, r.text
    assert db_session.scalars(select(m.ClientDiscount)).all() == []


def test_cannot_rate_order_twice(api, db_session, p23_operator):
    manager = login(api, "manager@test.local")
    modena = db_session.scalar(select(m.ClientCompany).where(m.ClientCompany.code == "modena"))
    order = _done_order(api, db_session, manager, p23_operator.id, client_company_id=modena.id)
    client_h = login(api, "modena@test.local")
    assert api.post(f"/api/v1/orders/{order['id']}/rating", json=GOOD, headers=client_h).status_code == 201
    assert api.post(f"/api/v1/orders/{order['id']}/rating", json=GOOD, headers=client_h).status_code == 409


def test_cannot_rate_order_before_done(api, db_session, p23_operator):
    manager = login(api, "manager@test.local")
    order = api.post("/api/v1/orders", json=_order_body(), headers=manager).json()
    r = api.post(f"/api/v1/orders/{order['id']}/rating", json=GOOD, headers=manager)
    assert r.status_code == 422


def test_other_client_cannot_rate_order(api, db_session, p23_operator):
    manager = login(api, "manager@test.local")
    modena = db_session.scalar(select(m.ClientCompany).where(m.ClientCompany.code == "modena"))
    order = _done_order(api, db_session, manager, p23_operator.id, client_company_id=modena.id)
    sportline_h = login(api, "sportline@test.local")
    assert api.post(f"/api/v1/orders/{order['id']}/rating", json=GOOD, headers=sportline_h).status_code == 403


def test_subcontractor_cannot_rate_order(api, db_session, p23_operator):
    manager = login(api, "manager@test.local")
    modena = db_session.scalar(select(m.ClientCompany).where(m.ClientCompany.code == "modena"))
    order = _done_order(api, db_session, manager, p23_operator.id, client_company_id=modena.id)
    p23_h = login(api, "p23@test.local")
    assert api.post(f"/api/v1/orders/{order['id']}/rating", json=GOOD, headers=p23_h).status_code == 403


def test_rating_requires_comment_below_threshold(api, db_session, p23_operator):
    manager = login(api, "manager@test.local")
    modena = db_session.scalar(select(m.ClientCompany).where(m.ClientCompany.code == "modena"))
    order = _done_order(api, db_session, manager, p23_operator.id, client_company_id=modena.id)
    client_h = login(api, "modena@test.local")
    without_comment = {k: v for k, v in BAD.items() if k != "comment"}
    r = api.post(f"/api/v1/orders/{order['id']}/rating", json=without_comment, headers=client_h)
    assert r.status_code == 422


# ---------- тратим скидку: заявка нижним 30% рейтинга ----------
def test_redeem_discount_assigns_bottom_ranked_operator_and_cuts_price(api, db_session):
    manager = login(api, "manager@test.local")
    p23 = db_session.scalar(select(m.Subcontractor).where(m.Subcontractor.code == "P23"))
    modena = db_session.scalar(select(m.ClientCompany).where(m.ClientCompany.code == "modena"))

    top = m.Operator(code="OP-TOP-D", subcontractor_id=p23.id, active=True)
    bottom = m.Operator(code="OP-BOTTOM-D", subcontractor_id=p23.id, active=True)
    db_session.add_all([top, bottom])
    db_session.commit()
    db_session.add(m.OperatorPointsEntry(operator_id=top.id, points=500, reason="shift_base"))
    db_session.add(m.OperatorPointsEntry(operator_id=bottom.id, points=1, reason="shift_base"))
    db_session.commit()
    rating = _dummy_rating(db_session, bottom.id)
    db_session.add(
        m.ClientDiscount(client_company_id=modena.id, pct=Decimal("15"), status="available", source_rating_id=rating.id)
    )
    db_session.commit()

    order = api.post(
        "/api/v1/orders", json=_order_body(client_company_id=modena.id), headers=manager
    ).json()
    r = api.post(f"/api/v1/orders/{order['id']}/auto-assign", params={"redeem_discount": True}, headers=manager)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["assigned_operator_id"] == bottom.id  # худший, не лучший
    assert Decimal(data["price_before_discount"]) == Decimal("22000.00")
    assert Decimal(data["price_net"]) == Decimal("18700.00")

    discount = db_session.scalar(select(m.ClientDiscount).where(m.ClientDiscount.client_company_id == modena.id))
    assert discount.status == "used" and discount.used_on_order_id == order["id"]


def test_redeem_discount_without_available_credit(api, db_session):
    manager = login(api, "manager@test.local")
    modena = db_session.scalar(select(m.ClientCompany).where(m.ClientCompany.code == "modena"))
    order = api.post("/api/v1/orders", json=_order_body(client_company_id=modena.id), headers=manager).json()
    r = api.post(f"/api/v1/orders/{order['id']}/auto-assign", params={"redeem_discount": True}, headers=manager)
    assert r.status_code == 409


def test_redeem_discount_requires_client_on_order(api, db_session):
    manager = login(api, "manager@test.local")
    order = api.post("/api/v1/orders", json=_order_body(), headers=manager).json()
    r = api.post(f"/api/v1/orders/{order['id']}/auto-assign", params={"redeem_discount": True}, headers=manager)
    assert r.status_code == 422


# ---------- видимость ----------
def test_client_sees_only_own_discounts(api, db_session, p23_operator):
    modena = db_session.scalar(select(m.ClientCompany).where(m.ClientCompany.code == "modena"))
    sportline = db_session.scalar(select(m.ClientCompany).where(m.ClientCompany.code == "sportlain"))
    rating1 = _dummy_rating(db_session, p23_operator.id)
    rating2 = _dummy_rating(db_session, p23_operator.id)
    db_session.add_all([
        m.ClientDiscount(client_company_id=modena.id, pct=Decimal("15"), status="available", source_rating_id=rating1.id),
        m.ClientDiscount(client_company_id=sportline.id, pct=Decimal("15"), status="available", source_rating_id=rating2.id),
    ])
    db_session.commit()

    h = login(api, "modena@test.local")
    rows = api.get("/api/v1/discounts", headers=h).json()
    assert len(rows) == 1 and rows[0]["client_company_id"] == modena.id

    staff_rows = api.get("/api/v1/discounts", headers=login(api, "manager@test.local")).json()
    assert len(staff_rows) == 2
