"""Загрузка contracts.json (пакет организаторов, schema_version 1.0) в БД.

Полная перезагрузка справочных данных в одной транзакции. Компании, субподрядчики и пользователи
сохраняются (обновляются по коду). Графики смен пересоздаются из назначений в пакете, поэтому
если в базе уже есть отметки смен, импорт откажет — пока не передан force=True (тогда отметки удаляются,
а у актов обнуляются ссылки на договоры и объекты).
"""
import datetime as dt
import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app import models
from app.schemas import ImportSummary
from app.services import checks
from app.services import contracts_v1 as v1

SourceKey = Tuple[Any, ...]


def load_file(path: Union[str, Path]) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    if not v1.is_v1(raw):
        raise ValueError("Ожидается contracts.json пакета организаторов (schema_version 1.0)")
    return raw


class _Sources:
    """Дедупликация ссылок на источники: одна строка на (файл, страница/страницы, лист, строка, пояснение)."""

    def __init__(self, db: Session):
        self.db = db
        self.cache: Dict[SourceKey, models.DocumentSourceReference] = {}

    def get(self, src: Dict[str, Any]) -> models.DocumentSourceReference:
        pages = src.get("pages")
        key = (src["file"], src.get("page"), tuple(pages or ()), src.get("sheet"), src.get("row"), src.get("page_note"))
        if key not in self.cache:
            ref = models.DocumentSourceReference(
                file=src["file"],
                page=src.get("page"),
                pages=list(pages) if pages else None,
                sheet=src.get("sheet"),
                row=src.get("row"),
                note=src.get("page_note"),
            )
            self.db.add(ref)
            self.cache[key] = ref
        return self.cache[key]


def _wipe(db: Session) -> None:
    db.execute(update(models.BillingAct).values(source_id=None, contract_id=None))
    db.execute(update(models.BillingActLine).values(facility_object_id=None))
    for table in (
        models.dispute_sources,
        models.facility_sources,
        models.addendum_sources,
        models.contract_sources,
    ):
        db.execute(table.delete())
    for model in (
        models.ShiftReport,
        models.ShiftSchedule,
        models.DisputedCondition,
        models.FacilityObject,
        models.ContractAddendum,
        models.Contract,
    ):
        db.execute(delete(model))
    db.execute(delete(models.DocumentSourceReference))
    # Массовое удаление не чистит identity map; новые строки могут получить те же id.
    db.expunge_all()


def _common(values: List[Any]) -> Optional[Any]:
    distinct = set(values)
    return distinct.pop() if len(distinct) == 1 else None


class ImportBlocked(Exception):
    pass


