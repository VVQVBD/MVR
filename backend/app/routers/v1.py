"""/api/v1 — три вопроса руководителя IC Group.

1. GET  /analytics/growth-vector    — куда развиваться: выручка, маржа по актам, риски по городам и группам
2. POST /calculator/estimate-object — сколько стоит новый объект: смета по нормативам пакета (07, 09)
   GET  /calculator/norms           — справочник сегментов и графиков для формы
3. POST /contracts/audit-scan       — всё ли в порядке с договором (база, текст или скан через Claude)
   GET  /contracts/discrepancies    — реестр спорных условий Q-01…Q-11 с источниками
"""
import datetime as dt
from decimal import Decimal
from typing import Dict, List, Literal, Optional

import anthropic
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import access
from app import models as m
from app.config import settings
from app.db_async import get_async_db
from app.schemas import DisputeOut, Finding
from app.schemas_v1 import (
    AuditOut,
    MonthCloseOut,
    AuditScanIn,
    BenchmarkOut,
    BudgetOut,
    EstimateIn,
    EstimateLineOut,
    EstimateOut,
    ExtractedLineOut,
    ExtractionOut,
    GrowthVectorOut,
    NormsCatalogOut,
    PriceOut,
    Recommendation,
    SegmentStats,
    SummaryRow,
)
from app.security import any_user, staff
from app.services import checks, costing
from app.services import claude_audit as ca
from app.services import estimate as est
from app.services import month_close as mc
from app.services.norms import Norms, NormsError, load_norms

router = APIRouter(prefix="/api/v1", tags=["api v1"])

_OBJECT_OPTIONS = (
    selectinload(m.FacilityObject.contract).selectinload(m.Contract.addenda),
    selectinload(m.FacilityObject.client_company),
)


def get_norms() -> Norms:
    try:
        return load_norms()
    except NormsError as e:
        raise HTTPException(503, detail=f"Нормативы недоступны: {e}")


# =====================================================================================
# 1. Куда развиваться
# =====================================================================================
class _Acc:
    def __init__(self, key: str):
        self.key = key
        self.objects = 0
        self.clients = set()
        self.area = Decimal("0")
        self.revenue = Decimal("0")
        self.revenue_area = Decimal("0")
        self.on_request = 0
        self.assigned = 0
        self.at_risk = Decimal("0")
        self.acts = Decimal("0")
        self.acted_revenue = Decimal("0")
        self.with_acts = 0

    def out(self) -> SegmentStats:
        margin = self.acted_revenue - self.acts if self.with_acts else None
        return SegmentStats(
            key=self.key,
            objects=self.objects,
            clients=len(self.clients),
            area_m2=self.area,
            revenue_net_month=costing.money(self.revenue),
            revenue_per_m2=costing.rate(self.revenue / self.revenue_area) if self.revenue_area else None,
            objects_on_request=self.on_request,
            subcontractor_assigned=self.assigned,
            revenue_at_risk=costing.money(self.at_risk),
            acts_month=costing.money(self.acts) if margin is not None else None,
            margin_month=costing.money(margin) if margin is not None else None,
            margin_pct=(margin / self.acted_revenue * 100).quantize(Decimal("0.1")) if margin is not None else None,
            objects_with_acts=self.with_acts,
        )


