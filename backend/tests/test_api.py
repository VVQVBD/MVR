"""API: вход, роли и видимость строк (те же правила, что RLS)."""
from decimal import Decimal

from tests.conftest import login


def _ids(resp):
    assert resp.status_code == 200, resp.text
    return [x["id"] for x in resp.json()]


# ---------- вход ----------
def test_login_wrong_password(api):
    assert api.post("/auth/token", data={"username": "boss@test.local", "password": "nope"}).status_code == 401


def test_requires_token(api):
    assert api.get("/objects").status_code == 401


def test_me(api, as_p23):
    me = api.get("/auth/me", headers=as_p23).json()
    assert me["role"] == "subcontractor" and me["subcontractor_id"] is not None


# ---------- руководитель и менеджер: всё ----------
def test_staff_sees_everything(api, as_manager):
    assert len(_ids(api.get("/clients", headers=as_manager))) == 8
    assert len(_ids(api.get("/objects", headers=as_manager))) == 81
    assert len(_ids(api.get("/disputed-conditions", headers=as_manager))) == 11
    assert len(_ids(api.get("/schedules", headers=as_manager))) == 12


# ---------- клиент: только своя компания ----------
def test_client_sees_only_own_company(api, as_modena, db_session):
    modena_id = db_session.users["modena@test.local"].client_company_id
    assert _ids(api.get("/clients", headers=as_modena)) == [modena_id]
    objects = api.get("/objects", headers=as_modena).json()
    assert len(objects) == 24 and {o["client_company_id"] for o in objects} == {modena_id}
    assert sorted(_ids(api.get("/disputed-conditions", headers=as_modena))) == ["Q-05", "Q-08", "Q-11"]
    contracts = api.get("/contracts", headers=as_modena).json()
    assert [c["number"] for c in contracts] == ["MR-01/2020"]
    assert [a["number"] for a in contracts[0]["addenda"]] == ["ДС №24"]
    assert len(_ids(api.get("/schedules", headers=as_modena))) == 2
    assert [s["code"] for s in api.get("/subcontractors", headers=as_modena).json()] == ["P23"]


def test_client_cannot_open_foreign_rows(api, as_modena, db_session):
    other = db_session.users["sportline@test.local"].client_company_id
    assert api.get(f"/clients/{other}", headers=as_modena).status_code == 404
    assert api.get("/disputed-conditions/Q-01", headers=as_modena).status_code == 404
    assert api.get("/checks", headers=as_modena).status_code == 403


def test_client_cannot_write(api, as_modena):
    assert api.post("/clients", json={"code": "x", "name": "X"}, headers=as_modena).status_code == 403
    assert api.patch("/disputed-conditions/Q-11", json={"status": "resolved"}, headers=as_modena).status_code == 403


# ---------- субподрядчик: только объекты из графика ----------
def test_subcontractor_sees_only_assigned_objects(api, as_p23, as_p24):
    p23 = sorted(o["code"] for o in api.get("/objects", headers=as_p23).json())
    assert p23 == ["kapri-02", "modena-01", "modena-02", "sportlain-01", "sportlain-03"]
    p24 = sorted(o["code"] for o in api.get("/objects", headers=as_p24).json())
    assert p24 == ["lira-01", "lira-02", "venta-01", "venta-02"]
    assert api.get("/clients", headers=as_p23).json() == []
    assert api.get("/contracts", headers=as_p23).json() == []
    assert api.get("/disputed-conditions", headers=as_p23).json() == []
    assert [s["code"] for s in api.get("/subcontractors", headers=as_p23).json()] == ["P23"]
    assert len(api.get("/schedules", headers=as_p23).json()) == 6


PRICE_FIELDS = {"monthly_tariff", "price_per_m2", "vat_basis", "vat_rate", "vat_note", "pricing_group"}
LINK_FIELDS = {"client_company_id", "contract_id", "addendum_id"}


def test_subcontractor_gets_objects_without_prices(api, as_p23, as_manager):
    objects = api.get("/objects", headers=as_p23).json()
    assert objects and all(not (set(o) & (PRICE_FIELDS | LINK_FIELDS)) for o in objects)
    assert {"city", "name", "area_m2", "services"} <= set(objects[0])
    one = api.get(f"/objects/{objects[0]['id']}", headers=as_p23).json()
    assert not set(one) & PRICE_FIELDS
    # персоналу цены по-прежнему отдаются
    staff = api.get(f"/objects/{objects[0]['id']}", headers=as_manager).json()
    assert staff["monthly_tariff"] is not None and PRICE_FIELDS <= set(staff)


