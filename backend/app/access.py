"""Видимость строк по ролям в API — те же правила, что RLS-политики в db/rls.sql.

executive, manager — всё;
client — только своя компания (договоры, ДС, объекты, спорные условия, графики и отметки по своим объектам, свои АВР);
subcontractor — только объекты, на которые он назначен в графике смен, свои графики, отметки и акты.

FastAPI подключается к БД ролью-владельцем (RLS её не ограничивает), поэтому правила продублированы здесь.
"""
from decimal import Decimal
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


def _oid(user: m.User):
    return user.operator_id


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
    if user.role == "operator":
        return m.ShiftReport.operator_id == _oid(user)
    return m.ShiftReport.schedule_id.in_(select(m.ShiftSchedule.id).where(schedules(user)))


def operators(user: m.User) -> ColumnElement:
    if user.is_staff:
        return true()
    if user.role == "subcontractor":
        return m.Operator.subcontractor_id == _sid(user)
    if user.role == "operator":
        return m.Operator.id == _oid(user)
    return false()


def operator_ratings(user: m.User) -> ColumnElement:
    if user.is_staff:
        return true()
    if user.role == "operator":
        return m.OperatorRating.operator_id == _oid(user)
    return false()


def operator_points(user: m.User) -> ColumnElement:
    if user.is_staff:
        return true()
    if user.role == "operator":
        return m.OperatorPointsEntry.operator_id == _oid(user)
    return false()


def orders(user: m.User) -> ColumnElement:
    """Разовые заявки (CleaningOrder): штат — всё; клиент — свои (по компании или кто создал);
    субподрядчик — заявки, назначенные его операторам; оператор — свои назначенные заявки."""
    if user.is_staff:
        return true()
    if user.role == "client":
        return and_(
            m.CleaningOrder.client_company_id.isnot(None), m.CleaningOrder.client_company_id == _cid(user)
        )
    if user.role == "subcontractor":
        return m.CleaningOrder.assigned_operator_id.in_(
            select(m.Operator.id).where(m.Operator.subcontractor_id == _sid(user))
        )
    if user.role == "operator":
        return m.CleaningOrder.assigned_operator_id == _oid(user)
    return false()


def order_photos(user: m.User) -> ColumnElement:
    if user.is_staff:
        return true()
    if user.role == "operator":
        return m.OrderPhoto.operator_id == _oid(user)
    return m.OrderPhoto.order_id.in_(select(m.CleaningOrder.id).where(orders(user)))


def bonus_records(user: m.User) -> ColumnElement:
    if user.is_staff:
        return true()
    if user.role == "operator":
        return m.OperatorBonusRecord.operator_id == _oid(user)
    if user.role == "subcontractor":
        return m.OperatorBonusRecord.operator_id.in_(
            select(m.Operator.id).where(m.Operator.subcontractor_id == _sid(user))
        )
    return false()


def can_set_preferred_city(user: m.User, operator: "m.Operator", rank: int, total: int) -> bool:
    """Кто может задать себе район: штат — всегда; оператор — только себе и только если он в топ-30%
    текущего рейтинга квартала (механика «лидер выбирает район» из предложения)."""
    if user.is_staff:
        return True
    if user.role != "operator" or operator.id != _oid(user):
        return False
    if total <= 0:
        return False
    share = Decimal(rank - 1) / Decimal(total)
    return share <= Decimal("0.30")


def acts(user: m.User) -> ColumnElement:
    if user.is_staff:
        return true()
    if user.role == "client":
        return and_(m.BillingAct.kind == "client_avr", m.BillingAct.client_company_id == _cid(user))
    return and_(m.BillingAct.kind == "subcontractor_act", m.BillingAct.subcontractor_id == _sid(user))


def can_rate_shift_report(user: m.User, report: "m.ShiftReport") -> bool:
    """Кто может оценить смену 1–10: персонал — любую; клиент — только по своему объекту."""
    if user.is_staff:
        return True
    if user.role != "client":
        return False
    obj = report.schedule.facility_object
    return obj is not None and obj.client_company_id == _cid(user)


def can_rate_order(user: m.User, order: "m.CleaningOrder") -> bool:
    """Кто может оценить разовую заявку 1–10: персонал — любую; клиент — только свою."""
    if user.is_staff:
        return True
    if user.role != "client":
        return False
    return order.client_company_id is not None and order.client_company_id == _cid(user)


def discounts(user: m.User) -> ColumnElement:
    """Скидки клиента за низкую оценку (ClientDiscount): штат — всё; клиент — свои."""
    if user.is_staff:
        return true()
    if user.role == "client":
        return m.ClientDiscount.client_company_id == _cid(user)
    return false()


def get_visible(db: Session, model: Type, pk, clause: ColumnElement):
    """Строка по ключу, если пользователь её видит; иначе 404 (не раскрываем, что строка существует)."""
    obj = db.scalar(select(model).where(model.id == pk, clause))
    if obj is None:
        raise HTTPException(404, detail="Не найдено")
    return obj
