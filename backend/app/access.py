"""Видимость строк по ролям в API — те же правила, что RLS-политики в db/rls.sql.

executive, manager — всё;
client — только своя компания (договоры, ДС, объекты, спорные условия, графики и отметки по своим объектам, свои АВР);
subcontractor — только объекты, на которые он назначен в графике смен, свои графики, отметки и акты.

FastAPI подключается к БД ролью-владельцем (RLS её не ограничивает), поэтому правила продублированы здесь.
"""
from typing import Type

from fastapi import HTTPException
from sqlalchemy import and_, false, select, true
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app import models as m


def _cid(user: m.User):
    return user.client_company_id


def _sid(user: m.User):
    return user.subcontractor_id


def subcontractor_object_ids(user: m.User):
    return select(m.ShiftSchedule.facility_object_id).where(m.ShiftSchedule.subcontractor_id == _sid(user))


def client_object_ids(user: m.User):
    return select(m.FacilityObject.id).where(m.FacilityObject.client_company_id == _cid(user))


def companies(user: m.User) -> ColumnElement:
    if user.is_staff:
        return true()
    if user.role == "client":
        return m.ClientCompany.id == _cid(user)
    return false()


def subcontractors(user: m.User) -> ColumnElement:
    if user.is_staff:
        return true()
    if user.role == "subcontractor":
        return m.Subcontractor.id == _sid(user)
    # клиент видит субподрядчиков, назначенных на его объекты
    return m.Subcontractor.id.in_(
        select(m.FacilityObject.subcontractor_id).where(m.FacilityObject.client_company_id == _cid(user))
    )


def contracts(user: m.User) -> ColumnElement:
    if user.is_staff:
        return true()
    if user.role == "client":
        return m.Contract.client_company_id == _cid(user)
    return false()


def facility_objects(user: m.User) -> ColumnElement:
    if user.is_staff:
        return true()
    if user.role == "client":
        return m.FacilityObject.client_company_id == _cid(user)
    return m.FacilityObject.id.in_(subcontractor_object_ids(user))


def disputes(user: m.User) -> ColumnElement:
    if user.is_staff:
        return true()
    if user.role == "client":
        return m.DisputedCondition.client_company_id == _cid(user)
    return false()


def schedules(user: m.User) -> ColumnElement:
    if user.is_staff:
        return true()
    if user.role == "client":
        return m.ShiftSchedule.facility_object_id.in_(client_object_ids(user))
    return m.ShiftSchedule.subcontractor_id == _sid(user)


def reports(user: m.User) -> ColumnElement:
    if user.is_staff:
        return true()
    return m.ShiftReport.schedule_id.in_(select(m.ShiftSchedule.id).where(schedules(user)))


def acts(user: m.User) -> ColumnElement:
    if user.is_staff:
        return true()
    if user.role == "client":
        return and_(m.BillingAct.kind == "client_avr", m.BillingAct.client_company_id == _cid(user))
    return and_(m.BillingAct.kind == "subcontractor_act", m.BillingAct.subcontractor_id == _sid(user))


def get_visible(db: Session, model: Type, pk, clause: ColumnElement):
    """Строка по ключу, если пользователь её видит; иначе 404 (не раскрываем, что строка существует)."""
    obj = db.scalar(select(model).where(model.id == pk, clause))
    if obj is None:
        raise HTTPException(404, detail="Не найдено")
    return obj
