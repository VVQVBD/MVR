"""Разбор полей пакета организаторов (contracts.json, schema_version 1.0).

Свободный текст (НДС, пролонгация, ставка за м², график ОПУ) разбирается правилами,
не моделью: если правило не уверено, значение остаётся пустым.
"""
import datetime as dt
import re
from decimal import Decimal
from typing import Any, Dict, List, NamedTuple, Optional, Tuple


_SUB_RE = re.compile(r"^\s*(P\d+)\s+(.+?)\s*$")
_RATE_RE = re.compile(r"(\d{1,2})\s*%")
_PER_M2_RE = re.compile(r"(\d[\d\s]*?)\s*тг/м²")
_TOTAL_RE = re.compile(r"total\s+([\d\s]+?)\s*KZT", re.IGNORECASE)
_TERM_YEARS_RE = re.compile(r"(\d+)\s*(год|года|лет)")
_ADDENDUM_FILE_RE = re.compile(r"ДС\s*(\d+)")
_ADDENDUM_SIGNED_RE = re.compile(r"[Дд]опсоглашени\w*\s*№\s*(\d+)\s*от\s*(\d{4}-\d{2}-\d{2})")
_ADDENDUM_EFFECTIVE_RE = re.compile(r"[Дд]опсоглашени\w*\s*№\s*(\d+)\s*меняет\s+цены\s+с\s*(\d{4}-\d{2}-\d{2})")
_TIME_RE = re.compile(r"(\d{1,2}:\d{2})\s*[–-]\s*(\d{1,2}:\d{2})")
_OPU_RE = re.compile(r"(\d+)\s*ОПУ")
_DAYS = [(re.compile(r"ежедневн", re.I), "ежедневно"), (re.compile(r"5/2"), "5/2"), (re.compile(r"пт\s*[–-]\s*вс"), "пт–вс")]
_MONTHS = {
    "январ": 1, "феврал": 2, "март": 3, "апрел": 4, "ма": 5, "июн": 6,
    "июл": 7, "август": 8, "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12,
}
_TRANSLIT = dict(
    zip(
        "абвгдеёжзийклмнопрстуфхцчшщъыьэюяәғқңөұүһі",
        ["a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "i", "k", "l", "m", "n", "o", "p", "r", "s", "t", "u",
         "f", "h", "ts", "ch", "sh", "sch", "", "y", "", "e", "yu", "ya", "a", "g", "k", "n", "o", "u", "u", "h", "i"],
    )
)

SCHEDULE_FILE_HINT = "график"


def is_v1(raw: Dict[str, Any]) -> bool:
    clients = raw.get("clients") or []
    return "schema_version" in raw and bool(clients) and "contract" in clients[0]


def date_or_none(value: Optional[str]) -> Optional[dt.date]:
    return dt.date.fromisoformat(value) if value else None


def add_years(d: dt.date, years: int) -> dt.date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:  # 29 февраля
        return d.replace(year=d.year + years, day=28)


def to_decimal(value: Any) -> Optional[Decimal]:
    if value is None:
        return None
    return Decimal(re.sub(r"\s", "", str(value)))


def client_code(name: str) -> str:
    """«ТОО «Модена Ритейл KZ»» → modena."""
    m = re.search(r"«([^»]+)»", name)
    word = (m.group(1) if m else name).split()[0].lower()
    return "".join(_TRANSLIT.get(ch, ch) for ch in word if ch.isalnum())


def parse_vat(text: Optional[str]) -> Tuple[str, Optional[Decimal]]:
    """(included | excluded | unknown, ставка %)."""
    if not text:
        return "unknown", None
    t = text.lower()
    if "без ндс" in t or "excluding vat" in t or "ндс сверх" in t:
        basis = "excluded"
    elif "с ндс" in t:
        basis = "included"
    else:
        basis = "unknown"
    m = _RATE_RE.search(text)
    return basis, (Decimal(m.group(1)) if m else None)


