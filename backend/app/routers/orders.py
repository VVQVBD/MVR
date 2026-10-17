"""Разовые заявки на уборку: форма заказа, назначение оператора, фото, завершение.

Этап 2–3 docs/OPERATOR_RATING_PROPOSAL.md — новый слой поверх долгосрочных договоров
(Contract/FacilityObject), не замена им: CleaningOrder может быть самостоятельной заявкой
или опционально ссылаться на client_company_id постоянного клиента.
"""
import datetime as dt
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import access
from app import models as m
from app.config import settings
from app.db import get_db
from app.schemas_v1 import (
    DiscountOut,
    OperatorRatingCreate,
    OperatorRatingOut,
    OrderAssignIn,
    OrderCreate,
    OrderOut,
    OrderPhotoOut,
)
from app.security import any_user, require_roles, staff
from app.services import discounts as discounts_svc
from app.services import operator_rating as opr
from app.services import orders as orders_svc

router = APIRouter(prefix="/api/v1", tags=["orders"])
can_create_order = require_roles("executive", "manager", "client")
can_rate = require_roles("executive", "manager", "client")
STORAGE_ROOT = Path(__file__).resolve().parents[2]


def _commit(db: Session):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, detail="Нарушение уникальности или ссылки")


def _get_order(db: Session, order_id: int, user: m.User) -> m.CleaningOrder:
    return access.get_visible(db, m.CleaningOrder, order_id, access.orders(user))


@router.post("/orders", response_model=OrderOut, status_code=201, dependencies=[Depends(can_create_order)])
def create_order(body: OrderCreate, user: m.User = Depends(any_user), db: Session = Depends(get_db)):
    if body.client_company_id is not None and db.get(m.ClientCompany, body.client_company_id) is None:
        raise HTTPException(422, detail="Клиент не найден")
    if user.role == "client" and body.client_company_id not in (None, user.client_company_id):
        raise HTTPException(403, detail="Нельзя создавать заявку от имени другой компании")
    order = m.CleaningOrder(
        created_by_id=user.id,
        client_company_id=body.client_company_id or (user.client_company_id if user.role == "client" else None),
        client_name=body.client_name,
        city=body.city,
        area_m2=body.area_m2,
        quality=body.quality,
        team_mode=body.team_mode,
        custom_operators_count=body.custom_operators_count,
        notes=body.notes,
        price_net=orders_svc.price_net(body.area_m2, body.quality),
        status="new",
    )
    db.add(order)
    _commit(db)
    return order


@router.get("/orders", response_model=List[OrderOut])
def list_orders(
    status: Optional[str] = None, city: Optional[str] = None, user: m.User = Depends(any_user), db: Session = Depends(get_db)
):
    q = select(m.CleaningOrder).where(access.orders(user)).order_by(m.CleaningOrder.created_at.desc())
    if status is not None:
        q = q.where(m.CleaningOrder.status == status)
    if city is not None:
        q = q.where(m.CleaningOrder.city == city)
    return db.scalars(q).all()


@router.get("/orders/{order_id}", response_model=OrderOut)
def get_order(order_id: int, user: m.User = Depends(any_user), db: Session = Depends(get_db)):
    return _get_order(db, order_id, user)


@router.post("/orders/{order_id}/assign", response_model=OrderOut, dependencies=[Depends(staff)])
def assign_order(order_id: int, body: OrderAssignIn, db: Session = Depends(get_db)):
    order = db.get(m.CleaningOrder, order_id)
    if order is None:
        raise HTTPException(404, detail="Заявка не найдена")
    if order.status != "new":
        raise HTTPException(409, detail="Заявка уже назначена или закрыта")
    operator = db.get(m.Operator, body.operator_id)
    if operator is None or not operator.active:
        raise HTTPException(422, detail="Оператор не найден или неактивен")
    order.assigned_operator_id = operator.id
    order.assigned_at = dt.datetime.now(dt.timezone.utc)
    order.assigned_by_auto_priority = False
    order.status = "assigned"
    _commit(db)
    return order


@router.post("/orders/{order_id}/auto-assign", response_model=OrderOut, dependencies=[Depends(staff)])
def auto_assign_order(order_id: int, redeem_discount: bool = False, db: Session = Depends(get_db)):
    order = db.get(m.CleaningOrder, order_id)
    if order is None:
        raise HTTPException(404, detail="Заявка не найдена")
    if order.status != "new":
        raise HTTPException(409, detail="Заявка уже назначена или закрыта")

    discount = None
    if redeem_discount:
        if order.client_company_id is None:
            raise HTTPException(422, detail="У заявки не указан клиент — скидку не на что начислить")
        discount = db.scalar(
            select(m.ClientDiscount).where(
                m.ClientDiscount.client_company_id == order.client_company_id,
                m.ClientDiscount.status == "available",
            )
        )
        if discount is None:
            raise HTTPException(409, detail="У клиента нет доступной скидки")
        operator = orders_svc.pick_discount_operator_for_order(db, order)
        if operator is None:
            raise HTTPException(409, detail="Нет свободного оператора в нижних рядах рейтинга для этого города")
    else:
        operator = orders_svc.pick_operator_for_order(db, order)
        if operator is None:
            raise HTTPException(409, detail="Нет свободного оператора по приоритету для этого города")

    order.assigned_operator_id = operator.id
    order.assigned_at = dt.datetime.now(dt.timezone.utc)
    order.assigned_by_auto_priority = True
    order.status = "assigned"
    if discount is not None:
        discounts_svc.apply_to_order(discount, order)
    _commit(db)
    return order


