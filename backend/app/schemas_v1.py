"""DTO для /api/v1: аналитика, калькулятор, аудит договоров."""
import datetime as dt
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from app.schemas import Finding


# ---------- 1. Куда развиваться ----------
class SegmentStats(BaseModel):
    key: str
    objects: int
    clients: int
    area_m2: Decimal
    revenue_net_month: Decimal = Field(description="Выручка без НДС в месяц по действующим тарифам, ₸")
    revenue_per_m2: Optional[Decimal] = None
    objects_on_request: int = Field(description="Объекты «по заявке» — без ежемесячного тарифа")
    subcontractor_assigned: int
    revenue_at_risk: Decimal = Field(description="Выручка по истёкшим договорам, ₸/мес")
    acts_month: Optional[Decimal] = Field(None, description="Акты субподрядчиков за месяц по объектам с актами, ₸")
    margin_month: Optional[Decimal] = Field(None, description="Выручка без НДС − акт, по объектам с актами")
    margin_pct: Optional[Decimal] = None
    objects_with_acts: int = 0


class Recommendation(BaseModel):
    priority: Literal["high", "medium", "low"]
    city: Optional[str] = None
    action: str
    reason: str


class GrowthVectorOut(BaseModel):
    as_of: dt.date
    margin_available: bool
    margin_period: Optional[dt.date] = Field(None, description="Месяц актов, по которым посчитана маржа")
    by_city: List[SegmentStats]
    by_group: List[SegmentStats]
    recommendations: List[Recommendation]
    assumptions: List[str]


# ---------- 2. Сколько стоит новый объект ----------
class SupportIn(BaseModel):
    positions: int = Field(gt=0, le=50, description="Позиций в смене")
    schedule: str = Field(description="График из «Графики и ставки ОПУ», напр. «5/2 полный день 9 ч»")


class EstimateIn(BaseModel):
    """Поля как в 10_Заявки_на_расчёт.xlsx."""

    city: str = Field(min_length=2)
    segment: str = Field(description="Сегмент из листа «Производительность», напр. «Офисы и бизнес-центры»")
    area_m2: Decimal = Field(gt=0, le=1_000_000)
    toilets: int = Field(0, ge=0, le=500)
    base_schedule: str = Field(description="График базовой уборки, напр. «5/2 утро 4 ч»")
    support: List[SupportIn] = Field([], max_length=10)
    hygiene: bool = Field(False, description="Гигиена по ТЗ клиента")
    general_cleaning: bool = False
    client_budget_month_gross: Optional[Decimal] = Field(None, gt=0, description="Бюджет клиента в месяц, ₸ с НДС")
    vat_rate: Optional[Literal[12, 16]] = Field(None, description="По умолчанию — ставка на дату as_of")
    ic_margin_pct: Optional[Decimal] = Field(None, gt=0, lt=100, description="По умолчанию — из 07_Нормативы.json")
    as_of: Optional[dt.date] = None


class EstimateLineOut(BaseModel):
    section: str
    name: str
    unit: str
    qty: Decimal
    price_with_vat: Optional[Decimal] = None
    price_net: Optional[Decimal] = None
    period_months: int
    monthly_net: Decimal
    note: str = ""


class SummaryRow(BaseModel):
    item: str
    monthly_net: Decimal
    yearly_net: Decimal
    share_of_price_pct: Decimal


class PriceOut(BaseModel):
    cost: Decimal
    subcontractor_fee: Decimal
    subcontractor_admin: Decimal
    subcontractor_budget: Decimal = Field(description="Столько IC Line платит субподрядчику в месяц")
    ic_margin: Decimal
    ic_margin_pct: Decimal
    net: Decimal
    vat_rate_pct: Decimal
    vat: Decimal
    gross: Decimal


class BudgetOut(BaseModel):
    client_budget_gross: Decimal
    gap: Decimal = Field(description="Запас (+) или превышение (−) бюджета клиента")
    margin_at_budget: Optional[Decimal] = None
    margin_at_budget_pct: Optional[Decimal] = None


class BenchmarkOut(BaseModel):
    scope: str
    objects: int
    per_m2_median: Decimal
    per_m2_min: Decimal
    per_m2_max: Decimal
    price_net_at_median: Decimal
    our_price_per_m2: Decimal
    object_codes: List[str]


class EstimateOut(BaseModel):
    operators: int
    base_positions: int
    lines: List[EstimateLineOut]
    summary: List[SummaryRow]
    price: PriceOut
    budget: Optional[BudgetOut] = None
    benchmark: Optional[BenchmarkOut] = None
    norms_sources: List[str]
    warnings: List[str] = []


class NormsCatalogOut(BaseModel):
    segments: List[str]
    schedules: List[str]
    cities_with_coefficient: dict
    vat_rates: dict
    ic_margin_pct: Decimal
    min_ic_margin_pct: Decimal


# ---------- 3. Всё ли в порядке с договорами ----------
class AuditScanIn(BaseModel):
    contract_id: Optional[int] = Field(None, description="Проверить договор из базы")
    text: Optional[str] = Field(None, max_length=400_000, description="Текст договора (OCR/копия)")
    pdf_base64: Optional[str] = Field(None, description="Скан договора, PDF в base64")
    client_code: Optional[str] = None
    as_of: Optional[dt.date] = None

    @model_validator(mode="after")
    def _one_source(self):
        given = [x for x in (self.contract_id, self.text, self.pdf_base64) if x]
        if len(given) != 1:
            raise ValueError("Передайте ровно одно: contract_id, text или pdf_base64")
        return self


class ExtractedLineOut(BaseModel):
    object_name: str
    city: Optional[str] = None
    area_m2: Optional[Decimal] = None
    price_per_m2: Optional[Decimal] = None
    monthly_amount: Optional[Decimal] = None
    page: Optional[int] = None


class ExtractionOut(BaseModel):
    model: str
    request_id: Optional[str] = None
    contract_number: Optional[str] = None
    client_name: Optional[str] = None
    valid_from: Optional[dt.date] = None
    valid_until: Optional[dt.date] = None
    renewal: str
    renewal_quote: Optional[str] = None
    vat_basis: str
    vat_rate: Optional[Decimal] = None
    stated_monthly_total: Optional[Decimal] = None
    lines: List[ExtractedLineOut] = []
    amounts_not_in_text: List[str] = Field([], description="Суммы, которых нет в тексте — в проверки не идут")
    verified_against_text: bool


class AuditOut(BaseModel):
    source: Literal["database", "text", "pdf"]
    as_of: dt.date
    contract_number: Optional[str] = None
    contract_id: Optional[int] = None
    verdict: Literal["ok", "warnings", "problems"]
    findings: List[Finding]
    removed_instructions: List[str] = Field([], description="Строки-инструкции, вырезанные до разбора")
    extraction: Optional[ExtractionOut] = None
