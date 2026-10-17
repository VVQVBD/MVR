"""Пилот рейтинга операторов: карточка оператора, оценка смены 1–10, лента баллов, рейтинг квартала.

См. docs/OPERATOR_RATING_PROPOSAL.md. Баллы начисляются в двух местах:
  shift_base          — при отметке смены выполненной/частичной (POST /shift-reports, operations.py);
  rating_adjustment    — здесь, при оценке этой смены.
"""
import datetime as dt
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app import access
from app import models as m
from app.db import get_db
from app.schemas_v1 import (
    OperatorCreate,
    OperatorOut,
    OperatorRankingOut,
    OperatorRankingRow,
    OperatorRatingCreate,
    OperatorRatingOut,
)
from app.security import any_user, require_roles, staff
from app.services import operator_rating as opr

router = APIRouter(prefix="/api/v1", tags=["operators"])
can_rate = require_roles("executive", "manager", "client")


def _commit(db: Session):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, detail="Нарушение уникальности или ссылки")


@router.get("/operators", response_model=List[OperatorOut])
def list_operators(
    subcontractor_id: Optional[int] = None, user: m.User = Depends(any_user), db: Session = Depends(get_db)
):
    q = select(m.Operator).where(access.operators(user)).order_by(m.Operator.code)
    if subcontractor_id is not None:
        q = q.where(m.Operator.subcontractor_id == subcontractor_id)
    return db.scalars(q).all()


@router.post("/operators", response_model=OperatorOut, status_code=201, dependencies=[Depends(staff)])
def create_operator(body: OperatorCreate, db: Session = Depends(get_db)):
    if db.get(m.Subcontractor, body.subcontractor_id) is None:
        raise HTTPException(422, detail="Субподрядчик не найден")
    operator = m.Operator(**body.model_dump())
    db.add(operator)
    _commit(db)
    return operator


@router.post(
    "/shift-reports/{report_id}/rating",
    response_model=OperatorRatingOut,
    status_code=201,
    dependencies=[Depends(can_rate)],
)
def rate_shift(
    report_id: int, body: OperatorRatingCreate, user: m.User = Depends(any_user), db: Session = Depends(get_db)
):
    report = db.scalar(
        select(m.ShiftReport)
        .where(m.ShiftReport.id == report_id)
        .options(selectinload(m.ShiftReport.schedule).selectinload(m.ShiftSchedule.facility_object))
    )
    if report is None:
        raise HTTPException(404, detail="Смена не найдена")
    if not access.can_rate_shift_report(user, report):
        raise HTTPException(403, detail="Нельзя оценивать смены чужих объектов")
    if report.operator_id is None:
        raise HTTPException(422, detail="У смены не указан оператор (operator_id) — оценить нельзя")
    if db.scalar(select(m.OperatorRating).where(m.OperatorRating.shift_report_id == report_id)) is not None:
        raise HTTPException(409, detail="Эта смена уже оценена")

    average = (body.cleanliness + body.quality + body.promptness + body.courtesy) / 4
    rating = m.OperatorRating(
        shift_report_id=report_id,
        operator_id=report.operator_id,
        rated_by_id=user.id,
        cleanliness=body.cleanliness,
        quality=body.quality,
        promptness=body.promptness,
        courtesy=body.courtesy,
        average=round(average, 1),
        comment=body.comment,
    )
    db.add(rating)
    db.add(
        m.OperatorPointsEntry(
            operator_id=report.operator_id,
            shift_report_id=report_id,
            points=opr.rating_adjustment_points(rating),
            reason="rating_adjustment",
            note=f"Оценка {rating.average}/10 за смену {report.work_date}" + (f": «{body.comment}»" if body.comment else ""),
        )
    )
    _commit(db)
    return rating


@router.get("/operators/ranking", response_model=OperatorRankingOut, dependencies=[Depends(staff)])
def ranking(
    as_of: Optional[dt.date] = None, subcontractor_id: Optional[int] = None, db: Session = Depends(get_db)
):
    as_of = as_of or dt.date.today()
    start, end = opr.quarter_bounds(as_of)

    op_query = select(m.Operator).where(m.Operator.active.is_(True))
    if subcontractor_id is not None:
        op_query = op_query.where(m.Operator.subcontractor_id == subcontractor_id)
    operators = db.scalars(op_query).all()

    entries = (
        db.scalars(
            select(m.OperatorPointsEntry).where(
                m.OperatorPointsEntry.operator_id.in_([o.id for o in operators]),
                m.OperatorPointsEntry.created_at >= dt.datetime.combine(start, dt.time.min),
                m.OperatorPointsEntry.created_at <= dt.datetime.combine(end, dt.time.max),
            )
        ).all()
        if operators
        else []
    )

    rows = opr.build_ranking(operators, entries)
    return OperatorRankingOut(
        quarter_start=start,
        quarter_end=end,
        rows=[
            OperatorRankingRow(
                operator=OperatorOut.model_validate(r.operator),
                points=r.points,
                shifts_done=r.shifts_done,
                rank=r.rank,
                bonus=r.bonus,
            )
            for r in rows
        ],
    )