@router.post("/orders/{order_id}/complete", response_model=OrderOut)
def complete_order(order_id: int, user: m.User = Depends(any_user), db: Session = Depends(get_db)):
    order = _get_order(db, order_id, user)
    if order.status not in ("assigned", "in_progress"):
        raise HTTPException(409, detail="Заявку можно завершить только из статуса «назначена»/«в работе»")
    if not user.is_staff and not (user.role == "operator" and order.assigned_operator_id == user.operator_id):
        raise HTTPException(403, detail="Завершить заявку может только назначенный оператор или штат")
    order.status = "done"
    order.completed_at = dt.datetime.now(dt.timezone.utc)
    db.add(
        m.OperatorPointsEntry(
            operator_id=order.assigned_operator_id,
            order_id=order.id,
            points=orders_svc.order_base_points(order),
            reason="order_base",
            note=f"Разовая заявка №{order.id} ({order.city}, {order.area_m2} м², {order.quality})",
        )
    )
    _commit(db)
    return order


@router.post("/orders/{order_id}/photos", response_model=OrderPhotoOut, status_code=201)
async def upload_order_photo(
    order_id: int, file: UploadFile = File(...), user: m.User = Depends(any_user), db: Session = Depends(get_db)
):
    order = _get_order(db, order_id, user)
    if not user.is_staff and not (user.role == "operator" and order.assigned_operator_id == user.operator_id):
        raise HTTPException(403, detail="Загрузить фото может только назначенный оператор или штат")
    if order.assigned_operator_id is None:
        raise HTTPException(409, detail="У заявки нет назначенного оператора")
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(422, detail="Ожидается файл изображения")

    content = await file.read()
    if len(content) > settings.order_photo_max_bytes:
        raise HTTPException(413, detail="Файл больше допустимого размера")

    order_dir = STORAGE_ROOT / settings.order_photos_dir / str(order_id)
    order_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename or "").suffix[:10]
    disk_name = f"{uuid.uuid4().hex}{suffix}"
    (order_dir / disk_name).write_bytes(content)
    rel_path = f"{settings.order_photos_dir}/{order_id}/{disk_name}"

    photo = m.OrderPhoto(
        order_id=order_id,
        operator_id=order.assigned_operator_id,
        file_path=rel_path,
        content_type=file.content_type,
    )
    db.add(photo)
    _commit(db)
    return photo


@router.get("/orders/{order_id}/photos", response_model=List[OrderPhotoOut])
def list_order_photos(order_id: int, user: m.User = Depends(any_user), db: Session = Depends(get_db)):
    _get_order(db, order_id, user)
    return db.scalars(
        select(m.OrderPhoto).where(m.OrderPhoto.order_id == order_id).order_by(m.OrderPhoto.uploaded_at)
    ).all()


@router.post(
    "/orders/{order_id}/rating",
    response_model=OperatorRatingOut,
    status_code=201,
    dependencies=[Depends(can_rate)],
)
def rate_order(order_id: int, body: OperatorRatingCreate, user: m.User = Depends(any_user), db: Session = Depends(get_db)):
    """Оценка 1–10 завершённой разовой заявки. Низкая оценка (с обязательным комментарием —
    см. OperatorRatingCreate) автоматически выдаёт клиенту скидку, см. docs/OPERATOR_RATING_PROPOSAL.md."""
    order = db.get(m.CleaningOrder, order_id)
    if order is None:
        raise HTTPException(404, detail="Заявка не найдена")
    if not access.can_rate_order(user, order):
        raise HTTPException(403, detail="Нельзя оценивать чужие заявки")
    if order.status != "done":
        raise HTTPException(422, detail="Оценить можно только завершённую заявку")
    if order.assigned_operator_id is None:
        raise HTTPException(422, detail="У заявки нет назначенного оператора")
    if db.scalar(select(m.OperatorRating).where(m.OperatorRating.order_id == order_id)) is not None:
        raise HTTPException(409, detail="Эта заявка уже оценена")

    average = (body.cleanliness + body.quality + body.promptness + body.courtesy) / 4
    rating = m.OperatorRating(
        order_id=order_id,
        operator_id=order.assigned_operator_id,
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
            operator_id=order.assigned_operator_id,
            order_id=order.id,
            reason="rating_adjustment",
            points=opr.rating_adjustment_points(rating),
            note=f"Оценка {rating.average}/10 за заявку №{order.id}" + (f": «{body.comment}»" if body.comment else ""),
        )
    )
    discount = discounts_svc.grant_if_low_rating(rating, order.client_company_id)
    if discount is not None:
        db.add(discount)
    _commit(db)
    return rating


@router.get("/discounts", response_model=List[DiscountOut])
def list_discounts(status: Optional[str] = None, user: m.User = Depends(any_user), db: Session = Depends(get_db)):
    q = select(m.ClientDiscount).where(access.discounts(user)).order_by(m.ClientDiscount.created_at.desc())
    if status is not None:
        q = q.where(m.ClientDiscount.status == status)
    return db.scalars(q).all()