def test_subcontractor_reports_own_shift_only(api, as_p23, as_p24, as_modena):
    own = api.get("/schedules", headers=as_p23).json()[0]["id"]
    foreign = api.get("/schedules", headers=as_p24).json()[0]["id"]
    body = {"schedule_id": own, "work_date": "2026-09-05", "operator_code": "OP-17", "status": "done", "hours": "1.5"}
    r = api.post("/shift-reports", json=body, headers=as_p23)
    assert r.status_code == 201, r.text
    assert api.post("/shift-reports", json=body, headers=as_p23).status_code == 409  # дубль
    assert api.post("/shift-reports", json={**body, "schedule_id": foreign}, headers=as_p23).status_code == 404
    assert api.post("/shift-reports", json={**body, "work_date": "2026-10-01"}, headers=as_p23).status_code == 422
    assert api.post("/shift-reports", json=body, headers=as_modena).status_code == 403
    assert len(api.get("/shift-reports", headers=as_p23).json()) == 1
    assert api.get("/shift-reports", headers=as_p24).json() == []


# ---------- акты ----------
def test_billing_acts_visibility_and_totals(api, as_manager, as_modena, as_p23, as_p24, db_session):
    modena_id = db_session.users["modena@test.local"].client_company_id
    p24_id = db_session.users["p24@test.local"].subcontractor_id
    avr = {
        "kind": "client_avr", "period_month": "2026-09-01", "client_company_id": modena_id, "vat_rate": "16",
        "lines": [{"description": "Норд, сентябрь", "amount_net": "289800"}, {"description": "Самал Сити", "amount_net": "255300"}],
    }
    r = api.post("/billing-acts", json=avr, headers=as_manager)
    assert r.status_code == 201, r.text
    assert Decimal(r.json()["amount_net"]) == Decimal("545100")
    assert Decimal(r.json()["amount_gross"]) == Decimal("632316")
    act = {"kind": "subcontractor_act", "period_month": "2026-09-01", "subcontractor_id": p24_id, "lines": []}
    assert api.post("/billing-acts", json=act, headers=as_manager).status_code == 201
    bad = {**act, "subcontractor_id": None}
    assert api.post("/billing-acts", json=bad, headers=as_manager).status_code == 422

    assert [a["kind"] for a in api.get("/billing-acts", headers=as_modena).json()] == ["client_avr"]
    assert [a["kind"] for a in api.get("/billing-acts", headers=as_p24).json()] == ["subcontractor_act"]
    assert api.get("/billing-acts", headers=as_p23).json() == []


# ---------- запись персоналом ----------
def test_manager_crud_and_executive_only_delete(api, as_manager, as_boss):
    r = api.post("/clients", json={"code": "test", "name": "ТОО «Тест»", "bin": "123456789012"}, headers=as_manager)
    assert r.status_code == 201
    cid = r.json()["id"]
    assert api.post("/clients", json={"code": "test", "name": "дубль"}, headers=as_manager).status_code == 409
    assert api.post("/clients", json={"code": "t2", "name": "X", "bin": "123"}, headers=as_manager).status_code == 422
    assert api.patch(f"/clients/{cid}", json={"notes": "проверка"}, headers=as_manager).json()["notes"] == "проверка"
    assert api.delete(f"/clients/{cid}", headers=as_manager).status_code == 403
    assert api.delete(f"/clients/{cid}", headers=as_boss).status_code == 204


def test_dispute_resolution_records_who(api, as_manager, db_session):
    r = api.patch("/disputed-conditions/Q-11", json={"status": "resolved", "resolution": "Акт по сумме строк"}, headers=as_manager)
    assert r.status_code == 200 and r.json()["resolved_at"]


def test_only_executive_creates_users_and_imports(api, as_manager, as_boss, raw, db_session):
    body = {"email": "c@test.local", "password": "12345678", "role": "client"}
    assert api.post("/auth/users", json=body, headers=as_boss).status_code == 422  # нет компании
    body["client_company_id"] = db_session.users["modena@test.local"].client_company_id
    assert api.post("/auth/users", json=body, headers=as_manager).status_code == 403
    assert api.post("/auth/users", json=body, headers=as_boss).status_code == 201
    assert api.post("/import", json=raw, headers=as_manager).status_code == 403
    r = api.post("/import", json=raw, headers=as_boss)
    assert r.status_code == 200 and r.json()["facility_objects"] == 81
    assert api.post("/import", json={"clients": []}, headers=as_boss).status_code == 422


def test_checks_endpoint(api, as_manager):
    kinds = {(f["kind"], f["contract_number"]) for f in api.get("/checks", params={"as_of": "2026-10-16"}, headers=as_manager).json()}
    assert ("arithmetic", "MR-01/2020") in kinds and ("vat_rate", "MD-001") in kinds
