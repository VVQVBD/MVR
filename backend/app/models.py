"""ORM-модели IC Group (SQLAlchemy 2, PostgreSQL / Supabase; SQLite — для тестов).

ClientCompany ─┬─ Contract ─┬─ ContractAddendum
               │            └─ FacilityObject ── Subcontractor (назначение только по графику)
               ├─ DisputedCondition (Q-01 … Q-11)
               └─ BillingAct (АВР клиенту)
FacilityObject ── ShiftSchedule ── ShiftReport (отметки смен ОПУ)
Subcontractor ── BillingAct (акт субподрядчика P01/P23/P24)
DocumentSourceReference ── M2M с договорами, ДС, объектами и спорными условиями.

Перечисления — строки + CHECK, чтобы одна схема работала и в Postgres, и в SQLite.
Доступ по ролям в Postgres задаётся RLS (db/rls.sql), в API — app/access.py.
"""
import datetime as dt
import uuid
from decimal import Decimal
from typing import List, Optional, Sequence

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Table,
    Text,
    Time,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

Money = Numeric(18, 2)
Area = Numeric(12, 2)
Json = JSON().with_variant(JSONB(), "postgresql")

ROLES = ("executive", "manager", "subcontractor", "client", "operator")
STAFF_ROLES = ("executive", "manager")
SEVERITIES = ("low", "medium", "high")
DISPUTE_STATUSES = ("open", "resolved", "rejected")
RENEWALS = ("auto_annual", "by_agreement", "none")
CONTRACT_STATUSES = ("active", "auto_renewed", "expiring", "expired", "unknown")
VAT_BASES = ("included", "excluded", "unknown")
SHIFT_STATUSES = ("done", "partial", "missed", "replaced")
ACT_KINDS = ("client_avr", "subcontractor_act")
ACT_STATUSES = ("draft", "issued", "signed", "disputed")


def one_of(column: str, values: Sequence[str], name: Optional[str] = None) -> CheckConstraint:
    allowed = ", ".join(f"'{v}'" for v in values)
    return CheckConstraint(f"{column} IN ({allowed})", name=name or column)


def _link(name: str, left: str, left_fk: str) -> Table:
    return Table(
        name,
        Base.metadata,
        Column(left, ForeignKey(left_fk, ondelete="CASCADE"), primary_key=True),
        Column("source_id", ForeignKey("document_source_references.id", ondelete="CASCADE"), primary_key=True),
    )


contract_sources = _link("contract_sources", "contract_id", "contracts.id")
addendum_sources = _link("addendum_sources", "addendum_id", "contract_addenda.id")
facility_sources = _link("facility_sources", "facility_object_id", "facility_objects.id")
dispute_sources = _link("dispute_sources", "dispute_id", "disputed_conditions.id")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        one_of("role", ROLES),
        CheckConstraint("role <> 'client' OR client_company_id IS NOT NULL", name="client_has_company"),
        CheckConstraint("role <> 'subcontractor' OR subcontractor_id IS NOT NULL", name="subcontractor_has_id"),
        CheckConstraint("role <> 'operator' OR operator_id IS NOT NULL", name="operator_has_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Связь с auth.users в Supabase; по нему RLS находит пользователя через auth.uid().
    auth_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, unique=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    # Пароль для собственного входа FastAPI; при входе через Supabase Auth может быть пустым.
    password_hash: Mapped[Optional[str]] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))
    client_company_id: Mapped[Optional[int]] = mapped_column(ForeignKey("client_companies.id", ondelete="CASCADE"))
    subcontractor_id: Mapped[Optional[int]] = mapped_column(ForeignKey("subcontractors.id", ondelete="CASCADE"))
    operator_id: Mapped[Optional[int]] = mapped_column(ForeignKey("operators.id", ondelete="CASCADE"))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    client_company: Mapped[Optional["ClientCompany"]] = relationship()
    subcontractor: Mapped[Optional["Subcontractor"]] = relationship()
    operator: Mapped[Optional["Operator"]] = relationship()

    @property
    def is_staff(self) -> bool:
        return self.role in STAFF_ROLES


