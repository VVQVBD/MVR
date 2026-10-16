"""Фактические акты субподрядчиков из 05_Факт_сентябрь_2026.xlsx.

Листы «Акт субподрядчика Pxx <месяц>»: строки «Договор клиента | Объект | Основание | Часов | Сумма без НДС».
Каждая строка сопоставляется объекту по номеру договора, коду субподрядчика и названиям в «кавычках».
Повторный импорт того же месяца заменяет акты этого субподрядчика.
"""
import datetime as dt
import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import openpyxl
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app import models as m
from app.schemas import Finding
from app.services import checks, costing
from app.services.contracts_v1 import _MONTHS

ACT_SHEET = re.compile(r"^Акт субподрядчика\s+(P\d+)\s+(\S+)", re.IGNORECASE)
ISSUED = re.compile(r"выставлен.*?(\d{2}\.\d{2}\.\d{4})")
QUOTED = re.compile(r"«([^»]+)»")


@dataclass
class ActLine:
    row: int
    contract: str
    object_text: str
    basis: str
    hours: Optional[Decimal]
    amount: Decimal


@dataclass
class ParsedAct:
    sheet: str
    code: str
    period: dt.date
    lines: List[ActLine]
    stated_total: Optional[Decimal]
    issued_at: Optional[dt.date]
    note: str = ""


@dataclass
class ActualsSummary:
    acts: int
    lines: int
    matched: int
    total_amount: Decimal
    warnings: List[str] = field(default_factory=list)


def _month(word: str, year: int) -> Optional[dt.date]:
    low = word.lower()
    for stem, month in _MONTHS.items():
        if low.startswith(stem):
            return dt.date(year, month, 1)
    return None


def parse_workbook(path: Union[str, Path], year: int) -> Tuple[List[ParsedAct], List[str]]:
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    acts, warnings = [], []
    for ws in wb.worksheets:
        mt = ACT_SHEET.match(ws.title)
        if not mt:
            continue
        period = _month(mt.group(2), year)
        if period is None:
            warnings.append(f"«{ws.title}»: не понял месяц")
            continue
        act = ParsedAct(ws.title, mt.group(1).upper(), period, [], None, None)
        for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            cells = list(row) + [None] * 6
            num, contract, obj, basis, hours, amount = cells[:6]
            if isinstance(obj, str) and obj.strip().upper() == "ИТОГО":
                act.stated_total = Decimal(str(amount)) if amount is not None else None
            elif contract and amount is not None:
                act.lines.append(
                    ActLine(i, str(contract).strip(), str(obj or "").strip(), str(basis or ""),
                            Decimal(str(hours)) if hours is not None else None, Decimal(str(amount)))
                )
            elif isinstance(num, str) and "выставлен" in num:
                act.note = num
                mi = ISSUED.search(num)
                if mi:
                    act.issued_at = dt.datetime.strptime(mi.group(1), "%d.%m.%Y").date()
        lines_sum = sum((l.amount for l in act.lines), Decimal(0))
        if act.stated_total is not None and lines_sum != act.stated_total:
            warnings.append(f"«{ws.title}»: ИТОГО {act.stated_total} ≠ сумма строк {lines_sum}")
        acts.append(act)
    wb.close()
    return acts, warnings


def _match(line: ActLine, candidates: List[m.FacilityObject]) -> Optional[m.FacilityObject]:
    if len(candidates) == 1:
        return candidates[0]
    tokens = set(QUOTED.findall(line.object_text)) or {line.object_text}
    scored = [(sum(1 for t in tokens if t in c.name), c) for c in candidates]
    best = max((s for s, _ in scored), default=0)
    top = [c for s, c in scored if s == best]
    return top[0] if best > 0 and len(top) == 1 else None


