"""Графики смен, отметки смен и акты (АВР клиентам, акты субподрядчиков)."""
import datetime as dt
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app import access
from app import models as m
from app.db import get_db
from app.schemas import (
    BillingActCreate,
    BillingActOut,
    ShiftReportCreate,
    ShiftReportOut,
    ShiftScheduleCreate,
    ShiftScheduleOut,
)
from app.security import any_user, require_roles, staff

router = APIRouter(tags=["operations"])
staff_or_subcontractor = require_roles("executive", "manager", "subcontractor")


def _commit(db: Session):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, detail="Нарушение уникальности или ссылки")


# ---------- графики ----------
@router.get("/schedules", response_model=List[ShiftScheduleOut])
def list_schedules(
    period_month: Optional[dt.date] = None,
    facility_object_id: Optional[int] = None,
    user: m.User = Depends(any_user),
    db: Session = Depends(get_db),
):
    q = (
        select(m.ShiftSchedule)
        .where(access.schedules(user))
        .options(selectinload(m.ShiftSchedule.source))
        .order_by(m.ShiftSchedule.period_month, m.ShiftSchedule.facility_object_id, m.ShiftSchedule.shift_start)
    )
    if period_month is not None:
        q = q.where(m.ShiftSchedule.period_month == period_month)
    if facility_object_id is not None:
        q = q.where(m.ShiftSchedule.facility_object_id == facility_object_id)
    return db.scalars(q).all()


@router.post("/schedules", response_model=ShiftScheduleOut, status_code=201, dependencies=[Depends(staff)])
def create_schedule(body: ShiftScheduleCreate, db: Session = Depends(get_db)):
    obj = db.get(m.FacilityObject, body.facility_object_id)
    if obj is None:
        raise HTTPException(422, detail="Объект не найден")
    schedule = m.ShiftSchedule(**body.model_dump())
    db.add(schedule)
    # Назначение в графике = назначение объекта.
    obj.subcontractor_id = body.subcontractor_id
    _commit(db)
    return schedule


# ---------- отметки смен ----------
@router.get("/shift-reports", response_model=List[ShiftReportOut])
def list_reports(
    schedule_id: Optional[int] = None,
    date_from: Optional[dt.date] = None,
    date_to: Optional[dt.date] = None,
    user: m.User = Depends(any_user),
    db: Session = Depends(get_db),
):
    q = select(m.ShiftReport).where(access.reports(user)).order_by(m.ShiftReport.work_date, m.ShiftReport.id)
    if schedule_id is not None:
        q = q.where(m.ShiftReport.schedule_id == schedule_id)
    if date_from is not None:
        q = q.where(m.ShiftReport.work_date >= date_from)
    if date_to is not None:
        q = q.where(m.ShiftReport.work_date <= date_to)
    return db.scalars(q).all()


@router.post("/shift-reports", response_model=ShiftReportOut, status_code=201)
def create_report(body: ShiftReportCreate, user: m.User = Depends(staff_or_subcontractor), db: Session = Depends(get_db)):
    schedule = access.get_visible(db, m.ShiftSchedule, body.schedule_id, access.schedules(user))
    month = schedule.period_month
    if (body.work_date.year, body.work_date.month) != (month.year, month.month):
        raise HTTPException(422, detail="Дата смены вне месяца графика")
    report = m.ShiftReport(**body.model_dump(), reported_by_id=user.id)
    db.add(report)
    _commit(db)
    return report


# ---------- акты ----------
def _totals(act: m.BillingAct) -> None:
    net = sum((l.amount_net for l in act.lines), Decimal("0"))
    act.amount_net = net.quantize(Decimal("0.01"))
    if act.vat_rate is not None:
        act.vat_amount = (net * act.vat_rate / 100).quantize(Decimal("0.01"))
        act.amount_gross = act.amount_net + act.vat_amount
    else:
        act.vat_amount = None
        act.amount_gross = act.amount_net


@router.get("/billing-acts", response_model=List[BillingActOut])
def list_acts(
    kind: Optional[str] = None,
    period_month: Optional[dt.date] = None,
    user: m.User = Depends(any_user),
    db: Session = Depends(get_db),
):
    q = select(m.BillingAct).where(access.acts(user)).options(selectinload(m.BillingAct.lines)).order_by(m.BillingAct.period_month, m.BillingAct.id)
    if kind:
        q = q.where(m.BillingAct.kind == kind)
    if period_month is not None:
        q = q.where(m.BillingAct.period_month == period_month)
    return db.scalars(q).all()


@router.post("/billing-acts", response_model=BillingActOut, status_code=201, dependencies=[Depends(staff)])
def create_act(body: BillingActCreate, db: Session = Depends(get_db)):
    data = body.model_dump(exclude={"lines"})
    act = m.BillingAct(**data)
    for line in body.lines:
        act.lines.append(m.BillingActLine(**line.model_dump()))
    _totals(act)
    db.add(act)
    _commit(db)
    return act


@router.patch("/billing-acts/{act_id}/status", response_model=BillingActOut, dependencies=[Depends(staff)])
def set_act_status(act_id: int, status: str, db: Session = Depends(get_db)):
    if status not in m.ACT_STATUSES:
        raise HTTPException(422, detail=f"Статус: {', '.join(m.ACT_STATUSES)}")
    act = db.get(m.BillingAct, act_id)
    if act is None:
        raise HTTPException(404, detail="Не найдено")
    act.status = status
    _commit(db)
    return act
