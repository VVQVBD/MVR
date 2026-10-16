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

ROLES = ("executive", "manager", "subcontractor", "client")
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
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    client_company: Mapped[Optional["ClientCompany"]] = relationship()
    subcontractor: Mapped[Optional["Subcontractor"]] = relationship()

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
    status: Mapped[str] = mapped_column(String(10))
    started_at: Mapped[Optional[dt.time]] = mapped_column(Time)
    ended_at: Mapped[Optional[dt.time]] = mapped_column(Time)
    hours: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    note: Mapped[Optional[str]] = mapped_column(Text)
    reported_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    schedule: Mapped[ShiftSchedule] = relationship(back_populates="reports")


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
    client_company_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("client_companies.id", ondelete="CASCADE"), index=True
    )
    contract_id: Mapped[Optional[int]] = mapped_column(ForeignKey("contracts.id", ondelete="SET NULL"))
    subcontractor_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("subcontractors.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(10), default="draft")
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


class BillingActLine(Base):
    __tablename__ = "billing_act_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    act_id: Mapped[int] = mapped_column(ForeignKey("billing_acts.id", ondelete="CASCADE"), index=True)
    facility_object_id: Mapped[Optional[int]] = mapped_column(ForeignKey("facility_objects.id", ondelete="SET NULL"))
    description: Mapped[str] = mapped_column(Text)
    amount_net: Mapped[Decimal] = mapped_column(Money)
    note: Mapped[Optional[str]] = mapped_column(Text)

    act: Mapped[BillingAct] = relationship(back_populates="lines")
