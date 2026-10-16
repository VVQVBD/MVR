"""Денежные вспомогательные функции: тариф без НДС, тип помещения, группы городов, рыночный ориентир.

Смета нового объекта — в services/estimate.py (нормативы пакета 07 и 09).
"""
import datetime as dt
import statistics
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, Iterable, List, NamedTuple, Optional, Tuple

from app.config import settings

KZT = Decimal("1")

PREMISE_LABEL = {
    "retail": "магазин / бутик",
    "office": "офис",
    "warehouse": "склад",
    "production": "производство",
    "bank_branch": "отделение / филиал банка",
    "mall_common": "общие зоны ТРЦ",
}

# Сегменты из 09_Нормы_для_сметы → тип помещения действующих объектов (для сравнения с портфелем)
SEGMENT_PREMISE = {
    "Офисы и бизнес-центры": "office",
    "Банки и финансовые организации": "bank_branch",
    "Торговая недвижимость: сетевой ретейл": "retail",
    "Торговая недвижимость: ТРЦ": "mall_common",
    "Склады и e-commerce": "warehouse",
    "Производство и промышленность": "production",
}


def money(v: Decimal) -> Decimal:
    return v.quantize(KZT, rounding=ROUND_HALF_UP)


def rate(v: Decimal) -> Decimal:
    """₸ за м² — с копейками."""
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def legal_vat_rate(on: dt.date) -> Decimal:
    return settings.vat_new_rate if on >= settings.vat_change_date else settings.vat_old_rate


def net_tariff(
    tariff: Decimal, vat_basis: str, vat_rate: Optional[Decimal], as_of: dt.date
) -> Tuple[Optional[Decimal], Optional[str]]:
    """Тариф без НДС. Возвращает (сумма, допущение) или (None, причина)."""
    if vat_basis == "excluded":
        return tariff, None
    if vat_basis == "included":
        if vat_rate is not None:
            return tariff / (1 + vat_rate / 100), None
        r = legal_vat_rate(as_of)
        return tariff / (1 + r / 100), f"ставка НДС не указана, выделена по закону {r}%"
    return None, "базис НДС не определён"


_PREMISE_KEYWORDS: List[Tuple[str, Tuple[str, ...]]] = [
    ("mall_common", ("общие зоны",)),
    ("warehouse", ("склад",)),
    ("production", ("фабрика", "цех", "производств")),
    ("bank_branch", ("отделение", "филиал")),
    ("office", ("офис",)),
    ("retail", ("магазин", "бутик")),
]


def premise_type(name: str) -> Optional[str]:
    low = name.lower()
    for kind, words in _PREMISE_KEYWORDS:
        if any(w in low for w in words):
            return kind
    return None


def city_groups(objects: Iterable) -> Dict[str, str]:
    """Группы городов I/II/III — из договора, где они заданы (Жұлдыз Банк). Других источников групп нет."""
    out: Dict[str, str] = {}
    for o in objects:
        if o.pricing_group:
            out.setdefault(o.city, o.pricing_group)
    return out


class Benchmark(NamedTuple):
    scope: str
    n: int
    per_m2_median: Decimal
    per_m2_min: Decimal
    per_m2_max: Decimal
    object_codes: List[str]


def benchmark(objects: List, premise: str, city: str, groups: Dict[str, str], as_of: dt.date) -> Optional[Benchmark]:
    """Тариф без НДС за м² у похожих действующих объектов: тот же тип в городе → в группе → по стране."""

    def per_m2(o) -> Optional[Decimal]:
        if o.monthly_tariff is None or not o.area_m2:
            return None
        net, _ = net_tariff(o.monthly_tariff, o.vat_basis, o.vat_rate, as_of)
        return None if net is None else net / o.area_m2

    same_type = [(o, per_m2(o)) for o in objects if premise_type(o.name) == premise]
    same_type = [(o, v) for o, v in same_type if v is not None]
    group = groups.get(city)
    scopes = [
        (f"{PREMISE_LABEL[premise]}, {city}", [x for x in same_type if x[0].city == city]),
        (f"{PREMISE_LABEL[premise]}, группа {group}", [x for x in same_type if group and groups.get(x[0].city) == group]),
        (f"{PREMISE_LABEL[premise]}, все города", same_type),
    ]
    for scope, rows in scopes:
        if len(rows) >= 3:
            values = [v for _, v in rows]
            return Benchmark(
                scope=scope,
                n=len(rows),
                per_m2_median=rate(Decimal(statistics.median(values))),
                per_m2_min=rate(min(values)),
                per_m2_max=rate(max(values)),
                object_codes=sorted(o.code for o, _ in rows),
            )
    return None


class VatPrice(NamedTuple):
    net: Decimal
    vat_rate: Decimal  # %
    vat: Decimal
    gross: Decimal


class VatTransition(NamedTuple):
    """Цена услуги в месяце `on` с учётом ставки НДС на эту дату."""

    keep_net: VatPrice  # база без НДС сохраняется, НДС начисляется по новой ставке
    keep_gross: Optional[VatPrice]  # сумма с НДС фиксирована в договоре (только для «с НДС»)
    note: str


def _price(net: Decimal, rate_pct: Decimal) -> VatPrice:
    vat = net * rate_pct / 100
    return VatPrice(rate(net), rate_pct, rate(vat), rate(net + vat))


def price_on(tariff: Decimal, vat_basis: str, contract_vat_rate: Optional[Decimal], on: dt.date) -> VatTransition:
    """Пересчёт ежемесячной цены на дату `on` (12 % до 31.12.2025, 16 % с 01.01.2026).

    «без НДС / НДС сверх»: база не меняется, меняется только НДС сверху.
    «с НДС»: база = тариф ÷ (1 + ставка договора); дальше два прочтения — сохранить базу
    (сумма к оплате растёт) или сохранить сумму с НДС (база падает). Какое верно — вопрос к клиенту (Q-04, Q-06, Q-09).
    """
    legal = legal_vat_rate(on)
    if vat_basis == "excluded":
        return VatTransition(_price(tariff, legal), None, "НДС сверх тарифа по ставке на дату оборота")
    if vat_basis == "included":
        base_rate = contract_vat_rate if contract_vat_rate is not None else legal
        net = tariff / (1 + base_rate / 100)
        keep_gross = _price(tariff / (1 + legal / 100), legal)
        note = (
            f"база выделена по ставке договора {base_rate}%"
            if contract_vat_rate is not None
            else f"ставка в договоре не указана, база выделена по закону {legal}%"
        )
        return VatTransition(_price(net, legal), keep_gross, note)
    raise ValueError("Базис НДС не определён — пересчёт невозможен")