@router.get("/analytics/growth-vector", response_model=GrowthVectorOut, dependencies=[Depends(staff)])
async def growth_vector(
    as_of: Optional[dt.date] = Query(None, description="Дата расчёта статусов договоров и НДС"),
    db: AsyncSession = Depends(get_async_db),
):
    as_of = as_of or dt.date.today()
    objects = (await db.scalars(select(m.FacilityObject).options(*_OBJECT_OPTIONS))).all()
    if not objects:
        raise HTTPException(404, detail="В базе нет объектов — выполните seed_data.py")

    # Маржа — по последнему месяцу, за который есть акты субподрядчиков
    period = await db.scalar(
        select(m.BillingAct.period_month)
        .where(m.BillingAct.kind == "subcontractor_act", m.BillingAct.period_month <= as_of)
        .order_by(m.BillingAct.period_month.desc())
        .limit(1)
    )
    acts_by_object: Dict[int, Decimal] = {}
    if period is not None:
        rows = await db.execute(
            select(m.BillingActLine.facility_object_id, m.BillingActLine.amount_net)
            .join(m.BillingAct)
            .where(
                m.BillingAct.kind == "subcontractor_act",
                m.BillingAct.period_month == period,
                m.BillingActLine.facility_object_id.is_not(None),
            )
        )
        for oid, amount in rows:
            acts_by_object[oid] = acts_by_object.get(oid, Decimal(0)) + amount

    groups = costing.city_groups(objects)
    by_city: Dict[str, _Acc] = {}
    by_group: Dict[str, _Acc] = {}
    expired_contracts: Dict[str, Dict] = {}
    assumptions = set()

    for o in objects:
        group = groups.get(o.city, "без группы")
        accs = [by_city.setdefault(o.city, _Acc(o.city)), by_group.setdefault(group, _Acc(group))]
        net = None
        if o.monthly_tariff is not None:
            net, note = costing.net_tariff(o.monthly_tariff, o.vat_basis, o.vat_rate, as_of)
            if note:
                assumptions.add(f"{o.contract.number}: {note}")
        expired = checks.contract_status(o.contract, as_of) == "expired"
        if expired and net is not None:
            risk = expired_contracts.setdefault(
                o.contract.number,
                {"client": o.client_company.name, "until": checks.effective_valid_to(o.contract), "revenue": Decimal("0"), "cities": set()},
            )
            risk["revenue"] += net
            risk["cities"].add(o.city)
        act = acts_by_object.get(o.id)

        for a in accs:
            a.objects += 1
            a.clients.add(o.client_company_id)
            a.area += o.area_m2 or 0
            a.assigned += 1 if o.subcontractor_id else 0
            if o.monthly_tariff is None:
                a.on_request += 1
            if net is not None:
                a.revenue += net
                a.revenue_area += o.area_m2 or 0
                if expired:
                    a.at_risk += net
                if act is not None:
                    a.acts += act
                    a.acted_revenue += net
                    a.with_acts += 1

    cities = sorted((a.out() for a in by_city.values()), key=lambda s: -s.revenue_net_month)
    group_stats = sorted((a.out() for a in by_group.values()), key=lambda s: s.key)
    if period is None:
        assumptions.add("Актов субподрядчиков в базе нет (scripts.import_actuals) — маржа не рассчитана")
    else:
        assumptions.add(
            f"Маржа — выручка без НДС минус акты субподрядчиков за {period:%Y-%m} "
            f"({len(acts_by_object)} объектов); по остальным объектам актов нет"
        )
    assumptions.add("Группы городов I/II/III взяты из договора Жұлдыз Банк — других источников групп в пакете нет")

    return GrowthVectorOut(
        as_of=as_of,
        margin_available=period is not None,
        margin_period=period,
        by_city=cities,
        by_group=group_stats,
        recommendations=_recommendations(cities, expired_contracts),
        assumptions=sorted(assumptions),
    )


