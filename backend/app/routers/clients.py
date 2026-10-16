"""Компании-клиенты, субподрядчики, договоры и объекты."""
from typing import List, Optional, Union

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app import access
from app import models as m
from app.db import get_db
from app.schemas import (
    ClientCompanyCreate,
    ClientCompanyOut,
    ClientCompanyUpdate,
    ContractOut,
    FacilityObjectCreate,
    FacilityObjectForSubcontractor,
    FacilityObjectOut,
    FacilityObjectUpdate,
    SubcontractorOut,
)
from app.security import any_user, executive, staff
from app.services import checks

router = APIRouter(tags=["clients"])


def _commit(db: Session):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, detail="Нарушение уникальности или ссылки")


# ---------- компании ----------
@router.get("/clients", response_model=List[ClientCompanyOut])
def list_clients(user: m.User = Depends(any_user), db: Session = Depends(get_db)):
    return db.scalars(select(m.ClientCompany).where(access.companies(user)).order_by(m.ClientCompany.name)).all()


@router.get("/clients/{client_id}", response_model=ClientCompanyOut)
def get_client(client_id: int, user: m.User = Depends(any_user), db: Session = Depends(get_db)):
    return access.get_visible(db, m.ClientCompany, client_id, access.companies(user))


@router.post("/clients", response_model=ClientCompanyOut, status_code=201, dependencies=[Depends(staff)])
def create_client(body: ClientCompanyCreate, db: Session = Depends(get_db)):
    company = m.ClientCompany(**body.model_dump())
    db.add(company)
    _commit(db)
    return company


@router.patch("/clients/{client_id}", response_model=ClientCompanyOut, dependencies=[Depends(staff)])
def update_client(client_id: int, body: ClientCompanyUpdate, db: Session = Depends(get_db)):
    company = db.get(m.ClientCompany, client_id)
    if company is None:
        raise HTTPException(404, detail="Не найдено")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(company, k, v)
    _commit(db)
    return company


@router.delete("/clients/{client_id}", status_code=204, dependencies=[Depends(executive)])
def delete_client(client_id: int, db: Session = Depends(get_db)):
    company = db.get(m.ClientCompany, client_id)
    if company is None:
        raise HTTPException(404, detail="Не найдено")
    db.delete(company)
    _commit(db)


# ---------- субподрядчики ----------
@router.get("/subcontractors", response_model=List[SubcontractorOut])
def list_subcontractors(user: m.User = Depends(any_user), db: Session = Depends(get_db)):
    return db.scalars(select(m.Subcontractor).where(access.subcontractors(user)).order_by(m.Subcontractor.code)).all()


# ---------- договоры ----------
_contract_options = (
    selectinload(m.Contract.addenda).selectinload(m.ContractAddendum.sources),
    selectinload(m.Contract.sources),
)


@router.get("/contracts", response_model=List[ContractOut])
def list_contracts(
    client_id: Optional[int] = None,
    status: Optional[str] = None,
    user: m.User = Depends(any_user),
    db: Session = Depends(get_db),
):
    q = select(m.Contract).where(access.contracts(user)).options(*_contract_options).order_by(m.Contract.number)
    if client_id is not None:
        q = q.where(m.Contract.client_company_id == client_id)
    if status:
        q = q.where(m.Contract.status == status)
    return db.scalars(q).all()


@router.get("/contracts/{contract_id}", response_model=ContractOut)
def get_contract(contract_id: int, user: m.User = Depends(any_user), db: Session = Depends(get_db)):
    return access.get_visible(db, m.Contract, contract_id, access.contracts(user))


@router.get("/contracts/{contract_id}/text", dependencies=[Depends(staff)])
def get_contract_text(contract_id: int, db: Session = Depends(get_db)):
    """Текст документа без строк, похожих на инструкции для ИИ."""
    c = db.get(m.Contract, contract_id)
    if c is None:
        raise HTTPException(404, detail="Не найдено")
    text, removed = checks.sanitize_text(c.raw_text)
    return {"number": c.number, "text": text, "removed_lines": removed}


# ---------- объекты ----------
def _object_view(user: m.User, obj: m.FacilityObject):
    """Субподрядчику — без тарифа, ставки за м², НДС, договора и клиента."""
    if user.role == "subcontractor":
        return FacilityObjectForSubcontractor.model_validate(obj)
    return FacilityObjectOut.model_validate(obj)


@router.get("/objects", response_model=Union[List[FacilityObjectOut], List[FacilityObjectForSubcontractor]])
def list_objects(
    client_id: Optional[int] = None,
    city: Optional[str] = None,
    subcontractor_id: Optional[int] = None,
    user: m.User = Depends(any_user),
    db: Session = Depends(get_db),
):
    q = (
        select(m.FacilityObject)
        .where(access.facility_objects(user))
        .options(selectinload(m.FacilityObject.subcontractor))
        .order_by(m.FacilityObject.code)
    )
    if client_id is not None:
        q = q.where(m.FacilityObject.client_company_id == client_id)
    if city:
        q = q.where(m.FacilityObject.city == city)
    if subcontractor_id is not None:
        q = q.where(m.FacilityObject.subcontractor_id == subcontractor_id)
    return [_object_view(user, o) for o in db.scalars(q).all()]


@router.get("/objects/{object_id}", response_model=Union[FacilityObjectOut, FacilityObjectForSubcontractor])
def get_object(object_id: int, user: m.User = Depends(any_user), db: Session = Depends(get_db)):
    return _object_view(user, access.get_visible(db, m.FacilityObject, object_id, access.facility_objects(user)))


@router.post("/objects", response_model=FacilityObjectOut, status_code=201, dependencies=[Depends(staff)])
def create_object(body: FacilityObjectCreate, db: Session = Depends(get_db)):
    contract = db.get(m.Contract, body.contract_id)
    if contract is None:
        raise HTTPException(422, detail="Договор не найден")
    obj = m.FacilityObject(**body.model_dump(), client_company_id=contract.client_company_id)
    db.add(obj)
    _commit(db)
    return obj


@router.patch("/objects/{object_id}", response_model=FacilityObjectOut, dependencies=[Depends(staff)])
def update_object(object_id: int, body: FacilityObjectUpdate, db: Session = Depends(get_db)):
    obj = db.get(m.FacilityObject, object_id)
    if obj is None:
        raise HTTPException(404, detail="Не найдено")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    _commit(db)
    return obj


@router.delete("/objects/{object_id}", status_code=204, dependencies=[Depends(executive)])
def delete_object(object_id: int, db: Session = Depends(get_db)):
    obj = db.get(m.FacilityObject, object_id)
    if obj is None:
        raise HTTPException(404, detail="Не найдено")
    db.delete(obj)
    _commit(db)
