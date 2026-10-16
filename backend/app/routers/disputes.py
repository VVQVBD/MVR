"""Реестр спорных условий, автопроверки и импорт пакета."""
import datetime as dt
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import access
from app import models as m
from app.db import get_db
from app.schemas import DisputeOut, DisputeUpdate, Finding, ImportSummary
from app.security import any_user, executive, staff
from app.services import checks
from app.services import contracts_v1
from app.services.importer import ImportBlocked, import_contracts

router = APIRouter(tags=["disputes"])


def _out(d: m.DisputedCondition) -> DisputeOut:
    out = DisputeOut.model_validate(d)
    out.client_name = d.client_company.name if d.client_company else None
    return out


@router.get("/disputed-conditions", response_model=List[DisputeOut])
def list_disputes(
    client_id: Optional[int] = None,
    severity: Optional[str] = None,
    status: Optional[str] = None,
    user: m.User = Depends(any_user),
    db: Session = Depends(get_db),
):
    q = (
        select(m.DisputedCondition)
        .where(access.disputes(user))
        .options(selectinload(m.DisputedCondition.sources), selectinload(m.DisputedCondition.client_company))
        .order_by(m.DisputedCondition.id)
    )
    if client_id is not None:
        q = q.where(m.DisputedCondition.client_company_id == client_id)
    if severity:
        q = q.where(m.DisputedCondition.severity == severity)
    if status:
        q = q.where(m.DisputedCondition.status == status)
    return [_out(d) for d in db.scalars(q).all()]


@router.get("/disputed-conditions/{dispute_id}", response_model=DisputeOut)
def get_dispute(dispute_id: str, user: m.User = Depends(any_user), db: Session = Depends(get_db)):
    return _out(access.get_visible(db, m.DisputedCondition, dispute_id, access.disputes(user)))


@router.patch("/disputed-conditions/{dispute_id}", response_model=DisputeOut)
def update_dispute(
    dispute_id: str, body: DisputeUpdate, user: m.User = Depends(staff), db: Session = Depends(get_db)
):
    d = db.get(m.DisputedCondition, dispute_id)
    if d is None:
        raise HTTPException(404, detail="Не найдено")
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(d, k, v)
    if data.get("status") in ("resolved", "rejected"):
        d.resolved_by_id, d.resolved_at = user.id, dt.datetime.now(dt.timezone.utc)
    elif data.get("status") == "open":
        d.resolved_by_id = d.resolved_at = None
    db.commit()
    return _out(d)


@router.get("/checks", response_model=List[Finding], dependencies=[Depends(staff)])
def run_checks(
    as_of: Optional[dt.date] = Query(None, description="Дата проверки, по умолчанию сегодня"),
    db: Session = Depends(get_db),
):
    contracts = db.scalars(
        select(m.Contract).options(
            selectinload(m.Contract.facility_objects),
            selectinload(m.Contract.addenda).selectinload(m.ContractAddendum.facility_objects),
            selectinload(m.Contract.client_company),
        )
    ).all()
    return checks.run_all(contracts, as_of or dt.date.today())


@router.post("/import", response_model=ImportSummary, dependencies=[Depends(executive)])
def import_json(
    body: dict = Body(..., description="contracts.json пакета организаторов (schema_version 1.0)"),
    as_of: Optional[dt.date] = None,
    force: bool = False,
    db: Session = Depends(get_db),
):
    if not contracts_v1.is_v1(body):
        raise HTTPException(422, detail="Ожидается contracts.json пакета организаторов (schema_version 1.0)")
    try:
        return import_contracts(db, body, as_of=as_of, force=force)
    except ImportBlocked as e:
        db.rollback()
        raise HTTPException(409, detail=str(e))
    except (KeyError, ValueError) as e:
        db.rollback()
        raise HTTPException(422, detail=f"Неверный формат: {e}")