def _recommendations(cities: List[SegmentStats], expired: Dict[str, Dict]) -> List[Recommendation]:
    recs: List[Recommendation] = []
    # рост — там, где уже есть спрос нескольких клиентов, а не один крупный объект
    ranked = sorted((s for s in cities if s.clients >= 2 and s.revenue_per_m2 is not None), key=lambda s: -s.revenue_per_m2)
    for s in ranked[:3]:
        margin = f", маржа по актам {s.margin_pct}%" if s.margin_pct is not None else ""
        recs.append(
            Recommendation(
                priority="high",
                city=s.key,
                action="Наращивать присутствие: новые объекты действующих клиентов и новые клиенты в городе",
                reason=f"выручка за м² {s.revenue_per_m2} ₸, {s.objects} объектов, {s.clients} клиентов, "
                f"{s.revenue_net_month} ₸/мес без НДС{margin}",
            )
        )
    for s in cities:
        if s.margin_pct is not None and s.margin_pct < 10:
            recs.append(
                Recommendation(
                    priority="high",
                    city=s.key,
                    action="Пересмотреть тарифы или ставку субподрядчика до расширения",
                    reason=f"маржа по актам {s.margin_pct}% — ниже минимума 10%",
                )
            )
    renew = [
        Recommendation(
            priority="high",
            action=f"Перезаключить договор {number} ({r['client']}) до любых шагов по расширению",
            reason=f"срок истёк {r['until']}, под риском {costing.money(r['revenue'])} ₸/мес без НДС "
            f"в {len(r['cities'])} городах",
        )
        for number, r in sorted(expired.items(), key=lambda kv: -kv[1]["revenue"])
    ]
    uncovered = [s.key for s in cities if s.subcontractor_assigned == 0]
    if uncovered:
        recs.append(
            Recommendation(
                priority="medium",
                action="Назначить субподрядчиков в графике (вопрос Q-07)",
                reason=f"в {len(uncovered)} городах нет ни одного назначения: {', '.join(sorted(uncovered))}",
            )
        )
    singles = [s.key for s in cities if s.objects == 1]
    if singles:
        recs.append(
            Recommendation(
                priority="low",
                action="Точки присутствия: расти через клиентов, уже работающих в этих городах",
                reason=f"по одному объекту: {', '.join(sorted(singles))}",
            )
        )
    return renew + recs  # сначала — деньги, которые уже под риском


# =====================================================================================
# 2. Сколько стоит новый объект
# =====================================================================================
@router.get("/calculator/norms", response_model=NormsCatalogOut, dependencies=[Depends(staff)])
async def calculator_norms(norms: Norms = Depends(get_norms)):
    return NormsCatalogOut(
        segments=list(norms.productivity),
        schedules=list(norms.schedules),
        cities_with_coefficient={k: str(v) for k, v in norms.city_coef.items()},
        vat_rates={("ранее" if start == dt.date.min else f"с {start}"): str(r) for start, r in norms.vat_by_date},
        ic_margin_pct=norms.ic_margin * 100,
        min_ic_margin_pct=norms.min_ic_margin * 100,
    )


