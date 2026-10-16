"""Сидинг из data/contracts.json."""
import copy
import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app import models as m
from app.services import contracts_v1 as v1
from app.services.importer import ImportBlocked, import_contracts
from tests.conftest import AS_OF


def _contract(db, number) -> m.Contract:
    return db.scalar(select(m.Contract).where(m.Contract.number == number))


def test_counts(db_session):
    s = db_session.summary
    assert (s.client_companies, s.contracts, s.facility_objects, s.disputed_conditions) == (8, 8, 81, 11)
    assert (s.addenda, s.subcontractors, s.shift_schedules) == (3, 3, 12)
    assert s.injection_flagged == []


def test_company_codes(db_session):
    codes = set(db_session.scalars(select(m.ClientCompany.code)))
    assert codes == {"modena", "lira", "venta", "sportlain", "kapri", "taimas", "zhuldyz", "medeu"}


def test_addenda(db_session):
    ds = {a.number: a for a in db_session.scalars(select(m.ContractAddendum))}
    assert set(ds) == {"ДС №24", "ДС №61", "ДС №1"}
    assert ds["ДС №24"].stated_monthly_total == Decimal("5571400")
    assert len(ds["ДС №24"].facility_objects) == 24
    assert (ds["ДС №61"].signed_at, ds["ДС №61"].effective_from) == (dt.date(2026, 8, 1), dt.date(2026, 8, 1))
    assert ds["ДС №1"].effective_from == dt.date(2026, 1, 1)
    assert any(s.note and "5 571 400" in s.note for s in ds["ДС №24"].sources)


def test_contract_status(db_session):
    got = {c.number: c.status for c in db_session.scalars(select(m.Contract))}
    assert got == {
        "MR-01/2020": "auto_renewed",
        "LR-ICL-2020/06": "auto_renewed",
        "ICL-048": "auto_renewed",
        "SL-2023/114": "expired",
        "KC-02/2024": "auto_renewed",
        "TP-0412/2024": "expiring",
        "ZB-2023-0457": "expired",
        "MD-001": "auto_renewed",
    }


def test_medeu_term_and_areas(db_session):
    md = _contract(db_session, "MD-001")
    assert (md.valid_from, md.valid_to) == (dt.date(2023, 10, 19), dt.date(2024, 10, 18))
    obj = md.facility_objects[0]
    assert (obj.area_m2, obj.external_area_m2, obj.facade_area_m2) == (21400, 28000, 16500)
    assert (obj.vat_basis, obj.vat_rate) == ("included", Decimal("12"))


def test_subcontractors_only_from_schedule(db_session):
    rows = dict(
        db_session.execute(
            select(m.Subcontractor.code, func.count(m.FacilityObject.id))
            .join(m.FacilityObject, m.FacilityObject.subcontractor_id == m.Subcontractor.id)
            .group_by(m.Subcontractor.code)
        ).all()
    )
    assert rows == {"P01": 1, "P23": 5, "P24": 4}


def test_schedules_parsed_from_services(db_session):
    sl = db_session.scalar(select(m.FacilityObject).where(m.FacilityObject.code == "sportlain-01"))
    shifts = sorted((s.operators_count, str(s.shift_start), str(s.shift_end), s.days_pattern) for s in sl.schedules)
    assert shifts == [(1, "07:30:00", "10:00:00", "ежедневно"), (1, "15:00:00", "17:00:00", "пт–вс")]
    assert all(s.period_month == dt.date(2026, 9, 1) for s in sl.schedules)
    assert sl.schedules[0].source.file == "04_Операторы_и_график_сентябрь.xlsx"
    # Медеу: назначен P01, но часов и числа ОПУ в договоре нет — не выдумываем.
    md = db_session.scalar(select(m.FacilityObject).where(m.FacilityObject.code == "medeu-01"))
    assert [(s.operators_count, s.shift_start) for s in md.schedules] == [(None, None)]


def test_disputes_linked_to_companies(db_session):
    got = {d.id: (d.client_company.code if d.client_company else None) for d in db_session.scalars(select(m.DisputedCondition))}
    assert got == {
        "Q-01": "sportlain", "Q-02": "zhuldyz", "Q-03": "kapri", "Q-04": "kapri", "Q-05": "modena", "Q-06": "lira",
        "Q-07": None, "Q-08": "modena", "Q-09": "medeu", "Q-10": "sportlain", "Q-11": "modena",
    }
    q10 = db_session.get(m.DisputedCondition, "Q-10")
    assert [(s.file, s.page) for s in q10.sources] == [("D_01_Договор_Спортлайн_SL-2023-114.pdf", 6)]


def test_sources_deduplicated(db_session):
    rows = db_session.execute(
        select(m.DocumentSourceReference.file, m.DocumentSourceReference.page, m.DocumentSourceReference.sheet,
               m.DocumentSourceReference.row, m.DocumentSourceReference.note)
    ).all()
    keys = [(r[0], r[1], r[2], r[3], r[4]) for r in rows]
    pages = db_session.scalars(select(m.DocumentSourceReference.pages)).all()
    assert len(set(zip(keys, map(lambda p: tuple(p or ()), pages)))) == len(keys)


def test_reimport_blocked_when_shift_reports_exist(db_session, raw):
    schedule = db_session.scalars(select(m.ShiftSchedule)).first()
    db_session.add(m.ShiftReport(schedule=schedule, work_date=dt.date(2026, 9, 1), operator_code="OP-1", status="done"))
    db_session.commit()
    with pytest.raises(ImportBlocked):
        import_contracts(db_session, copy.deepcopy(raw), as_of=AS_OF)
    db_session.rollback()
    summary = import_contracts(db_session, copy.deepcopy(raw), as_of=AS_OF, force=True)
    assert summary.facility_objects == 81
    assert db_session.scalar(select(func.count(m.ShiftReport.id))) == 0


def test_reimport_keeps_companies_and_users(db_session, raw):
    before = {c.code: c.id for c in db_session.scalars(select(m.ClientCompany))}
    import_contracts(db_session, copy.deepcopy(raw), as_of=AS_OF)
    after = {c.code: c.id for c in db_session.scalars(select(m.ClientCompany))}
    assert before == after
    assert db_session.scalar(select(func.count(m.User.id))) == 6


def test_parse_helpers():
    assert v1.parse_vat("без НДС; НДС сверх по ставке на дату оборота") == ("excluded", None)
    assert v1.parse_vat("с НДС 16%; базовая 203 тг/м² = 288 260") == ("included", Decimal("16"))
    assert v1.parse_vat("с НДС; базис ставки не уточнён") == ("included", None)
    assert v1.parse_renewal("в предоставленном тексте автоматическое продление не указано") == "none"
    assert v1.parse_renewal("продление только дополнительным соглашением") == "by_agreement"
    assert v1.parse_subcontractor("P23 ИП «Шанырак Клин»") == ("P23", "ИП «Шанырак Клин»")
    assert v1.client_code("АО «Жұлдыз Банк»") == "zhuldyz"
    assert v1.schedule_month("04_Операторы_и_график_сентябрь.xlsx", 2026) == dt.date(2026, 9, 1)
    assert v1.schedule_month("A_02_ДС24_Модена.pdf", 2026) is None
    shifts = v1.parse_shifts("2 ОПУ 08:00–16:00 и 2 ОПУ 16:00–00:00, график 5/2; по заявке: трактор")
    assert [(s.operators, str(s.start), str(s.end), s.days) for s in shifts] == [
        (2, "08:00:00", "16:00:00", "5/2"),
        (2, "16:00:00", "00:00:00", "5/2"),
    ]