def import_contracts(
    db: Session, raw: Dict[str, Any], as_of: Optional[dt.date] = None, force: bool = False
) -> ImportSummary:
    as_of = as_of or v1.date_or_none(raw.get("as_of")) or dt.date.today()
    reports = db.scalar(select(func.count(models.ShiftReport.id)))
    if reports and not force:
        raise ImportBlocked(f"В базе {reports} отметок смен; повторный импорт удалит их. Передайте force=True.")
    _wipe(db)
    sources = _Sources(db)

    companies = {c.code: c for c in db.scalars(select(models.ClientCompany))}
    subs = {s.code: s for s in db.scalars(select(models.Subcontractor))}
    seen_companies: Set[str] = set()
    file_owner: Dict[str, Set[str]] = {}
    counts = {"addenda": 0, "objects": 0, "schedules": 0}
    flagged: List[str] = []
    contracts: List[models.Contract] = []

    for c in raw["clients"]:
        code = v1.client_code(c["client"])
        company = companies.get(code)
        if company is None:
            company = models.ClientCompany(code=code, name=c["client"])
            db.add(company)
            companies[code] = company
        company.name = c["client"]
        seen_companies.add(code)

        validity = c.get("validity") or {}
        valid_from, valid_to = v1.term(validity, c.get("contract_date"))
        contract_vat_basis, contract_vat_rate = v1.parse_vat(c.get("vat"))
        terms = {k: c[k] for k in ("pricing_rules", "additional_tariffs") if k in c}
        terms["validity"] = validity
        contract = models.Contract(
            client_company=company,
            number=c["contract"],
            signed_at=v1.date_or_none(c.get("contract_date")),
            valid_from=valid_from,
            valid_to=valid_to,
            renewal=v1.parse_renewal(validity.get("renewal")),
            renewal_note=validity.get("renewal"),
            status_note=validity.get("current_status"),
            currency=raw.get("currency", "KZT"),
            vat_note=c.get("vat"),
            stated_monthly_total=v1.parse_stated_total(c.get("vat")),
            terms=terms,
            raw_text=c.get("raw_text"),
        )
        db.add(contract)
        contracts.append(contract)

        # ---- допсоглашения: по файлам-источникам «…ДС24…»
        addenda: Dict[str, models.ContractAddendum] = {}
        all_srcs = list(c.get("sources", [])) + [s for o in c.get("objects", []) for s in o.get("sources", [])]
        for src in all_srcs:
            file_owner.setdefault(src["file"], set()).add(code)
            number = v1.addendum_number(src["file"])
            if number and number not in addenda:
                signed, effective = v1.addendum_dates(number, validity.get("current_status"))
                addenda[number] = models.ContractAddendum(
                    contract=contract, number=number, signed_at=signed, effective_from=effective
                )
                counts["addenda"] += 1
        addendum_by_file = {
            src["file"]: addenda[v1.addendum_number(src["file"])]
            for src in all_srcs
            if v1.addendum_number(src["file"])
        }
        for src in c.get("sources", []):
            owner = addendum_by_file.get(src["file"])
            (owner.sources if owner else contract.sources).append(sources.get(src))

        stated = v1.to_decimal(c.get("monthly_total_stated_by_addendum"))
        if stated is not None:
            target = next(iter(addenda.values()), None)
            if target is not None and len(addenda) == 1:
                target.stated_monthly_total = stated
            else:
                contract.stated_monthly_total = stated

        # ---- объекты
        rules = {
            r["group"]: Decimal(str(r["monthly_price_per_m2"])) for r in c.get("pricing_rules", []) if r.get("group")
        }
        object_bases, object_rates = [], []
        for i, o in enumerate(c.get("objects", []), start=1):
            vat_text = o.get("vat") or c.get("vat")
            basis, rate = v1.parse_vat(vat_text)
            object_bases.append(basis)
            if rate is not None:
                object_rates.append(rate)
            sub_code, sub_name = v1.parse_subcontractor(o.get("subcontractor"))
            sub = None
            if sub_name:
                key = sub_code or sub_name
                sub = subs.get(key)
                if sub is None:
                    sub = models.Subcontractor(code=key, name=sub_name)
                    db.add(sub)
                    subs[key] = sub
            obj_addendum = next((addendum_by_file[s["file"]] for s in o.get("sources", []) if s["file"] in addendum_by_file), None)
            obj = models.FacilityObject(
                code=f"{code}-{i:02d}",
                client_company=company,
                contract=contract,
                addendum=obj_addendum,
                city=o["city"],
                name=o["object"],
                area_m2=v1.to_decimal(o.get("area_m2")),
                external_area_m2=v1.to_decimal(o.get("external_area_m2")),
                facade_area_m2=v1.to_decimal(o.get("facade_area_m2")),
                pricing_group=o.get("group"),
                services=o.get("services") or o.get("service"),
                monthly_tariff=v1.to_decimal(o.get("monthly_tariff")),
                price_per_m2=v1.price_per_m2(o, rules),
                vat_basis=basis,
                vat_rate=rate,
                vat_note=vat_text,
                subcontractor=sub,
            )
            for src in o.get("sources", []):
                obj.sources.append(sources.get(src))
            db.add(obj)
            counts["objects"] += 1

            # ---- график смен: только для объектов, назначенных в графике пакета
            schedule_src = next((s for s in o.get("sources", []) if v1.schedule_month(s["file"], as_of.year)), None)
            if sub is not None and schedule_src is not None:
                month = v1.schedule_month(schedule_src["file"], as_of.year)
                shifts = v1.parse_shifts(obj.services) or [v1.Shift(None, None, None, None, obj.services or "")]
                for sh in shifts:
                    db.add(
                        models.ShiftSchedule(
                            facility_object=obj,
                            subcontractor=sub,
                            period_month=month,
                            operators_count=sh.operators,
                            shift_start=sh.start,
                            shift_end=sh.end,
                            days_pattern=sh.days,
                            note=sh.text,
                            source=sources.get(schedule_src),
                        )
                    )
                    counts["schedules"] += 1

        # НДС договора: из текста договора, иначе общий для всех объектов.
        contract.vat_basis = contract_vat_basis if contract_vat_basis != "unknown" else (_common(object_bases) or "unknown")
        contract.vat_rate = contract_vat_rate or (object_rates[0] if object_rates else None)
        for add in addenda.values():
            linked = [b for b, o in zip(object_bases, c.get("objects", [])) if any(addendum_by_file.get(s["file"]) is add for s in o.get("sources", []))]
            add.vat_basis = _common(linked) or "unknown"
            add.vat_rate = contract.vat_rate
            add.summary = validity.get("current_status") if v1.addendum_dates(add.number, validity.get("current_status")) != (None, None) else None

    # ---- реестр спорных условий; клиент — по файлам, принадлежащим ровно одному договору
    disputes = 0
    for d in raw.get("disputed_conditions", []):
        owners: Set[str] = set()
        for s in d.get("sources", []):
            o = file_owner.get(s["file"], set())
            if len(o) == 1:
                owners |= o
        dispute = models.DisputedCondition(
            id=d["id"],
            client_company=companies[owners.pop()] if len(owners) == 1 else None,
            severity=d["severity"],
            topic=d["topic"],
            issue=d["issue"],
            ask=d.get("ask"),
            status="open",
        )
        for s in d.get("sources", []):
            dispute.sources.append(sources.get(s))
        db.add(dispute)
        disputes += 1

    db.flush()
    for contract in contracts:
        contract.status = checks.contract_status(contract, as_of)
        contract.status_as_of = as_of
        hits = checks.scan_contract_text(contract)
        contract.injection_flags = hits or None
        if hits:
            flagged.append(contract.number)

    db.commit()
    return ImportSummary(
        client_companies=len(seen_companies),
        contracts=len(contracts),
        addenda=counts["addenda"],
        facility_objects=counts["objects"],
        subcontractors=len(subs),
        shift_schedules=counts["schedules"],
        disputed_conditions=disputes,
        sources=len(sources.cache),
        injection_flagged=flagged,
    )