def parse_renewal(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    t = text.lower()
    if "автоматическ" in t and "не указан" not in t:
        return "auto_annual"
    if "соглашени" in t:
        return "by_agreement"
    if "не указан" in t or "не предусмотр" in t:
        return "none"
    return None


def parse_subcontractor(text: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    if not text:
        return None, None
    m = _SUB_RE.match(text)
    return (m.group(1), m.group(2)) if m else (None, text.strip())


def parse_stated_total(text: Optional[str]) -> Optional[Decimal]:
    m = _TOTAL_RE.search(text or "")
    return to_decimal(m.group(1)) if m else None


def price_per_m2(obj: Dict[str, Any], rules_by_group: Dict[str, Decimal]) -> Optional[Decimal]:
    group = obj.get("group")
    if group and group in rules_by_group:
        return rules_by_group[group]
    vat_text = obj.get("vat") or ""
    m = _PER_M2_RE.search(vat_text)
    # «базовая 203 тг/м² = 288 260, генуборка 52 200» — ставка покрывает только часть тарифа, не берём.
    if m and "=" not in vat_text:
        return to_decimal(m.group(1))
    return None


def term(validity: Dict[str, Any], contract_date: Optional[str]) -> Tuple[Optional[dt.date], Optional[dt.date]]:
    valid_from = date_or_none(validity.get("stated_from")) or date_or_none(contract_date)
    valid_to = date_or_none(validity.get("stated_until"))
    if valid_to is None and validity.get("initial_term") and valid_from:
        m = _TERM_YEARS_RE.search(validity["initial_term"])
        if m:
            valid_to = add_years(valid_from, int(m.group(1))) - dt.timedelta(days=1)
    return valid_from, valid_to


def addendum_number(file: str) -> Optional[str]:
    m = _ADDENDUM_FILE_RE.search(file)
    return f"ДС №{m.group(1)}" if m else None


def addendum_dates(number: str, status_note: Optional[str]) -> Tuple[Optional[dt.date], Optional[dt.date]]:
    """(signed_at, effective_from) из current_status, если там упомянут этот номер ДС."""
    n = number.split("№")[-1]
    signed = effective = None
    for m in _ADDENDUM_SIGNED_RE.finditer(status_note or ""):
        if m.group(1) == n:
            signed = date_or_none(m.group(2))
            if "с подписания" in (status_note or ""):
                effective = signed
    for m in _ADDENDUM_EFFECTIVE_RE.finditer(status_note or ""):
        if m.group(1) == n:
            effective = date_or_none(m.group(2))
    return signed, effective


def schedule_month(file: str, year: int) -> Optional[dt.date]:
    """«04_Операторы_и_график_сентябрь.xlsx» → 2026-09-01."""
    low = file.lower()
    if SCHEDULE_FILE_HINT not in low:
        return None
    tail = low.rsplit("_", 1)[-1]
    for stem, month in _MONTHS.items():
        if tail.startswith(stem):
            return dt.date(year, month, 1)
    return None


class Shift(NamedTuple):
    operators: Optional[int]
    start: Optional[dt.time]
    end: Optional[dt.time]
    days: Optional[str]
    text: str


def _days(text: str) -> Optional[str]:
    for rx, label in _DAYS:
        if rx.search(text):
            return label
    return None


def parse_shifts(services: Optional[str]) -> List[Shift]:
    """«1 ОПУ ежедневно 07:30–10:00, поддерживающая уборка 1 ОПУ пт–вс 15:00–17:00» → две смены."""
    if not services:
        return []
    shifts = []
    for segment in services.split(";"):
        prev = 0
        for m in _TIME_RE.finditer(segment):
            chunk = segment[prev : m.start()]
            opu = _OPU_RE.findall(chunk)
            shifts.append(
                Shift(
                    operators=int(opu[-1]) if opu else None,
                    start=dt.time.fromisoformat(m.group(1).zfill(5)),
                    end=dt.time.fromisoformat(m.group(2).zfill(5)),
                    days=_days(chunk) or _days(segment) or _days(services),
                    text=segment.strip(),
                )
            )
            prev = m.end()
    return shifts
