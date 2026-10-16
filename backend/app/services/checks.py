"""Детерминированные проверки данных договоров.

Всё, что касается денег, считается кодом, а не моделью: сумма строк против итога,
qty × цена против суммы строки, срок действия, ставка НДС. Текст сканов только
проверяется на посторонние инструкции и никогда не меняет цифры.
"""
import datetime as dt
import re
from decimal import Decimal
from typing import Iterable, List, Optional, Tuple

from app.config import settings
from app.models import Contract, FacilityObject
from app.schemas import Finding

# ---------- промпт-инъекции ----------
_INJECTION_PATTERNS = [
    r"ignore (all |any )?(previous|prior|above) (instructions|rules)",
    r"disregard (the )?(previous|above|system)",
    r"you are (now )?(an? )?(ai|assistant|model|chatgpt|claude)",
    r"\b(system|assistant)\s*:",
    r"игнорир\w* (все |всех |любые )?(предыдущ|прошл|вышеуказ)\w*",
    r"забудь\w* (все |всё )?(инструкц|правил)\w*",
    r"(инструкци\w*|указани\w*|сообщени\w*) для (ии|ai|ассистент\w*|модел\w*|нейросет\w*|бота)",
    r"обнул\w* (все |всю |всех )?(цен\w*|стоимост\w*|тариф\w*|сумм\w*)",
    r"(установи\w*|постав\w*|считай\w*) (цен\w*|стоимост\w*|тариф\w*|сумм\w*)[^.\n]{0,40}(\b0(?![\d,.])|ноль|нулев\w*)",
    r"(цен\w*|стоимост\w*|тариф\w*|сумм\w*)[^.\n]{0,20}(=|равн\w*)\s*0(?![\d,.])",
    r"не (сообщай|показывай|упоминай)\w* (пользовател\w*|оператор\w*|проверяющ\w*)",
    r"(систем\w*|модул\w*|программ\w*) (автоматической )?обработки документов",
    r"выстав\w* (цен\w*|стоимост\w*|тариф\w*|сумм\w*)[^.\n]{0,20}(\b0(?![\d,.])|ноль|нулев\w*)",
]
_INJECTION_RE = [re.compile(p, re.IGNORECASE | re.UNICODE) for p in _INJECTION_PATTERNS]


def detect_injection(text: Optional[str]) -> List[str]:
    """Возвращает строки текста, похожие на инструкции для ИИ."""
    if not text:
        return []
    hits = []
    for line in text.splitlines():
        if any(rx.search(line) for rx in _INJECTION_RE):
            hits.append(line.strip())
    return hits


def sanitize_text(text: Optional[str]) -> Tuple[str, List[str]]:
    """Удаляет подозрительные строки. Возвращает (очищенный текст, удалённые строки)."""
    if not text:
        return "", []
    kept, removed = [], []
    for line in text.splitlines():
        if any(rx.search(line) for rx in _INJECTION_RE):
            removed.append(line.strip())
        else:
            kept.append(line)
    return "\n".join(kept), removed