def import_actuals(db: Session, path: Union[str, Path], year: int) -> ActualsSummary:
    acts, warnings = parse_workbook(path, year)
    file_name = Path(path).name
    subs = {s.code: s for s in db.scalars(select(m.Subcontractor))}
    objects = db.scalars(select(m.FacilityObject).options(selectinload(m.FacilityObject.contract))).all()
    lines_total = matched = 0
    total = Decimal(0)

    for act in acts:
        sub = subs.get(act.code)
        if sub is None:
            warnings.append(f"{act.code}: субподрядчика нет в базе — акт пропущен")
            continue
        old = select(m.BillingAct.id).where(
            m.BillingAct.kind == "subcontractor_act",
            m.BillingAct.subcontractor_id == sub.id,
            m.BillingAct.period_month == act.period,
        )
        # строки — явно: в SQLite внешние ключи не каскадируются
        db.execute(delete(m.BillingActLine).where(m.BillingActLine.act_id.in_(old)))
        db.execute(delete(m.BillingAct).where(m.BillingAct.id.in_(old)))
        source = m.DocumentSourceReference(file=file_name, sheet=act.sheet, note=act.note or None)
        record = m.BillingAct(
            kind="subcontractor_act",
            number=f"{act.code}-{act.period:%Y-%m}",
            period_month=act.period,
            subcontractor_id=sub.id,
            status="issued",
            issued_at=act.issued_at,
            stated_total=act.stated_total,
            vat_rate=None,  # «ИП не является плательщиком НДС»
            source=source,
        )
        for line in act.lines:
            candidates = [o for o in objects if o.contract.number == line.contract and o.subcontractor_id == sub.id]
            obj = _match(line, candidates)
            if obj is None:
                warnings.append(f"{act.code}, строка {line.row}: «{line.object_text}» по {line.contract} не сопоставлен объекту")
            else:
                matched += 1
            record.lines.append(
                m.BillingActLine(
                    facility_object_id=obj.id if obj else None,
                    description=f"{line.contract}: {line.object_text}",
                    hours=line.hours,
                    amount_net=line.amount,
                    note=f"{line.basis}; строка {line.row}",
                )
            )
            lines_total += 1
            total += line.amount
        record.amount_net = sum((l.amount_net for l in record.lines), Decimal(0))
        record.amount_gross = record.amount_net
        db.add(record)
    db.commit()
    return ActualsSummary(len(acts), lines_total, matched, total, warnings)


# ---------- проверка актов ----------
def check_act_totals(acts: List[m.BillingAct]) -> List[Finding]:
    """ИТОГО в акте против суммы строк — как ДС №24 Модены, только на стороне субподрядчика."""
    findings = []
    for a in acts:
        rows = sum((l.amount_net for l in a.lines), Decimal(0))
        if a.stated_total is not None and a.stated_total != rows:
            findings.append(
                Finding(
                    kind="arithmetic",
                    severity="high",
                    client_code=a.subcontractor.code if a.subcontractor else "",
                    contract_number=a.number,
                    message=(
                        f"Акт {a.number}: ИТОГО {a.stated_total} ₸ ≠ сумма строк {rows} ₸. "
                        "Оплачивать по строкам, итог вернуть субподрядчику на исправление."
                    ),
                    expected=rows,
                    actual=a.stated_total,
                    difference=a.stated_total - rows,
                )
            )
    return findings


def check_acts(db_objects: List[m.FacilityObject], act_lines: List[m.BillingActLine], ic_margin: Decimal, as_of: dt.date) -> List[Finding]:
    """Акт субподрядчика должен быть равен цене клиента без НДС × (1 − маржа IC)."""
    by_id = {o.id: o for o in db_objects}
    findings = []
    for line in act_lines:
        o = by_id.get(line.facility_object_id)
        if o is None or o.monthly_tariff is None:
            continue
        net, _ = costing.net_tariff(o.monthly_tariff, o.vat_basis, o.vat_rate, as_of)
        if net is None:
            continue
        expected = net * (1 - ic_margin)
        if abs(expected - line.amount_net) > 1:
            findings.append(
                Finding(
                    kind="act_mismatch",
                    severity="medium",
                    client_code=o.client_company.code if o.client_company else "",
                    contract_number=o.contract.number,
                    message=(
                        f"{o.name}: акт {line.amount_net} ₸, а при цене без НДС {costing.money(net)} "
                        f"и марже {ic_margin * 100:.0f}% ожидалось {costing.money(expected)}"
                    ),
                    expected=costing.money(expected),
                    actual=line.amount_net,
                    difference=costing.money(line.amount_net - expected),
                )
            )
    return findings