class ClientCompany(Base):
    __tablename__ = "client_companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    bin: Mapped[Optional[str]] = mapped_column(String(12))
    notes: Mapped[Optional[str]] = mapped_column(Text)

    contracts: Mapped[List["Contract"]] = relationship(back_populates="client_company", cascade="all, delete-orphan")
    facility_objects: Mapped[List["FacilityObject"]] = relationship(
        back_populates="client_company", cascade="all, delete-orphan"
    )
    disputes: Mapped[List["DisputedCondition"]] = relationship(back_populates="client_company")


class Subcontractor(Base):
    __tablename__ = "subcontractors"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(10), unique=True)  # P01, P23, P24
    name: Mapped[str] = mapped_column(String(255))
    bin: Mapped[Optional[str]] = mapped_column(String(12))

    facility_objects: Mapped[List["FacilityObject"]] = relationship(back_populates="subcontractor")


class Operator(Base):
    """Оператор ОПУ — личность за табельным кодом (см. ShiftReport.operator_code).

    Пилот рейтинга: баллы лояльности и оценки клиента/менеджера начисляются оператору,
    не компании-субподрядчику. ФИО намеренно не храним (как и в остальных отметках смен) —
    только код и отображаемое имя, которое задаёт сам субподрядчик/менеджер.
    """

    __tablename__ = "operators"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)  # напр. OP-047, как в ShiftReport.operator_code
    subcontractor_id: Mapped[int] = mapped_column(ForeignKey("subcontractors.id", ondelete="CASCADE"), index=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(100))
    # Город, который оператор выбрал бы себе для разовых заявок — задел на «топ рейтинга выбирает район».
    preferred_city: Mapped[Optional[str]] = mapped_column(String(100))
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    subcontractor: Mapped["Subcontractor"] = relationship()


