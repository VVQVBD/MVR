"""Демо-вход по роли: работает только при DEMO_MODE=1."""
from sqlalchemy import select

from app.demo import DEMO_USERS
from app.models import ClientCompany, Subcontractor, User


def _demo_users(db):
    for role, (email, company, sub) in DEMO_USERS.items():
        db.add(User(
            email=email,
            role=role,
            client_company_id=db.scalar(select(ClientCompany.id).where(ClientCompany.code == company)) if company else None,
            subcontractor_id=db.scalar(select(Subcontractor.id).where(Subcontractor.code == sub)) if sub else None,
        ))
    db.commit()


def test_disabled_by_default(api, monkeypatch):
    monkeypatch.delenv("DEMO_MODE", raising=False)
    assert api.post("/auth/demo-token", json={"role": "executive"}).status_code == 404


def test_demo_roles_isolate_data(api, db_session, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "1")
    assert api.post("/auth/demo-token", json={"role": "client"}).status_code == 409  # ещё не созданы
    _demo_users(db_session)
    seen = {}
    for role in DEMO_USERS:
        r = api.post("/auth/demo-token", json={"role": role})
        assert r.status_code == 200, r.text
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        assert api.get("/auth/me", headers=h).json()["role"] == role
        seen[role] = len(api.get("/objects", headers=h).json())
    assert seen == {"executive": 81, "manager": 81, "client": 24, "subcontractor": 5}
    assert api.post("/auth/demo-token", json={"role": "admin"}).status_code == 422


def test_demo_users_cannot_login_with_password(api, db_session, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "1")
    _demo_users(db_session)
    r = api.post("/auth/token", data={"username": DEMO_USERS["executive"][0], "password": ""})
    assert r.status_code in (401, 422)
