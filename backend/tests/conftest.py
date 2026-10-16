import copy
import datetime as dt
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app import models as m
from app.db import Base, get_db, make_engine
from app.main import app
from app.security import hash_password
from app.services.importer import import_contracts

DATA = Path(__file__).resolve().parents[2] / "data" / "contracts.json"
AS_OF = dt.date(2026, 10, 16)
PASSWORD = "test-password-123"

# (email, роль, код компании, код субподрядчика)
USERS = [
    ("boss@test.local", "executive", None, None),
    ("manager@test.local", "manager", None, None),
    ("modena@test.local", "client", "modena", None),
    ("sportline@test.local", "client", "sportlain", None),
    ("p23@test.local", "subcontractor", None, "P23"),
    ("p24@test.local", "subcontractor", None, "P24"),
]


@pytest.fixture(scope="session")
def raw():
    return json.loads(DATA.read_text(encoding="utf-8"))


def create_users(db, with_auth_ids=False):
    import uuid

    companies = {c.code: c.id for c in db.scalars(select(m.ClientCompany))}
    subs = {s.code: s.id for s in db.scalars(select(m.Subcontractor))}
    users = {}
    for email, role, company, sub in USERS:
        u = m.User(
            email=email,
            password_hash=hash_password(PASSWORD),
            role=role,
            client_company_id=companies.get(company),
            subcontractor_id=subs.get(sub),
            auth_user_id=uuid.uuid4() if with_auth_ids else None,
        )
        db.add(u)
        users[email] = u
    db.commit()
    return users


@pytest.fixture()
def db_session(tmp_path, raw):
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    session.summary = import_contracts(session, copy.deepcopy(raw), as_of=AS_OF)
    session.users = create_users(session)
    yield session
    session.close()
    engine.dispose()


@pytest.fixture()
def api(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def login(api, email):
    r = api.post("/auth/token", data={"username": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def as_boss(api):
    return login(api, "boss@test.local")


@pytest.fixture()
def as_manager(api):
    return login(api, "manager@test.local")


@pytest.fixture()
def as_modena(api):
    return login(api, "modena@test.local")


@pytest.fixture()
def as_p23(api):
    return login(api, "p23@test.local")


@pytest.fixture()
def as_p24(api):
    return login(api, "p24@test.local")