@router.post("/calculator/estimate-object", response_model=EstimateOut, dependencies=[Depends(staff)])
async def estimate_object(
    body: EstimateIn, db: AsyncSession = Depends(get_async_db), norms: Norms = Depends(get_norms)
):
    as_of = body.as_of or dt.date.today()
    try:
        r = est.estimate(
            norms,
            city=body.city,
            segment=body.segment,
            area_m2=body.area_m2,
            toilets=body.toilets,
            base_schedule=body.base_schedule,
            support=[est.Support(s.positions, s.schedule) for s in body.support],
            hygiene=body.hygiene,
            general_cleaning=body.general_cleaning,
            budget_gross_month=body.client_budget_month_gross,
            vat_rate=Decimal(body.vat_rate) / 100 if body.vat_rate else None,
            as_of=as_of,
            ic_margin=body.ic_margin_pct / 100 if body.ic_margin_pct else None,
        )
    except est.EstimateError as e:
        raise HTTPException(422, detail=str(e))

    def share(v: Decimal) -> Decimal:
        return (v / r.price_net * 100).quantize(Decimal("0.1"))

    summary = [SummaryRow(item=est.SECTION_LABEL[k], monthly_net=v, yearly_net=v * 12, share_of_price_pct=share(v)) for k, v in r.totals.items()]
    summary += [
        SummaryRow(item=label, monthly_net=v, yearly_net=v * 12, share_of_price_pct=share(v))
        for label, v in (
            ("СЕБЕСТОИМОСТЬ", r.cost),
            ("Вознаграждение субподрядчика", r.subcontractor_fee),
            ("Административные расходы субподрядчика", r.subcontractor_admin),
            ("БЮДЖЕТ СУБПОДРЯДЧИКА", r.subcontractor_budget),
            ("Маржа IC Line", r.ic_margin),
            ("ЦЕНА КЛИЕНТУ БЕЗ НДС", r.price_net),
        )
    ]
    out = EstimateOut(
        operators=r.operators,
        base_positions=r.base_positions,
        lines=[
            EstimateLineOut(
                section=l.section,
                name=l.name,
                unit=l.unit,
                qty=l.qty,
                price_with_vat=l.price_with_vat,
                price_net=est.q2(l.price_net) if l.price_net is not None else None,
                period_months=l.period_months,
                monthly_net=est.q2(l.monthly_net),
                note=l.note,
            )
            for l in r.lines
        ],
        summary=summary,
        price=PriceOut(
            cost=r.cost,
            subcontractor_fee=r.subcontractor_fee,
            subcontractor_admin=r.subcontractor_admin,
            subcontractor_budget=r.subcontractor_budget,
            ic_margin=r.ic_margin,
            ic_margin_pct=share(r.ic_margin),
            net=r.price_net,
            vat_rate_pct=r.vat_rate * 100,
            vat=r.vat,
            gross=r.price_gross,
        ),
        norms_sources=norms.sources,
        warnings=r.warnings,
    )
    if r.budget_gross is not None:
        out.budget = BudgetOut(
            client_budget_gross=r.budget_gross,
            gap=r.budget_gap,
            margin_at_budget=r.margin_at_budget,
            margin_at_budget_pct=r.margin_at_budget_pct,
        )

    premise = costing.SEGMENT_PREMISE.get(body.segment)
    if premise:
        objects = (await db.scalars(select(m.FacilityObject).options(*_OBJECT_OPTIONS))).all()
        bm = costing.benchmark(list(objects), premise, body.city, costing.city_groups(objects), as_of)
        if bm:
            out.benchmark = BenchmarkOut(
                scope=bm.scope,
                objects=bm.n,
                per_m2_median=bm.per_m2_median,
                per_m2_min=bm.per_m2_min,
                per_m2_max=bm.per_m2_max,
                price_net_at_median=costing.money(bm.per_m2_median * body.area_m2),
                our_price_per_m2=costing.rate(r.price_net / body.area_m2),
                object_codes=bm.object_codes,
            )
    return out


# =====================================================================================
# 3. Всё ли в порядке с договорами
# =====================================================================================
_CONTRACT_OPTIONS = (
    selectinload(m.Contract.facility_objects),
    selectinload(m.Contract.addenda).selectinload(m.ContractAddendum.facility_objects),
    selectinload(m.Contract.client_company),
)


async def _work_after_expiry(db: AsyncSession, contract: m.Contract, as_of: dt.date) -> List[Finding]:
    """Графики и акты за периоды после окончания договора, который сам не продлевается."""
    valid_to = checks.effective_valid_to(contract)
    if valid_to is None or checks.contract_status(contract, as_of) != "expired":
        return []
    object_ids = [o.id for o in contract.facility_objects]
    findings = []
    schedules = (
        await db.scalars(
            select(m.ShiftSchedule).where(
                m.ShiftSchedule.facility_object_id.in_(object_ids), m.ShiftSchedule.period_month > valid_to
            )
        )
    ).all()
    acts = (
        await db.scalars(
            select(m.BillingAct)
            .join(m.BillingActLine, isouter=True)
            .where(
                m.BillingAct.period_month > valid_to,
                (m.BillingAct.contract_id == contract.id) | m.BillingActLine.facility_object_id.in_(object_ids),
            )
            .distinct()
        )
    ).all()
    months = sorted({s.period_month for s in schedules} | {a.period_month for a in acts})
    if months:
        periods = ", ".join(d.strftime("%Y-%m") for d in months)
        findings.append(
            Finding(
                kind="work_after_expiry",
                severity="critical",
                client_code=contract.client_company.code,
                contract_number=contract.number,
                message=(
                    f"{contract.number}: работы за {periods} ({len(schedules)} смен в графике, {len(acts)} актов), "
                    f"а договор истёк {valid_to}. Основания для АВР нет до продления."
                ),
            )
        )
    return findings


