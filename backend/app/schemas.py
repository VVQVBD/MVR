"""Pydantic v2 схемы API."""
import datetime as dt
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Role = Literal["executive", "manager", "subcontractor", "client"]
Severity = Literal["low", "medium", "high"]
FindingSeverity = Literal["low", "medium", "high", "critical"]
DisputeStatus = Literal["open", "resolved", "rejected"]
Renewal = Literal["auto_annual", "by_agreement", "none"]
ContractStatus = Literal["active", "auto_renewed", "expiring", "expired", "unknown"]
VatBasis = Literal["included", "excluded", "unknown"]
ShiftStatus = Literal["done", "partial", "missed", "replaced"]
ActKind = Literal["client_avr", "subcontractor_act"]
ActStatus = Literal["draft", "issued", "signed", "disputed"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- пользователи ----------
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserCreate(BaseModel):
    email: str
    password: str = Field(min_length=8)
    role: Role
    client_company_id: Optional[int] = None
    subcontractor_id: Optional[int] = None

    @model_validator(mode="after")
    def _binding(self):
        if self.role == "client" and self.client_company_id is None:
            raise ValueError("Для роли client нужен client_company_id")
        if self.role == "subcontractor" and self.subcontractor_id is None:
            raise ValueError("Для роли subcontractor нужен subcontractor_id")
        return self


class UserOut(ORM):
    id: int
    email: str
    role: Role
    client_company_id: Optional[int] = None
    subcontractor_id: Optional[int] = None


# ---------- справочники ----------
class SourceOut(ORM):
    id: int
    file: str
    page: Optional[int] = None
    pages: Optional[List[int]] = None
    sheet: Optional[str] = None
    row: Optional[int] = None
    quote: Optional[str] = None
    note: Optional[str] = None


class SubcontractorOut(ORM):
    id: int
    code: str
    name: str
    bin: Optional[str] = None


class ClientCompanyCreate(BaseModel):
    code: str
    name: str
    bin: Optional[str] = Field(None, pattern=r"^\d{12}$")
    notes: Optional[str] = None


class ClientCompanyUpdate(BaseModel):
    name: Optional[str] = None
    bin: Optional[str] = Field(None, pattern=r"^\d{12}$")
    notes: Optional[str] = None


class ClientCompanyOut(ORM):
    id: int
    code: str
    name: str
    bin: Optional[str] = None
    notes: Optional[str] = None


# ---------- договоры ----------
class AddendumOut(ORM):
    id: int
    contract_id: int
    number: str
    signed_at: Optional[dt.date] = None
    effective_from: Optional[dt.date] = None
    summary: Optional[str] = None
    vat_basis: VatBasis
    vat_rate: Optional[Decimal] = None
    stated_monthly_total: Optional[Decimal] = None
    injection_flags: Optional[List[str]] = None
    sources: List[SourceOut] = []


class ContractOut(ORM):
    id: int
    client_company_id: int
    number: str
    signed_at: Optional[dt.date] = None
    valid_from: Optional[dt.date] = None
    valid_to: Optional[dt.date] = None
    renewal: Optional[Renewal] = None
    renewal_note: Optional[str] = None
    status: ContractStatus
    status_as_of: Optional[dt.date] = None
    status_note: Optional[str] = None
    currency: str
    vat_basis: VatBasis
    vat_rate: Optional[Decimal] = None
    vat_note: Optional[str] = None
    stated_monthly_total: Optional[Decimal] = None
    terms: Optional[dict] = None
    injection_flags: Optional[List[str]] = None
    addenda: List[AddendumOut] = []
    sources: List[SourceOut] = []


# ---------- объекты ----------
class FacilityObjectBase(BaseModel):
    city: str
    name: str
    area_m2: Optional[Decimal] = Field(None, ge=0)
    external_area_m2: Optional[Decimal] = Field(None, ge=0)
    facade_area_m2: Optional[Decimal] = Field(None, ge=0)
    pricing_group: Optional[str] = None
    services: Optional[str] = None
    monthly_tariff: Optional[Decimal] = Field(None, ge=0)
    price_per_m2: Optional[Decimal] = Field(None, ge=0)
    vat_basis: VatBasis = "unknown"
    vat_rate: Optional[Decimal] = None
    vat_note: Optional[str] = None
    subcontractor_id: Optional[int] = None
    addendum_id: Optional[int] = None


class FacilityObjectCreate(FacilityObjectBase):
    code: str
    contract_id: int


class FacilityObjectUpdate(BaseModel):
    name: Optional[str] = None
    city: Optional[str] = None
    area_m2: Optional[Decimal] = Field(None, ge=0)
    services: Optional[str] = None
    monthly_tariff: Optional[Decimal] = Field(None, ge=0)
    vat_basis: Optional[VatBasis] = None
    vat_rate: Optional[Decimal] = None
    subcontractor_id: Optional[int] = None


class FacilityObjectOut(ORM, FacilityObjectBase):
    id: int
    code: str
    client_company_id: int
    contract_id: int
    subcontractor: Optional[SubcontractorOut] = None


class FacilityObjectForSubcontractor(ORM):
    """Объект глазами субподрядчика: адрес, площадь, услуги. Цен и НДС клиента нет."""

    id: int
    code: str
    city: str
    name: str
    area_m2: Optional[Decimal] = None
    external_area_m2: Optional[Decimal] = None
    facade_area_m2: Optional[Decimal] = None
    services: Optional[str] = None
    subcontractor_id: Optional[int] = None


# ---------- спорные условия ----------
class DisputeOut(ORM):
    id: str
    client_company_id: Optional[int] = None
    client_name: Optional[str] = None
    severity: Severity
    topic: str
    issue: str
    ask: Optional[str] = None
    status: DisputeStatus
    resolution: Optional[str] = None
    resolved_at: Optional[dt.datetime] = None
    sources: List[SourceOut] = []


class DisputeUpdate(BaseModel):
    status: Optional[DisputeStatus] = None
    resolution: Optional[str] = None


# ---------- смены ----------
def _first_day(v: dt.date) -> dt.date:
    if v.day != 1:
        raise ValueError("period_month — первое число месяца")
    return v


class ShiftScheduleCreate(BaseModel):
    facility_object_id: int
    subcontractor_id: int
    period_month: dt.date
    operators_count: Optional[int] = Field(None, gt=0)
    shift_start: Optional[dt.time] = None
    shift_end: Optional[dt.time] = None
    days_pattern: Optional[str] = None
    note: Optional[str] = None

    _period = field_validator("period_month")(_first_day)


class ShiftScheduleOut(ORM):
    id: int
    facility_object_id: int
    subcontractor_id: int
    period_month: dt.date
    operators_count: Optional[int] = None
    shift_start: Optional[dt.time] = None
    shift_end: Optional[dt.time] = None
    days_pattern: Optional[str] = None
    note: Optional[str] = None
    source: Optional[SourceOut] = None


class ShiftReportCreate(BaseModel):
    schedule_id: int
    work_date: dt.date
    operator_code: str = Field(min_length=1, max_length=32)
    status: ShiftStatus
    started_at: Optional[dt.time] = None
    ended_at: Optional[dt.time] = None
    hours: Optional[Decimal] = Field(None, ge=0, le=24)
    note: Optional[str] = None


class ShiftReportOut(ORM, ShiftReportCreate):
    id: int
    reported_by_id: Optional[int] = None


# ---------- акты ----------
class BillingActLineIn(BaseModel):
    facility_object_id: Optional[int] = None
    description: str
    amount_net: Decimal
    note: Optional[str] = None


class BillingActLineOut(ORM, BillingActLineIn):
    id: int


class BillingActCreate(BaseModel):
    kind: ActKind
    number: Optional[str] = None
    period_month: dt.date
    client_company_id: Optional[int] = None
    contract_id: Optional[int] = None
    subcontractor_id: Optional[int] = None
    status: ActStatus = "draft"
    vat_rate: Optional[Decimal] = None
    lines: List[BillingActLineIn] = []

    _period = field_validator("period_month")(_first_day)

    @model_validator(mode="after")
    def _party(self):
        if self.kind == "client_avr" and self.client_company_id is None:
            raise ValueError("АВР клиенту требует client_company_id")
        if self.kind == "subcontractor_act" and self.subcontractor_id is None:
            raise ValueError("Акт субподрядчика требует subcontractor_id")
        return self


class BillingActOut(ORM):
    id: int
    kind: ActKind
    number: Optional[str] = None
    period_month: dt.date
    client_company_id: Optional[int] = None
    contract_id: Optional[int] = None
    subcontractor_id: Optional[int] = None
    status: ActStatus
    amount_net: Optional[Decimal] = None
    vat_rate: Optional[Decimal] = None
    vat_amount: Optional[Decimal] = None
    amount_gross: Optional[Decimal] = None
    lines: List[BillingActLineOut] = []


# ---------- проверки и импорт ----------
class Finding(BaseModel):
    """Результат автоматической проверки (не путать с реестром disputed_conditions)."""

    kind: Literal[
        "arithmetic",
        "line_arithmetic",
        "expired",
        "expiring",
        "renewal_unconfirmed",
        "vat_rate",
        "vat_unspecified",
        "prompt_injection",
    ]
    severity: FindingSeverity
    client_code: str
    contract_number: Optional[str] = None
    message: str
    expected: Optional[Decimal] = None
    actual: Optional[Decimal] = None
    difference: Optional[Decimal] = None


class ImportSummary(BaseModel):
    client_companies: int
    contracts: int
    addenda: int
    facility_objects: int
    subcontractors: int
    shift_schedules: int
    disputed_conditions: int
    sources: int
    injection_flagged: List[str]
