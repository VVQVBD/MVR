"""Смета нового объекта по методике 01_Смета_пример_Орда_Трейдинг.xlsx и нормам 09/07.

ФОТ операторов (+ генуборка, + платформа занятости gross-up)
+ материалы + гигиена + инвентарь + оборудование + спецодежда   = себестоимость
+ вознаграждение субподрядчика = себестоимость × 0,101 / 0,9
+ административные расходы     = (себестоимость + вознаграждение) × 0,01 / 0,99
                                = бюджет субподрядчика (столько IC Line платит субподрядчику)
+ маржа IC Line                 = бюджет × 15/85 (15 % цены без НДС)
                                = цена клиенту без НДС, + НДС = цена с НДС.

Количества: материалы — расход на 1000 м² × площадь × коэффициент сегмента; гигиена — на санузел;
инвентарь и спецодежда — на число ОПУ; оборудование — по правилу сегмента; ОПУ базовой уборки —
площадь ÷ производительность сегмента ÷ часы смены, с округлением вверх.
"""
import datetime as dt
import math
import re
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import List, Optional, Tuple

from app.services.norms import Norms, NormsError

# Знаменатели из листа «Финансовые параметры» 09_Нормы_для_сметы (колонка «Как применяется»).
FEE_DENOMINATOR = Decimal("0.9")

SECTIONS = ("payroll", "materials", "hygiene", "inventory", "equipment", "uniform")
SECTION_LABEL = {
    "payroll": "ФОТ операторов с расходами платформы",
    "materials": "Моющие средства и расходные материалы",
    "hygiene": "Расходные материалы гигиены",
    "inventory": "Инвентарь",
    "equipment": "Оборудование",
    "uniform": "Спецодежда",
}


class EstimateError(ValueError):
    pass


