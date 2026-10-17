"""Пилот рейтинга операторов — см. docs/OPERATOR_RATING_PROPOSAL.md.

Баллы лояльности — лента записей (`OperatorPointsEntry`), а не просто счётчик: каждую запись
можно проследить до смены и причины. Два источника баллов за смену:
  shift_base          — начисляется при отметке смены выполненной/частичной (объём работы);
  rating_adjustment    — начисляется при оценке этой смены клиентом/менеджером (вариант 2 из
                         предложения: (средний балл − 5) × коэффициент; может быть отрицательным).
Рейтинг и премия считаются за календарный квартал и не хранятся — это проекция ленты баллов,
такую же дату всегда можно пересчитать и объяснить.
"""
import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Optional

from app.config import settings
from app.models import Operator, OperatorPointsEntry, OperatorRating, ShiftReport

HOURS_WEIGHT = {"done": Decimal("1"), "partial": Decimal("0.5"), "missed": Decimal("0"), "replaced": Decimal("0")}


def shift_base_points(report: ShiftReport) -> int:
    """Баллы за объём работы по факту отметки смены. 0, если смену не отработали."""
    hours = report.hours or Decimal(0)
    weight = HOURS_WEIGHT.get(report.status, Decimal(0))
    return round(hours * weight * settings.operator_points_per_hour)


def rating_adjustment_points(rating: OperatorRating) -> int:
    """Надбавка или штраф за оценку: средний балл выше середины — плюс, ниже — минус."""
    return round((rating.average - 5) * settings.operator_points_per_rating_unit)


def rating_needs_comment(cleanliness: int, quality: int, promptness: int, courtesy: int) -> bool:
    low = settings.operator_rating_comment_threshold
    return min(cleanliness, quality, promptness, courtesy) < low


def quarter_bounds(as_of: dt.date) -> tuple[dt.date, dt.date]:
    """Календарный квартал (янв–мар, апр–июн, июл–сен, окт–дек), включая обе границы."""
    q_start_month = (as_of.month - 1) // 3 * 3 + 1
    start = dt.date(as_of.year, q_start_month, 1)
    end_month = q_start_month + 2
    end = dt.date(as_of.year, end_month + 1, 1) - dt.timedelta(days=1) if end_month < 12 else dt.date(as_of.year, 12, 31)
    return start, end


def bonus_for_rank(rank: int, total: int) -> Decimal:
    """Фиксированная премия по месту в рейтинге квартала — первый подходящий порог."""
    if total <= 0:
        return Decimal(0)
    # Доля участников строго впереди (0 для 1-го места) — так лидер получает верхнюю премию
    # даже если в квартале работал один оператор, а не делит 100% рейтинга сам с собой.
    share = Decimal(rank - 1) / Decimal(total)
    for threshold, amount in settings.operator_bonus_tiers:
        if share <= threshold:
            return amount
    return Decimal(0)


@dataclass
class RankingRow:
    operator: Operator
    points: int
    shifts_done: int
    rank: int
    bonus: Decimal


def build_ranking(operators: List[Operator], entries: List[OperatorPointsEntry]) -> List[RankingRow]:
    """Сворачивает ленту баллов в таблицу рейтинга, отсортированную по убыванию баллов."""
    totals: Dict[int, int] = {o.id: 0 for o in operators}
    shift_counts: Dict[int, set] = {o.id: set() for o in operators}
    for e in entries:
        if e.operator_id in totals:
            totals[e.operator_id] += e.points
            if e.reason == "shift_base" and e.shift_report_id is not None:
                shift_counts[e.operator_id].add(e.shift_report_id)

    ordered = sorted(operators, key=lambda o: (-totals[o.id], o.code))
    total = len(ordered)
    rows = []
    for i, op in enumerate(ordered, start=1):
        rows.append(
            RankingRow(
                operator=op,
                points=totals[op.id],
                shifts_done=len(shift_counts[op.id]),
                rank=i,
                bonus=bonus_for_rank(i, total),
            )
        )
    return rows
