"""Разовые заявки на уборку (CleaningOrder) — этапы 2–3 docs/OPERATOR_RATING_PROPOSAL.md.

Цена и баллы считаются от площади и уровня качества (пилотные ставки, см. app/config.py —
в пакете организаторов нет готового тарифа на разовые выезды). Автоназначение и выбор района —
проекция того же рейтинга, что строит GET /api/v1/operators/ranking (app/services/operator_rating.py):
никакой отдельной «очереди приоритета» не хранится, порядок всегда можно пересчитать и объяснить.
"""
import calendar
import datetime as dt
from decimal import Decimal
from typing import List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import CleaningOrder, Operator, OperatorBonusRecord, OperatorPointsEntry
from app.services import operator_rating as opr


def price_net(area_m2: Decimal, quality: str) -> Decimal:
    rate = settings.order_quality_rates[quality]
    return (area_m2 * rate).quantize(Decimal("0.01"))


def order_base_points(order: CleaningOrder) -> int:
    return round(order.area_m2 * settings.order_points_per_m2)


def month_bounds(as_of: dt.date) -> tuple[dt.date, dt.date]:
    last_day = calendar.monthrange(as_of.year, as_of.month)[1]
    return dt.date(as_of.year, as_of.month, 1), dt.date(as_of.year, as_of.month, last_day)


def ranking_as_of(db: Session, as_of: dt.date, active_only: bool = True) -> tuple[List[opr.RankingRow], dt.date, dt.date]:
    """Та же проекция ленты баллов, что в GET /operators/ranking — единая точка правды для рейтинга."""
    start, end = opr.quarter_bounds(as_of)
    op_query = select(Operator)
    if active_only:
        op_query = op_query.where(Operator.active.is_(True))
    operators = db.scalars(op_query).all()
    entries = (
        db.scalars(
            select(OperatorPointsEntry).where(
                OperatorPointsEntry.operator_id.in_([o.id for o in operators]),
                OperatorPointsEntry.created_at >= dt.datetime.combine(start, dt.time.min),
                OperatorPointsEntry.created_at <= dt.datetime.combine(end, dt.time.max),
            )
        ).all()
        if operators
        else []
    )
    return opr.build_ranking(operators, entries), start, end


def _free_operator_ids(db: Session) -> set:
    return set(
        db.scalars(
            select(CleaningOrder.assigned_operator_id).where(
                CleaningOrder.status.in_(("assigned", "in_progress")),
                CleaningOrder.assigned_operator_id.isnot(None),
            )
        ).all()
    )


def pick_operator_for_order(db: Session, order: CleaningOrder, as_of: Optional[dt.date] = None) -> Optional[Operator]:
    """Автоназначение по приоритету: среди активных операторов без незавершённой заявки,
    у кого район заявки совпадает с предпочитаемым (или район не выбран), берём верхнего по рейтингу квартала."""
    as_of = as_of or dt.date.today()
    rows, _, _ = ranking_as_of(db, as_of)
    busy_ids = _free_operator_ids(db)
    for row in rows:
        operator = row.operator
        if operator.id in busy_ids:
            continue
        if operator.preferred_city and operator.preferred_city != order.city:
            continue
        return operator
    return None


def pick_discount_operator_for_order(
    db: Session, order: CleaningOrder, as_of: Optional[dt.date] = None
) -> Optional[Operator]:
    """Для скидочной заявки (`ClientDiscount`): симметрично `pick_operator_for_order`, но берём
    самого нуждающегося — худшего свободного оператора в нижних `discount_operator_bottom_share`
    рейтинга квартала (та же граница, что у «топ-30% выбирает район», но снизу). Так заявка
    реально помогает поднять рейтинг тому, кому это нужнее всего, а не случайному аутсайдеру."""
    as_of = as_of or dt.date.today()
    rows, _, _ = ranking_as_of(db, as_of)
    total = len(rows)
    if total == 0:
        return None
    cutoff = max(1, round(total * settings.discount_operator_bottom_share))
    bottom_rows = sorted(rows, key=lambda r: -r.rank)[:cutoff]  # худшие места — в начале
    busy_ids = _free_operator_ids(db)
    for row in bottom_rows:
        operator = row.operator
        if operator.id in busy_ids:
            continue
        if operator.preferred_city and operator.preferred_city != order.city:
            continue
        return operator
    return None


def close_bonus_period(
    db: Session, scope: str, as_of: dt.date, closed_by_id: Optional[int]
) -> List[OperatorBonusRecord]:
    """Фиксирует снэпшот премии за месяц (по текущим баллам квартала) или за квартал (итог периода).
    Идемпотентно по (operator_id, scope, period_start) — повторный вызов за тот же период обновляет запись."""
    rows, q_start, q_end = ranking_as_of(db, as_of)
    period_start, period_end = month_bounds(as_of) if scope == "month" else (q_start, q_end)
    total = len(rows)
    records: List[OperatorBonusRecord] = []
    for row in rows:
        existing = db.scalar(
            select(OperatorBonusRecord).where(
                OperatorBonusRecord.operator_id == row.operator.id,
                OperatorBonusRecord.scope == scope,
                OperatorBonusRecord.period_start == period_start,
            )
        )
        if existing is None:
            existing = OperatorBonusRecord(
                operator_id=row.operator.id, scope=scope, period_start=period_start, period_end=period_end
            )
            db.add(existing)
        existing.period_end = period_end
        existing.points = row.points
        existing.rank = row.rank
        existing.total_operators = total
        existing.bonus_amount = row.bonus
        existing.closed_by_id = closed_by_id
        records.append(existing)
    return records