def _verdict(findings: List[Finding]) -> str:
    if any(f.severity in ("critical", "high") for f in findings):
        return "problems"
    return "warnings" if findings else "ok"


def _transient_contract(data: ca.ExtractedContract, client_code: str, removed: List[str]) -> m.Contract:
    """Договор из разбора — в памяти, в базу не пишется; нужен, чтобы прогнать те же проверки."""
    company = m.ClientCompany(code=client_code, name=data.client_name or client_code)
    contract = m.Contract(
        client_company=company,
        number=data.contract_number or "без номера",
        valid_from=data.valid_from,
        valid_to=data.valid_until,
        renewal=None if data.renewal == "unknown" else data.renewal,
        vat_basis=data.vat_basis,
        vat_rate=ca.to_decimal(data.vat_rate),
        stated_monthly_total=ca.to_decimal(data.stated_monthly_total),
        injection_flags=(removed + list(data.suspicious_instructions)) or None,
    )
    for i, line in enumerate(data.lines, start=1):
        m.FacilityObject(
            code=f"scan-{i:02d}",
            client_company=company,
            contract=contract,
            city=line.city or "",
            name=line.object_name,
            area_m2=ca.to_decimal(line.area_m2),
            price_per_m2=ca.to_decimal(line.price_per_m2),
            monthly_tariff=ca.to_decimal(line.monthly_amount),
            vat_basis=data.vat_basis,
            vat_rate=ca.to_decimal(data.vat_rate),
        )
    return contract