class OperatorRating(Base):
    """Оценка 1–10 по четырём критериям — либо отработанной смены (долгосрочный объект),
    либо разовой заявки (`CleaningOrder`). Ровно одно из двух: ни смены без заявки, ни заявки
    без смены, ни обеих сразу — так каждая оценка однозначно ведёт к одной работе."""

    __tablename__ = "operator_ratings"
    __table_args__ = (
        UniqueConstraint("shift_report_id", name="uq_operator_ratings_shift_report"),
        UniqueConstraint("order_id", name="uq_operator_ratings_order"),
        CheckConstraint(
            "(shift_report_id IS NOT NULL) <> (order_id IS NOT NULL)", name="exactly_one_target"
        ),
        CheckConstraint(
            "cleanliness BETWEEN 1 AND 10 AND quality BETWEEN 1 AND 10 "
            "AND promptness BETWEEN 1 AND 10 AND courtesy BETWEEN 1 AND 10",
            name="scores_1_10",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shift_report_id: Mapped[Optional[int]] = mapped_column(ForeignKey("shift_reports.id", ondelete="CASCADE"), index=True)
    order_id: Mapped[Optional[int]] = mapped_column(ForeignKey("cleaning_orders.id", ondelete="CASCADE"), index=True)
    operator_id: Mapped[int] = mapped_column(ForeignKey("operators.id", ondelete="CASCADE"), index=True)
    rated_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    cleanliness: Mapped[int]
    quality: Mapped[int]
    promptness: Mapped[int]
    courtesy: Mapped[int]
    average: Mapped[Decimal] = mapped_column(Numeric(3, 1))
    # Обязателен, если хоть один критерий низкий — отрицательную оценку нельзя оставить без объяснения.
    comment: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    shift_report: Mapped[Optional["ShiftReport"]] = relationship()
    order: Mapped[Optional["CleaningOrder"]] = relationship()
    operator: Mapped[Operator] = relationship()
    rated_by: Mapped[Optional["User"]] = relationship()


class OperatorPointsEntry(Base):
    """Запись в ленте баллов лояльности — один оператор, одна причина, одна смена (если есть).

    Лента, а не просто счётчик: рейтинг всегда можно пересчитать и объяснить, откуда взялось число.
    """

    __tablename__ = "operator_points_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    operator_id: Mapped[int] = mapped_column(ForeignKey("operators.id", ondelete="CASCADE"), index=True)
    shift_report_id: Mapped[Optional[int]] = mapped_column(ForeignKey("shift_reports.id", ondelete="SET NULL"))
    points: Mapped[int]
    # "shift_base" | "rating_adjustment" (за смену по графику) | "order_base" (за разовую заявку)
    reason: Mapped[str] = mapped_column(String(50))
    note: Mapped[Optional[str]] = mapped_column(Text)
    order_id: Mapped[Optional[int]] = mapped_column(ForeignKey("cleaning_orders.id", ondelete="SET NULL"))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    operator: Mapped[Operator] = relationship()
    shift_report: Mapped[Optional["ShiftReport"]] = relationship()
    order: Mapped[Optional["CleaningOrder"]] = relationship()


ORDER_QUALITY = ("surface", "standard", "general")  # поверхностная / средняя / генеральная
ORDER_TEAM_MODE = ("duo", "team", "custom")  # 1–2 оператора / бригада / «другое» число
ORDER_STATUS = ("new", "assigned", "in_progress", "done", "cancelled")
BONUS_SCOPE = ("month", "quarter")
DISCOUNT_STATUS = ("available", "used", "expired")


class CleaningOrder(Base):
    """Разовая заявка на уборку — новый слой поверх долгосрочных Б2Б-договоров (не заменяет их).

    Цена = площадь × ставка за м² по уровню качества (`ORDER_QUALITY_RATES` в app/config.py).
    Ставки — пилотные оценочные значения, в пакете организаторов цен на разовые заявки нет;
    перед продакшеном согласовать с коммерцией. Количество операторов — выбор клиента/менеджера,
    на цену не влияет (на оплату исполнителя — да, но это отдельный расчёт, здесь не считается).
    """

    __tablename__ = "cleaning_orders"
    __table_args__ = (
        one_of("quality", ORDER_QUALITY),
        one_of("team_mode", ORDER_TEAM_MODE),
        one_of("status", ORDER_STATUS),
        CheckConstraint("team_mode <> 'custom' OR custom_operators_count IS NOT NULL", name="custom_needs_count"),
        CheckConstraint("area_m2 > 0", name="area_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # Существующий клиент компании — опционально; для разовых/новых клиентов достаточно client_name.
    client_company_id: Mapped[Optional[int]] = mapped_column(ForeignKey("client_companies.id", ondelete="SET NULL"))
    client_name: Mapped[Optional[str]] = mapped_column(String(255))
    city: Mapped[str] = mapped_column(String(100), index=True)
    area_m2: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    quality: Mapped[str] = mapped_column(String(20))
    team_mode: Mapped[str] = mapped_column(String(20))
    custom_operators_count: Mapped[Optional[int]]
    notes: Mapped[Optional[str]] = mapped_column(Text)  # пожелания, исключения, особые условия
    price_net: Mapped[Decimal] = mapped_column(Money)
    # Скидка «плохая оценка → скидка клиенту» (см. ClientDiscount.used_on_order_id — FK идёт
    # оттуда, чтобы не получить циклическую зависимость между таблицами при создании схемы).
    # price_net уже со скидкой, price_before_discount хранит исходную цену для прослеживаемости.
    price_before_discount: Mapped[Optional[Decimal]] = mapped_column(Money)
    status: Mapped[str] = mapped_column(String(20), default="new")
    assigned_operator_id: Mapped[Optional[int]] = mapped_column(ForeignKey("operators.id", ondelete="SET NULL"))
    assigned_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    assigned_by_auto_priority: Mapped[bool] = mapped_column(default=False)
    completed_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    created_by: Mapped["User"] = relationship(foreign_keys=[created_by_id])
    client_company: Mapped[Optional[ClientCompany]] = relationship()
    assigned_operator: Mapped[Optional[Operator]] = relationship()
    applied_discount: Mapped[Optional["ClientDiscount"]] = relationship(back_populates="used_on_order", uselist=False)
    photos: Mapped[List["OrderPhoto"]] = relationship(back_populates="order", cascade="all, delete-orphan")


class ClientDiscount(Base):
    """Скидка клиенту за честную низкую оценку работы оператора — лента, как OperatorPointsEntry,
    а не флаг: видно, из-за какой оценки выдана, когда и на какую заявку потрачена.

    Выдаётся автоматически, когда клиент/менеджер ставит оценке (смены или разовой заявки)
    средний балл ниже порога комментария (`operator_rating_comment_threshold`, см. app/config.py) —
    низкая оценка уже требует обоснования, этого достаточно, чтобы считать её добросовестной,
    отдельной модерации нет. Потратить можно только на новую заявку, которую переназначили оператору
    из нижних 30% рейтинга квартала (`POST /orders/{id}/auto-assign?redeem_discount=true`) — так
    выигрывают обе стороны: оператор поднимает рейтинг, клиент получает скидку.
    """

    __tablename__ = "client_discounts"
    __table_args__ = (one_of("status", DISCOUNT_STATUS), CheckConstraint("pct > 0 AND pct < 100", name="pct_range"))

    id: Mapped[int] = mapped_column(primary_key=True)
    client_company_id: Mapped[int] = mapped_column(ForeignKey("client_companies.id", ondelete="CASCADE"), index=True)
    pct: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    source_rating_id: Mapped[int] = mapped_column(ForeignKey("operator_ratings.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(20), default="available")
    used_on_order_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("cleaning_orders.id", ondelete="SET NULL"), unique=True
    )
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    used_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))

    client_company: Mapped[ClientCompany] = relationship()
    source_rating: Mapped["OperatorRating"] = relationship()
    used_on_order: Mapped[Optional["CleaningOrder"]] = relationship(back_populates="applied_discount")


class OrderPhoto(Base):
    """Фото после уборки — просто файл и факт загрузки. Оценка по фото — заявлена на защите как
    следующий шаг, сейчас не считается: `ai_review_status` всегда 'not_evaluated'."""

    __tablename__ = "order_photos"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("cleaning_orders.id", ondelete="CASCADE"), index=True)
    operator_id: Mapped[int] = mapped_column(ForeignKey("operators.id", ondelete="CASCADE"))
    file_path: Mapped[str] = mapped_column(String(500))  # относительный путь под backend/storage/
    content_type: Mapped[str] = mapped_column(String(100))
    ai_review_status: Mapped[str] = mapped_column(String(20), default="not_evaluated")
    uploaded_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    order: Mapped[CleaningOrder] = relationship(back_populates="photos")
    operator: Mapped[Operator] = relationship()


class OperatorBonusRecord(Base):
    """Закрытый (зафиксированный) расчёт премии за месяц/квартал — не пересчитывается задним числом,
    в отличие от живого /operators/ranking. Рейтинг физически не «обнуляется»: период уже ограничен
    датами в запросе, новый квартал сам по себе считается от нуля."""

    __tablename__ = "operator_bonus_records"
    __table_args__ = (
        one_of("scope", BONUS_SCOPE),
        UniqueConstraint("operator_id", "scope", "period_start", name="uq_bonus_operator_scope_period"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    operator_id: Mapped[int] = mapped_column(ForeignKey("operators.id", ondelete="CASCADE"), index=True)
    scope: Mapped[str] = mapped_column(String(10))
    period_start: Mapped[dt.date] = mapped_column(Date)
    period_end: Mapped[dt.date] = mapped_column(Date)
    points: Mapped[int]
    rank: Mapped[int]
    total_operators: Mapped[int]
    bonus_amount: Mapped[Decimal] = mapped_column(Money)
    closed_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    closed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    operator: Mapped[Operator] = relationship()


class DocumentSourceReference(Base):
    """Файл пакета (PDF/XLSX/JSON), страница или страницы, лист, строка, цитата/пояснение."""

    __tablename__ = "document_source_references"

    id: Mapped[int] = mapped_column(primary_key=True)
    file: Mapped[str] = mapped_column(String(500), index=True)
    page: Mapped[Optional[int]]
    pages: Mapped[Optional[list]] = mapped_column(Json)
    sheet: Mapped[Optional[str]] = mapped_column(String(100))
    row: Mapped[Optional[int]]
    quote: Mapped[Optional[str]] = mapped_column(Text)
    note: Mapped[Optional[str]] = mapped_column(Text)


class Contract(Base):
    __tablename__ = "contracts"
    __table_args__ = (
        UniqueConstraint("client_company_id", "number", name="uq_contracts_company_number"),
        one_of("renewal", RENEWALS),
        one_of("status", CONTRACT_STATUSES),
        one_of("vat_basis", VAT_BASES),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    client_company_id: Mapped[int] = mapped_column(ForeignKey("client_companies.id", ondelete="CASCADE"), index=True)
    number: Mapped[str] = mapped_column(String(100))
    signed_at: Mapped[Optional[dt.date]] = mapped_column(Date)
    valid_from: Mapped[Optional[dt.date]] = mapped_column(Date)
    valid_to: Mapped[Optional[dt.date]] = mapped_column(Date)  # срок по тексту договора, без пролонгаций
    renewal: Mapped[Optional[str]] = mapped_column(String(20))
    renewal_note: Mapped[Optional[str]] = mapped_column(Text)
    # Статус на дату расчёта (status_as_of); пересчитывается импортом/проверками.
    status: Mapped[str] = mapped_column(String(20), default="unknown")
    status_as_of: Mapped[Optional[dt.date]] = mapped_column(Date)
    status_note: Mapped[Optional[str]] = mapped_column(Text)
    currency: Mapped[str] = mapped_column(String(3), default="KZT")
    vat_basis: Mapped[str] = mapped_column(String(10), default="unknown")
    vat_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    vat_note: Mapped[Optional[str]] = mapped_column(Text)
    stated_monthly_total: Mapped[Optional[Decimal]] = mapped_column(Money)
    # Ставки за м² по группам городов, допуслуги, исходный блок validity.
    terms: Mapped[Optional[dict]] = mapped_column(Json)
    # Текст скана. Никогда не влияет на цифры; проверяется на посторонние инструкции.
    raw_text: Mapped[Optional[str]] = mapped_column(Text)
    injection_flags: Mapped[Optional[list]] = mapped_column(Json)

    client_company: Mapped[ClientCompany] = relationship(back_populates="contracts")
    addenda: Mapped[List["ContractAddendum"]] = relationship(
        back_populates="contract", cascade="all, delete-orphan", order_by="ContractAddendum.id"
    )
    facility_objects: Mapped[List["FacilityObject"]] = relationship(
        back_populates="contract", order_by="FacilityObject.id"
    )
    sources: Mapped[List[DocumentSourceReference]] = relationship(secondary=contract_sources)


class ContractAddendum(Base):
    """Дополнительное соглашение (ДС №24 Модена, ДС №61 Лира, ДС №1 Вента)."""

    __tablename__ = "contract_addenda"
    __table_args__ = (
        UniqueConstraint("contract_id", "number", name="uq_contract_addenda_contract_number"),
        one_of("vat_basis", VAT_BASES),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("contracts.id", ondelete="CASCADE"), index=True)
    number: Mapped[str] = mapped_column(String(50))
    signed_at: Mapped[Optional[dt.date]] = mapped_column(Date)
    effective_from: Mapped[Optional[dt.date]] = mapped_column(Date)
    # Отметка о продлении: ДС продлевает срок договора до этой даты (Спортлайн, Жұлдыз Банк — только так)
    extends_to: Mapped[Optional[dt.date]] = mapped_column(Date)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    vat_basis: Mapped[str] = mapped_column(String(10), default="unknown")
    vat_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    stated_monthly_total: Mapped[Optional[Decimal]] = mapped_column(Money)
    raw_text: Mapped[Optional[str]] = mapped_column(Text)
    injection_flags: Mapped[Optional[list]] = mapped_column(Json)

    contract: Mapped[Contract] = relationship(back_populates="addenda")
    facility_objects: Mapped[List["FacilityObject"]] = relationship(back_populates="addendum")
    sources: Mapped[List[DocumentSourceReference]] = relationship(secondary=addendum_sources)


class FacilityObject(Base):
    """Объект обслуживания и его ежемесячный тариф."""

    __tablename__ = "facility_objects"
    __table_args__ = (
        one_of("vat_basis", VAT_BASES),
        CheckConstraint("area_m2 IS NULL OR area_m2 >= 0", name="area_non_negative"),
        CheckConstraint("monthly_tariff IS NULL OR monthly_tariff >= 0", name="tariff_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    # Дублирует contract.client_company_id — чтобы RLS-политика клиента была одним сравнением.
    client_company_id: Mapped[int] = mapped_column(ForeignKey("client_companies.id", ondelete="CASCADE"), index=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("contracts.id", ondelete="CASCADE"), index=True)
    addendum_id: Mapped[Optional[int]] = mapped_column(ForeignKey("contract_addenda.id", ondelete="SET NULL"))
    city: Mapped[str] = mapped_column(String(100), index=True)
    name: Mapped[str] = mapped_column(String(500))
    area_m2: Mapped[Optional[Decimal]] = mapped_column(Area)
    external_area_m2: Mapped[Optional[Decimal]] = mapped_column(Area)
    facade_area_m2: Mapped[Optional[Decimal]] = mapped_column(Area)
    pricing_group: Mapped[Optional[str]] = mapped_column(String(10))
    services: Mapped[Optional[str]] = mapped_column(Text)
    monthly_tariff: Mapped[Optional[Decimal]] = mapped_column(Money)  # None — «по заявке»
    price_per_m2: Mapped[Optional[Decimal]] = mapped_column(Money)
    vat_basis: Mapped[str] = mapped_column(String(10), default="unknown")
    vat_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    vat_note: Mapped[Optional[str]] = mapped_column(Text)
    # Назначение только по графику объектов (04_Операторы_и_график); справочник по городам — не назначение.
    subcontractor_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("subcontractors.id", ondelete="SET NULL"), index=True
    )

    client_company: Mapped[ClientCompany] = relationship(back_populates="facility_objects")
    contract: Mapped[Contract] = relationship(back_populates="facility_objects")
    addendum: Mapped[Optional[ContractAddendum]] = relationship(back_populates="facility_objects")
    subcontractor: Mapped[Optional[Subcontractor]] = relationship(back_populates="facility_objects")
    sources: Mapped[List[DocumentSourceReference]] = relationship(secondary=facility_sources)
    schedules: Mapped[List["ShiftSchedule"]] = relationship(back_populates="facility_object", cascade="all, delete-orphan")


class DisputedCondition(Base):
    """Реестр спорных условий Q-01 … Q-11."""

    __tablename__ = "disputed_conditions"
    __table_args__ = (one_of("severity", SEVERITIES), one_of("status", DISPUTE_STATUSES))

    id: Mapped[str] = mapped_column(String(10), primary_key=True)  # Q-01
    client_company_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("client_companies.id", ondelete="SET NULL"), index=True
    )
    severity: Mapped[str] = mapped_column(String(10), index=True)
    topic: Mapped[str] = mapped_column(String(255))
    issue: Mapped[str] = mapped_column(Text)
    ask: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default="open")
    resolution: Mapped[Optional[str]] = mapped_column(Text)
    resolved_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    resolved_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))

    client_company: Mapped[Optional[ClientCompany]] = relationship(back_populates="disputes")
    sources: Mapped[List[DocumentSourceReference]] = relationship(secondary=dispute_sources)


class ShiftSchedule(Base):
    """Плановая смена на объекте: сколько ОПУ, в какие часы, по какому графику, за какой месяц."""

    __tablename__ = "shift_schedules"
    __table_args__ = (CheckConstraint("operators_count IS NULL OR operators_count > 0", name="operators_positive"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    facility_object_id: Mapped[int] = mapped_column(ForeignKey("facility_objects.id", ondelete="CASCADE"), index=True)
    subcontractor_id: Mapped[int] = mapped_column(ForeignKey("subcontractors.id", ondelete="CASCADE"), index=True)
    period_month: Mapped[dt.date] = mapped_column(Date)  # первое число месяца
    operators_count: Mapped[Optional[int]]  # None — в документе число ОПУ не указано
    shift_start: Mapped[Optional[dt.time]] = mapped_column(Time)
    shift_end: Mapped[Optional[dt.time]] = mapped_column(Time)
    days_pattern: Mapped[Optional[str]] = mapped_column(String(50))  # ежедневно, 5/2, пт–вс
    note: Mapped[Optional[str]] = mapped_column(Text)
    source_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("document_source_references.id", ondelete="SET NULL")
    )

    facility_object: Mapped[FacilityObject] = relationship(back_populates="schedules")
    subcontractor: Mapped[Subcontractor] = relationship()
    source: Mapped[Optional[DocumentSourceReference]] = relationship()
    reports: Mapped[List["ShiftReport"]] = relationship(back_populates="schedule", cascade="all, delete-orphan")


class ShiftReport(Base):
    """Отметка о фактически отработанной смене оператора ОПУ."""

    __tablename__ = "shift_reports"
    __table_args__ = (
        UniqueConstraint("schedule_id", "work_date", "operator_code", name="uq_shift_reports_day_operator"),
        one_of("status", SHIFT_STATUSES),
        CheckConstraint("hours IS NULL OR (hours >= 0 AND hours <= 24)", name="hours_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    schedule_id: Mapped[int] = mapped_column(ForeignKey("shift_schedules.id", ondelete="CASCADE"), index=True)
    work_date: Mapped[dt.date] = mapped_column(Date)
    # Табельный код оператора, без ФИО.
    operator_code: Mapped[str] = mapped_column(String(32))
    # Привязка к Operator — опциональна (старые/ручные отметки могли не завести оператора);
    # без неё смену нельзя оценить и начислить баллы.
    operator_id: Mapped[Optional[int]] = mapped_column(ForeignKey("operators.id", ondelete="SET NULL"), index=True)
    status: Mapped[str] = mapped_column(String(10))
    started_at: Mapped[Optional[dt.time]] = mapped_column(Time)
    ended_at: Mapped[Optional[dt.time]] = mapped_column(Time)
    hours: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    note: Mapped[Optional[str]] = mapped_column(Text)
    reported_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    schedule: Mapped[ShiftSchedule] = relationship(back_populates="reports")
    operator: Mapped[Optional[Operator]] = relationship()


class BillingAct(Base):
    """АВР клиенту или акт субподрядчика за месяц."""

    __tablename__ = "billing_acts"
    __table_args__ = (
        one_of("kind", ACT_KINDS),
        one_of("status", ACT_STATUSES),
        CheckConstraint("kind <> 'client_avr' OR client_company_id IS NOT NULL", name="avr_has_client"),
        CheckConstraint("kind <> 'subcontractor_act' OR subcontractor_id IS NOT NULL", name="act_has_subcontractor"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))
    number: Mapped[Optional[str]] = mapped_column(String(50))
    period_month: Mapped[dt.date] = mapped_column(Date)
    # Дни оказания услуг внутри месяца; пусто — весь месяц
    service_from: Mapped[Optional[dt.date]] = mapped_column(Date)
    service_to: Mapped[Optional[dt.date]] = mapped_column(Date)
    client_company_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("client_companies.id", ondelete="CASCADE"), index=True
    )
    contract_id: Mapped[Optional[int]] = mapped_column(ForeignKey("contracts.id", ondelete="SET NULL"))
    subcontractor_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("subcontractors.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(10), default="draft")
    issued_at: Mapped[Optional[dt.date]] = mapped_column(Date)
    stated_total: Mapped[Optional[Decimal]] = mapped_column(Money)  # «ИТОГО» как написано в акте
    amount_net: Mapped[Optional[Decimal]] = mapped_column(Money)
    vat_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    vat_amount: Mapped[Optional[Decimal]] = mapped_column(Money)
    amount_gross: Mapped[Optional[Decimal]] = mapped_column(Money)
    source_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("document_source_references.id", ondelete="SET NULL")
    )
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    lines: Mapped[List["BillingActLine"]] = relationship(back_populates="act", cascade="all, delete-orphan")
    source: Mapped[Optional[DocumentSourceReference]] = relationship()
    subcontractor: Mapped[Optional["Subcontractor"]] = relationship()


class BillingActLine(Base):
    __tablename__ = "billing_act_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    act_id: Mapped[int] = mapped_column(ForeignKey("billing_acts.id", ondelete="CASCADE"), index=True)
    facility_object_id: Mapped[Optional[int]] = mapped_column(ForeignKey("facility_objects.id", ondelete="SET NULL"))
    description: Mapped[str] = mapped_column(Text)
    hours: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    amount_net: Mapped[Decimal] = mapped_column(Money)
    note: Mapped[Optional[str]] = mapped_column(Text)

    act: Mapped[BillingAct] = relationship(back_populates="lines")