# ---------- проверки ----------
_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _q(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


def _add_years(d: dt.date, years: int) -> dt.date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        return d.replace(year=d.year + years, day=28)


def _sum(objects: Iterable[FacilityObject]) -> Optional[Decimal]:
    amounts = [o.monthly_tariff for o in objects if o.monthly_tariff is not None]
    return _q(sum(amounts, Decimal("0"))) if amounts else None


def is_rounded_per_m2(amount: Decimal, expected: Decimal) -> bool:
    """Сумма = площадь × ставка за м², округлённое до 100 тг (допуск 50)."""
    step = settings.per_m2_rounding
    return amount % step == 0 and abs(amount - expected) <= step / 2


def check_arithmetic(contract: Contract, client_code: str) -> List[Finding]:
    findings: List[Finding] = []
    tol = settings.money_tolerance

    for i, o in enumerate(contract.facility_objects, start=1):
        if o.monthly_tariff is None or o.area_m2 is None or o.price_per_m2 is None:
            continue
        expected = _q(o.area_m2 * o.price_per_m2)
        if abs(expected - o.monthly_tariff) > tol and not is_rounded_per_m2(o.monthly_tariff, expected):
            findings.append(
                Finding(
                    kind="line_arithmetic",
                    severity="medium",
                    client_code=client_code,
                    contract_number=contract.number,
                    message=f"{o.city}, {o.name}: {o.area_m2} м² × {o.price_per_m2} = {expected}, в документе {o.monthly_tariff}",
                    expected=expected,
                    actual=o.monthly_tariff,
                    difference=_q(o.monthly_tariff - expected),
                )
            )

    totals = [(a.number, a.stated_monthly_total, a.facility_objects) for a in contract.addenda]
    totals.append((None, contract.stated_monthly_total, contract.facility_objects))
    for addendum_number, stated, objects in totals:
        rows = _sum(objects)
        if stated is None or rows is None or abs(rows - stated) <= tol:
            continue
        doc = f"{contract.number} {addendum_number}" if addendum_number else contract.number
        findings.append(
            Finding(
                kind="arithmetic",
                severity="high",
                client_code=client_code,
                contract_number=contract.number,
                message=(
                    f"{doc}: итог в документе {stated} KZT не совпадает с суммой {len(objects)} строк {rows} KZT. "
                    "До подтверждения не выставлять счёт по итогу."
                ),
                expected=rows,
                actual=stated,
                difference=_q(stated - rows),
            )
        )
    return findings


def current_term_end(contract: Contract, as_of: dt.date) -> Optional[dt.date]:
    """Конец текущего срока с учётом ежегодной автопролонгации; None — срок не указан."""
    end = contract.valid_to
    if end is None:
        return None
    if contract.renewal == "auto_annual":
        while end < as_of:
            end = _add_years(end, 1)
    return end


def contract_status(contract: Contract, as_of: dt.date) -> str:
    if contract.valid_to is None:
        return "unknown"
    if contract.valid_to < as_of:
        return "auto_renewed" if contract.renewal == "auto_annual" else "expired"
    if contract.renewal != "auto_annual" and (contract.valid_to - as_of).days <= settings.expiring_days:
        return "expiring"
    return "active"


def check_expired(contract: Contract, client_code: str, as_of: dt.date) -> List[Finding]:
    valid_to = contract.valid_to
    if valid_to is None:
        return []
    has_objects = bool(contract.facility_objects)
    status = contract_status(contract, as_of)

    if status == "expiring":
        days_left = (valid_to - as_of).days
        return [
            Finding(
                kind="expiring",
                severity="medium" if days_left <= 30 else "low",
                client_code=client_code,
                contract_number=contract.number,
                message=(
                    f"{contract.number}: срок истекает {valid_to.isoformat()} (через {days_left} дн.), "
                    "автопролонгации нет — нужно допсоглашение или новый договор."
                ),
            )
        ]
    if status == "auto_renewed":
        end = current_term_end(contract, as_of)
        return [
            Finding(
                kind="renewal_unconfirmed",
                severity="low",
                client_code=client_code,
                contract_number=contract.number,
                message=(
                    f"{contract.number}: исходный срок до {valid_to.isoformat()}, действует по автопролонгации "
                    f"(текущий период до {end.isoformat()}). Подтвердить, что уведомлений о расторжении не было."
                ),
            )
        ]
    if status == "expired":
        how = " Продление — только допсоглашением, в пакете его нет." if contract.renewal == "by_agreement" else ""
        note = " Объекты по нему всё ещё числятся в работе." if has_objects else ""
        return [
            Finding(
                kind="expired",
                severity="high" if has_objects else "medium",
                client_code=client_code,
                contract_number=contract.number,
                message=f"{contract.number}: срок действия истёк {valid_to.isoformat()} (на дату {as_of.isoformat()}).{how}{note}",
            )
        ]
    return []


def check_vat(contract: Contract, client_code: str, as_of: dt.date) -> List[Finding]:
    change = settings.vat_change_date
    new = settings.vat_new_rate
    end = current_term_end(contract, max(as_of, change))
    starts_after = contract.valid_from is not None and contract.valid_from >= change
    if not (starts_after or end is None or end >= change):
        return []

    rate = contract.vat_rate
    if rate is None:
        if contract.vat_basis != "included":
            return []
        return [
            Finding(
                kind="vat_unspecified",
                severity="medium",
                client_code=client_code,
                contract_number=contract.number,
                message=(
                    f"{contract.number}: цены указаны с НДС, ставка не выделена; с {change} ставка {new}%. "
                    "Уточнить, фиксирована ли сумма с НДС или база пересчитывается."
                ),
                expected=new,
            )
        ]
    if rate == new:
        return []

    detail = ""
    total = _sum(contract.facility_objects)
    if contract.vat_basis == "included" and total is not None:
        base = _q(total / (1 + rate / 100))
        detail = f" База без НДС {base}, при {new}% сумма с НДС {_q(base * (1 + new / 100))} вместо {total}."
    if starts_after:
        msg, severity = f"{contract.number}: НДС {rate}% в документе, действующем с {contract.valid_from}; с {change} ставка {new}%.", "critical"
    else:
        msg, severity = f"{contract.number}: НДС {rate}%, а договор действует после {change}; для этих периодов ставка {new}%.", "high"
    return [
        Finding(
            kind="vat_rate",
            severity=severity,
            client_code=client_code,
            contract_number=contract.number,
            message=msg + detail,
            expected=new,
            actual=rate,
        )
    ]


def scan_contract_text(contract: Contract) -> List[str]:
    """Свободный текст договора и ДС + текстовые поля, пришедшие из распознавания."""
    texts = [contract.raw_text, contract.vat_note, contract.renewal_note, contract.status_note]
    texts += [a.raw_text for a in contract.addenda]
    texts += [t for o in contract.facility_objects for t in (o.services, o.vat_note)]
    return detect_injection("\n".join(t for t in texts if t))


def check_injection(contract: Contract, client_code: str) -> List[Finding]:
    hits = contract.injection_flags or scan_contract_text(contract)
    return [
        Finding(
            kind="prompt_injection",
            severity="critical",
            client_code=client_code,
            contract_number=contract.number,
            message=f"{contract.number}: в тексте документа посторонняя инструкция, проигнорирована: «{h[:200]}»",
        )
        for h in hits
    ]


def run_all(contracts: Iterable[Contract], as_of: dt.date) -> List[Finding]:
    findings: List[Finding] = []
    for c in contracts:
        code = c.client_company.code
        findings += check_arithmetic(c, code)
        findings += check_expired(c, code, as_of)
        findings += check_vat(c, code, as_of)
        findings += check_injection(c, code)
    findings.sort(key=lambda f: (_ORDER[f.severity], f.client_code, f.contract_number or ""))
    return findings
