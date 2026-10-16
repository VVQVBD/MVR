"""Акты субподрядчиков из 05_Факт_сентябрь_2026.xlsx."""
import datetime as dt
from decimal import Decimal

from sqlalchemy import func, select

from app import models as m
from app.services import actuals
from tests.conftest import ACTUALS, login


def test_import(db_session, with_acts):
    s = with_acts
    assert (s.acts, s.lines, s.matched) == (3, 10, 10)
    assert s.total_amount == Decimal("13192979")
    assert s.warnings == ["«Акт субподрядчика P24 сентябрь»: ИТОГО 1043456 ≠ сумма строк 1028456"]
    acts = {a.number: a for a in db_session.scalars(select(m.BillingAct))}
    assert set(acts) == {"P01-2026-09", "P23-2026-09", "P24-2026-09"}
    assert acts["P24-2026-09"].stated_total == Decimal("1043456")
    assert acts["P24-2026-09"].amount_net == Decimal("1028456")
    assert acts["P01-2026-09"].issued_at == dt.date(2026, 10, 2)
    assert acts["P01-2026-09"].source.sheet == "Акт субподрядчика P01 сентябрь"


def test_lines_matched_to_objects(db_session, with_acts):
    got = {}
    for line in db_session.scalars(select(m.BillingActLine)):
        got[db_session.get(m.FacilityObject, line.facility_object_id).code] = (line.hours, line.amount_net)
    assert got["modena-01"] == (Decimal("90"), Decimal("246330"))
    assert got["venta-01"] == (Decimal("123"), Decimal("249475"))  # «ТРЦ «Норд», магазин «Вента»»
    assert got["kapri-02"][1] == Decimal("68938")
    assert got["medeu-01"][1] == Decimal("11050000")
    assert len(got) == 10


def test_reimport_replaces(db_session, with_acts):
    actuals.import_actuals(db_session, ACTUALS, 2026)
    assert db_session.scalar(select(func.count(m.BillingAct.id))) == 3
    assert db_session.scalar(select(func.count(m.BillingActLine.id))) == 10


def test_every_act_is_85_percent_of_client_net_price(db_session, with_acts):
    objects = db_session.scalars(select(m.FacilityObject)).all()
    lines = db_session.scalars(select(m.BillingActLine)).all()
    assert actuals.check_acts(objects, lines, Decimal("0.15"), dt.date(2026, 9, 30)) == []
    # искажаем один акт — проверка ловит
    lines[0].amount_net += 5000
    assert [f.kind for f in actuals.check_acts(objects, lines, Decimal("0.15"), dt.date(2026, 9, 30))] == ["act_mismatch"]


def test_checks_endpoint_reports_act_total(api, with_acts):
    findings = api.get("/checks?as_of=2026-10-16", headers=login(api, "manager@test.local")).json()
    f = next(f for f in findings if f["contract_number"] == "P24-2026-09")
    assert f["kind"] == "arithmetic" and Decimal(f["difference"]) == Decimal("15000")
    assert not [f for f in findings if f["kind"] == "act_mismatch"]


def test_sportline_acts_after_expiry(api, db_session, with_acts):
    cid = db_session.scalar(select(m.Contract.id).where(m.Contract.number == "SL-2023/114"))
    a = api.post("/api/v1/contracts/audit-scan", json={"contract_id": cid, "as_of": "2026-10-16"}, headers=login(api, "manager@test.local")).json()
    w = next(f for f in a["findings"] if f["kind"] == "work_after_expiry")
    assert "1 актов" in w["message"] and "2026-09" in w["message"]