def q2(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def ceil_qty(v: Decimal) -> int:
    """Количество к закупке: вверх, но 6,00001 → 6 (как в примере сметы)."""
    return int(math.ceil(q2(v)))


@dataclass
class Line:
    section: str
    name: str
    unit: str
    qty: Decimal
    monthly_net: Decimal
    price_with_vat: Optional[Decimal] = None
    price_net: Optional[Decimal] = None
    period_months: int = 1
    note: str = ""


@dataclass
class Support:
    positions: int
    schedule: str


@dataclass
class EstimateResult:
    lines: List[Line]
    totals: dict
    cost: Decimal
    subcontractor_fee: Decimal
    subcontractor_admin: Decimal
    subcontractor_budget: Decimal
    ic_margin: Decimal
    price_net: Decimal
    vat_rate: Decimal
    vat: Decimal
    price_gross: Decimal
    operators: int
    base_positions: int
    budget_gross: Optional[Decimal] = None
    budget_gap: Optional[Decimal] = None
    margin_at_budget: Optional[Decimal] = None
    margin_at_budget_pct: Optional[Decimal] = None
    warnings: List[str] = field(default_factory=list)


_SUPPORT_RE = re.compile(r"(\d+)\s*[×xх*]\s*(.+)")


def parse_support(text: Optional[str]) -> List[Support]:
    """«1 × 5/2 полный день 9 ч; 1 × 5/2 день/вечер 4 ч» → [Support(1, …), Support(1, …)]."""
    out = []
    for part in (text or "").split(";"):
        part = part.strip()
        if not part:
            continue
        m = _SUPPORT_RE.match(part)
        if not m:
            raise EstimateError(f"Не понял поддерживающую уборку «{part}»: ожидается «N × график»")
        out.append(Support(int(m.group(1)), m.group(2).strip()))
    return out


def _schedule(norms: Norms, name: str):
    if name not in norms.schedules:
        raise EstimateError(f"Нет графика «{name}». Есть: {', '.join(norms.schedules)}")
    return norms.schedules[name]


def _qty_by_rule(rule: str, operators: int, area: Decimal) -> Optional[int]:
    """«1 на 3 ОПУ», «2 на объект», «1 шт. на каждое отделение», «1 на каждые 2000 м², с округлением вверх»."""
    r = rule.lower()
    m = re.match(r"(\d+)\s*(?:шт\.?)?\s*на\s*(\d+)\s*опу", r)
    if m:
        return int(m.group(1)) * math.ceil(operators / int(m.group(2)))
    m = re.match(r"(\d+)\s*(?:шт\.?)?\s*на\s*каждые\s*(\d+)\s*м²", r)
    if m:
        return int(m.group(1)) * math.ceil(area / Decimal(m.group(2)))
    m = re.match(r"(\d+)\s*(?:шт\.?)?\s*на\s*(?:объект|каждое отделение)", r)
    if m:
        return int(m.group(1))
    return None


def estimate(
    norms: Norms,
    *,
    city: str,
    segment: str,
    area_m2: Decimal,
    toilets: int,
    base_schedule: str,
    support: List[Support],
    hygiene: bool,
    general_cleaning: bool,
    budget_gross_month: Optional[Decimal] = None,
    vat_rate: Optional[Decimal] = None,
    as_of: Optional[dt.date] = None,
    ic_margin: Optional[Decimal] = None,
) -> EstimateResult:
    as_of = as_of or dt.date.today()
    if segment not in norms.productivity:
        raise EstimateError(f"Нет сегмента «{segment}». Есть: {', '.join(norms.productivity)}")
    if area_m2 <= 0:
        raise EstimateError("Площадь должна быть больше нуля")
    warnings: List[str] = list(norms.warnings)
    legal_vat = norms.vat_on(as_of)
    vat = legal_vat if vat_rate is None else vat_rate
    if vat != legal_vat:
        warnings.append(f"НДС {vat * 100:.0f}% не совпадает со ставкой на {as_of} ({legal_vat * 100:.0f}%) — расчёт для сравнения")
    margin_share = norms.ic_margin if ic_margin is None else ic_margin
    if margin_share < norms.min_ic_margin:
        warnings.append(f"Маржа {margin_share * 100:.1f}% ниже минимума {norms.min_ic_margin * 100:.0f}% — только с согласия директора")

    k_city = norms.city_k(city)
    if city not in norms.city_coef:
        warnings.append(f"«{city}»: коэффициент к ставкам ОПУ {k_city} (другие города)")
    lines: List[Line] = []

    # ---- ФОТ
    base = _schedule(norms, base_schedule)
    person_hours_per_day = area_m2 / norms.productivity[segment]
    base_positions = math.ceil(person_hours_per_day / base.hours_per_shift)
    base_people = Decimal(base_positions) * base.people_per_position
    lines.append(
        Line("payroll", f"ОПУ базовая уборка ({base.name})", "чел.", base_people, base_people * base.monthly_rate * k_city,
             price_net=base.monthly_rate * k_city,
             note=f"{area_m2} м² ÷ {norms.productivity[segment]} м²/ч·ч ÷ {base.hours_per_shift} ч = {base_positions} поз.")
    )
    people = base_people
    for s in support:
        sch = _schedule(norms, s.schedule)
        n = Decimal(s.positions) * sch.people_per_position
        people += n
        lines.append(Line("payroll", f"ОПУ поддержка ({sch.name})", "чел.", n, n * sch.monthly_rate * k_city, price_net=sch.monthly_rate * k_city))
    if general_cleaning:
        per_person = norms.general_cleaning_pay * norms.general_cleanings_per_year / 12
        lines.append(Line("payroll", "Генеральная уборка (ОПУ базовой уборки)", "чел.", base_people, base_people * per_person,
                          price_net=per_person, note=f"{norms.general_cleanings_per_year} раза в год"))
    fot = sum((l.monthly_net for l in lines if l.section == "payroll"), Decimal(0))
    lines.append(Line("payroll", "Расходы Платформы Занятости (gross-up)", "", Decimal(1),
                      fot * norms.platform / (1 - norms.platform), note=f"ФОТ × {norms.platform} / (1 − {norms.platform})"))
    operators = math.ceil(people)

    def item(section: str, name: str, unit: str, qty: int, price_vat: Decimal, life: int = 1, note: str = ""):
        net = price_vat / (1 + legal_vat)
        lines.append(Line(section, name, unit, Decimal(qty), Decimal(qty) * net / life, price_with_vat=price_vat,
                          price_net=net, period_months=life, note=note))

    # ---- материалы, гигиена
    coef = norms.material_coef[segment]
    for it in norms.materials:
        item("materials", it.name, it.unit, ceil_qty(it.qty_rule * area_m2 / 1000 * coef), it.price_with_vat)
    if hygiene:
        for it in norms.hygiene:
            item("hygiene", it.name, it.unit, ceil_qty(it.qty_rule * toilets), it.price_with_vat)

    # ---- инвентарь, оборудование
    for it in norms.inventory:
        qty = _qty_by_rule(it.rule, operators, area_m2)
        if qty is None:
            warnings.append(f"Инвентарь «{it.name}»: не понял правило «{it.rule}», не учтён")
            continue
        item("inventory", it.name, it.unit, qty, it.price_with_vat, it.life_months, it.rule)
    for eq in [e for e in norms.equipment if e.segment == segment]:
        qty = _qty_by_rule(eq.rule, operators, area_m2)
        if qty is None:
            warnings.append(f"Оборудование «{eq.name}»: не понял правило «{eq.rule}», не учтено")
            continue
        item("equipment", eq.name, "шт", qty, eq.price_with_vat, eq.life_months, eq.rule)

    # ---- спецодежда
    item("uniform", "Форма ОПУ (комплект)", "шт", int(operators * norms.uniform_sets_per_year), norms.uniform_price, 12)
    item("uniform", "Обувь рабочая", "пара", int(operators * norms.shoes_per_year), norms.shoes_price, 12)

    # ---- свод
    totals = {s: sum((l.monthly_net for l in lines if l.section == s), Decimal(0)) for s in SECTIONS}
    cost = sum(totals.values(), Decimal(0))
    fee = cost * norms.subcontractor_fee / FEE_DENOMINATOR
    admin = (cost + fee) * norms.subcontractor_admin / (1 - norms.subcontractor_admin)
    sub_budget = cost + fee + admin
    margin = sub_budget * margin_share / (1 - margin_share)
    price_net = sub_budget + margin
    vat_amount = price_net * vat
    price_gross = price_net + vat_amount

    result = EstimateResult(
        lines=lines,
        totals={k: q2(v) for k, v in totals.items()},
        cost=q2(cost),
        subcontractor_fee=q2(fee),
        subcontractor_admin=q2(admin),
        subcontractor_budget=q2(sub_budget),
        ic_margin=q2(margin),
        price_net=q2(price_net),
        vat_rate=vat,
        vat=q2(vat_amount),
        price_gross=q2(price_gross),
        operators=operators,
        base_positions=base_positions,
        warnings=warnings,
    )
    if budget_gross_month is not None:
        result.budget_gross = q2(budget_gross_month)
        result.budget_gap = q2(budget_gross_month - price_gross)
        if price_gross > budget_gross_month:
            net_at_budget = budget_gross_month / (1 + vat)
            result.margin_at_budget = q2(net_at_budget - sub_budget)
            result.margin_at_budget_pct = q2((net_at_budget - sub_budget) / net_at_budget * 100)
            if net_at_budget < sub_budget:
                warnings.append("Бюджет клиента не покрывает даже бюджет субподрядчика — объект убыточен")
            elif (net_at_budget - sub_budget) / net_at_budget < norms.min_ic_margin:
                warnings.append(
                    f"В бюджет клиента маржа {result.margin_at_budget_pct}% — ниже минимума "
                    f"{norms.min_ic_margin * 100:.0f}%, только с согласия директора"
                )
    return result