@router.post("/contracts/audit-scan", response_model=AuditOut, dependencies=[Depends(staff)])
async def audit_scan(
    body: AuditScanIn,
    db: AsyncSession = Depends(get_async_db),
    claude: anthropic.AsyncAnthropic = Depends(ca.get_claude),
):
    as_of = body.as_of or dt.date.today()

    # ---- договор из базы: только детерминированные проверки, ИИ не нужен
    if body.contract_id is not None:
        contract = await db.scalar(
            select(m.Contract).where(m.Contract.id == body.contract_id).options(*_CONTRACT_OPTIONS)
        )
        if contract is None:
            raise HTTPException(404, detail="Договор не найден")
        findings = checks.run_all([contract], as_of) + await _work_after_expiry(db, contract, as_of)
        return AuditOut(
            source="database",
            as_of=as_of,
            contract_number=contract.number,
            contract_id=contract.id,
            verdict=_verdict(findings),
            findings=findings,
            removed_instructions=list(contract.injection_flags or []),
        )

    # ---- текст или скан: Claude извлекает поля, проверяет код
    removed: List[str] = []
    if body.pdf_base64 is not None:
        if not ca.is_valid_base64_pdf(body.pdf_base64):
            raise HTTPException(422, detail="pdf_base64 — не PDF в base64")
        source, text = "pdf", None
    else:
        source = "text"
        text, removed = checks.sanitize_text(body.text)
        if not text.strip():
            raise HTTPException(422, detail="После удаления подозрительных строк текст пуст")

    try:
        data, request_id = await ca.extract_contract(claude, text=text, pdf_base64=body.pdf_base64)
    except ca.ClaudeUnavailable as e:
        raise HTTPException(503, detail=str(e))
    except ca.ClaudeRefused as e:
        raise HTTPException(422, detail=str(e))
    except ca.ClaudeBadOutput as e:
        raise HTTPException(502, detail=str(e))

    findings: List[Finding] = []
    missing: List[str] = []
    if text is not None:
        missing = ca.amounts_not_in_text(data, text)
        if missing:
            # суммы, которых нет в документе, в проверки не пускаем
            bad = set(missing)
            if f"итог: {data.stated_monthly_total}" in bad:
                data.stated_monthly_total = None
            for line in data.lines:
                if f"{line.object_name}: {line.monthly_amount}" in bad:
                    line.monthly_amount = None
            findings.append(
                Finding(
                    kind="unverified_amount",
                    severity="medium",
                    client_code=body.client_code or "scan",
                    contract_number=data.contract_number,
                    message=f"Суммы из разбора не найдены в тексте и исключены из проверок: {'; '.join(missing)}",
                )
            )

    contract = _transient_contract(data, body.client_code or "scan", removed)
    findings += checks.run_all([contract], as_of)

    matched_id = None
    if data.contract_number:
        db_contract = await db.scalar(
            select(m.Contract).where(m.Contract.number == data.contract_number).options(*_CONTRACT_OPTIONS)
        )
        if db_contract is not None:
            matched_id = db_contract.id
            findings += await _work_after_expiry(db, db_contract, as_of)

    findings.sort(key=lambda f: ({"critical": 0, "high": 1, "medium": 2, "low": 3}[f.severity], f.kind))
    return AuditOut(
        source=source,
        as_of=as_of,
        contract_number=data.contract_number,
        contract_id=matched_id,
        verdict=_verdict(findings),
        findings=findings,
        removed_instructions=removed,
        extraction=ExtractionOut(
            model=settings.claude_model,
            request_id=request_id or None,
            contract_number=data.contract_number,
            client_name=data.client_name,
            valid_from=data.valid_from,
            valid_until=data.valid_until,
            renewal=data.renewal,
            renewal_quote=data.renewal_quote,
            vat_basis=data.vat_basis,
            vat_rate=ca.to_decimal(data.vat_rate),
            stated_monthly_total=ca.to_decimal(data.stated_monthly_total),
            lines=[
                ExtractedLineOut(
                    object_name=l.object_name,
                    city=l.city,
                    area_m2=ca.to_decimal(l.area_m2),
                    price_per_m2=ca.to_decimal(l.price_per_m2),
                    monthly_amount=ca.to_decimal(l.monthly_amount),
                    page=l.page,
                )
                for l in data.lines
            ],
            amounts_not_in_text=missing,
            verified_against_text=text is not None,
        ),
    )


# =====================================================================================
# Реестр спорных условий
# =====================================================================================
@router.get("/contracts/discrepancies", response_model=List[DisputeOut])
async def discrepancies(
    severity: Optional[Literal["low", "medium", "high"]] = None,
    client_id: Optional[int] = None,
    status: Optional[Literal["open", "resolved", "rejected"]] = None,
    user: m.User = Depends(any_user),
    db: AsyncSession = Depends(get_async_db),
):
    q = (
        select(m.DisputedCondition)
        .where(access.disputes(user))
        .options(selectinload(m.DisputedCondition.sources), selectinload(m.DisputedCondition.client_company))
        .order_by(m.DisputedCondition.id)
    )
    if severity:
        q = q.where(m.DisputedCondition.severity == severity)
    if client_id is not None:
        q = q.where(m.DisputedCondition.client_company_id == client_id)
    if status:
        q = q.where(m.DisputedCondition.status == status)
    out = []
    for d in (await db.scalars(q)).all():
        item = DisputeOut.model_validate(d)
        item.client_name = d.client_company.name if d.client_company else None
        out.append(item)
    return out


# =====================================================================================
# Закрытие месяца (экран frontend/app/page.tsx — ops-консоль, без формы входа)
# =====================================================================================
@router.get("/ops/month-close", response_model=MonthCloseOut, dependencies=[Depends(staff)])
async def month_close(
    period: dt.date = Query(dt.date(2026, 9, 1), description="Первое число месяца закрытия"),
    db: AsyncSession = Depends(get_async_db),
):
    return await mc.build(db, period)
