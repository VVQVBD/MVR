"use client";

import {
  AlertTriangle, ArrowUpRight, Building2, CalendarDays, Check, ChevronDown,
  CircleHelp, FileWarning, Loader2, Menu, Send, ShieldAlert, ShieldCheck, WalletCards, X,
} from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";

import { type AuditedValue, type ReconciliationRow, type SourceRef, useMonthClose } from "@/hooks/use-month-close";
import { cn } from "@/lib/utils";

const money = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 });
const formatMoney = (value: number) => `${money.format(value)} ₸`;
const sourceLabel = (source: SourceRef) => [
  source.file, source.sheet, source.row && `строка ${source.row}`,
  source.page && `стр. ${Array.isArray(source.page) ? source.page.join(", ") : source.page}`,
].filter(Boolean).join(" · ");
type ObjectId = "nord" | "samal-city";

export default function Page() {
  const { data, isLoading, isError } = useMonthClose();
  const [objectId, setObjectId] = useState<ObjectId>("nord");
  const [mobileNav, setMobileNav] = useState(false);
  const [selected, setSelected] = useState<ReconciliationRow | null>(null);
  const [resolved, setResolved] = useState<string[]>([]);
  const [scheduleRequested, setScheduleRequested] = useState(false);
  const [manualOpen, setManualOpen] = useState(false);
  const [isSwitching, setIsSwitching] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    const saved = window.sessionStorage.getItem("ic-group-resolution-state");
    if (saved) setResolved(JSON.parse(saved) as string[]);
  }, []);
  useEffect(() => { window.sessionStorage.setItem("ic-group-resolution-state", JSON.stringify(resolved)); }, [resolved]);
  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 4500);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const current = data?.objects.find((item) => item.id === objectId) ?? data?.objects[0];
  const disputes = useMemo(() => data?.disputes.filter((item) => objectId === "nord"
    ? /Норд|Медеу|Капри|Спортлайн/i.test(`${item.topic} ${item.description}`)
    : /Самал/i.test(`${item.topic} ${item.description}`)) ?? [], [data, objectId]);

  if (isLoading) return <StateScreen loading />;
  if (isError || !data || !current) return <StateScreen />;

  const openRemarks = current.clientRemarks.filter((item) => item.status === "open" && !resolved.includes(`remark:${item.id}`));
  const openDisputes = disputes.filter((item) => !resolved.includes(`dispute:${item.id}`));
  const openRowIssues = current.reconciliation.filter((item) => item.anomalies.length > 0 && !resolved.includes(`row:${item.id}`));
  const issueCount = openRemarks.length + openDisputes.length + openRowIssues.length;
  const resolve = (id: string) => setResolved((items) => items.includes(id) ? items : [...items, id]);
  const requestSchedule = () => {
    setScheduleRequested(true);
    setToast("Запрос на недостающий файл графика отправлен ответственным лицам");
  };
  const switchObject = (nextId: ObjectId) => {
    if (nextId === objectId) return;
    setIsSwitching(true);
    setSelected(null);
    setObjectId(nextId);
    window.setTimeout(() => setIsSwitching(false), 220);
  };
  const revenueSources = current.reconciliation.flatMap((row) => row.revenue.sources);
  const payoutSources = current.reconciliation.flatMap((row) => row.subcontractorPayout.sources);
  const marginSources = current.reconciliation.flatMap((row) => row.marginBeforeOperatorPayout.sources);

  return <main className="min-h-screen bg-[#0b0f17] text-slate-100 selection:bg-emerald-400/30">
    <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(circle_at_76%_-5%,rgba(16,185,129,.14),transparent_25%),radial-gradient(circle_at_5%_90%,rgba(13,148,136,.08),transparent_24%)]" />
    <aside className={cn("fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r border-slate-800/80 bg-[#0d121c]/95 p-4 backdrop-blur-xl transition-transform lg:translate-x-0", mobileNav ? "translate-x-0" : "-translate-x-full")}>
      <Brand />
      <nav className="mt-9 space-y-1"><p className="px-3 pb-2 text-[10px] font-semibold uppercase tracking-[.14em] text-slate-600">Управление</p>
        <NavItem icon={Building2}>Объекты и договоры</NavItem><NavItem icon={ShieldCheck}>Уборка и замечания</NavItem>
        <button className="flex w-full items-center gap-3 rounded-xl bg-emerald-400/10 px-3 py-2.5 text-sm font-medium text-emerald-300 ring-1 ring-inset ring-emerald-400/15"><WalletCards size={17} />Закрытие месяца</button>
      </nav>
      <div className="mt-auto rounded-2xl border border-emerald-400/10 bg-emerald-400/[.06] p-3.5"><p className="flex items-center gap-2 text-xs font-semibold text-emerald-300"><ShieldCheck size={15} />Audit Trail включён</p><p className="mt-2 text-[11px] text-slate-500">Каждая цифра связана с источником.</p></div>
    </aside>
    {mobileNav && <button className="fixed inset-0 z-30 bg-slate-950/70 lg:hidden" onClick={() => setMobileNav(false)} aria-label="Закрыть меню" />}
    <section className="relative min-h-screen lg:pl-64">
      <header className="sticky top-0 z-20 flex h-[74px] items-center justify-between border-b border-slate-800/80 bg-[#0b0f17]/85 px-5 backdrop-blur-xl sm:px-8">
        <div className="flex items-center gap-3"><button className="rounded-xl border border-slate-800 p-2 lg:hidden" onClick={() => setMobileNav(true)} aria-label="Открыть меню"><Menu size={18} /></button><div><p className="text-xs text-slate-500">Финансы / Закрытие месяца</p><p className="text-sm font-semibold text-slate-200">Операционная консоль</p></div></div>
        <div className="flex gap-2"><label className="relative"><select value={objectId} onChange={(event) => switchObject(event.target.value as ObjectId)} className="h-10 appearance-none rounded-xl border border-slate-700 bg-slate-900/70 py-0 pl-3 pr-8 text-xs font-medium text-slate-200 sm:text-sm">{data.objects.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select><ChevronDown className="pointer-events-none absolute right-2.5 top-3 text-slate-500" size={15} /></label><span className="hidden h-10 items-center gap-2 rounded-xl border border-slate-700 bg-slate-900/70 px-3 text-xs text-slate-300 sm:flex"><CalendarDays size={15} className="text-emerald-400" />Сентябрь 2026</span></div>
      </header>
      <div className="mx-auto max-w-[1600px] px-5 py-7 sm:px-8 lg:px-10">
        <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end"><div><span className="rounded-full border border-emerald-400/20 bg-emerald-400/10 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[.13em] text-emerald-300">Период · {data.period}</span><h1 className="mt-4 text-3xl font-semibold tracking-tight">Закрытие месяца</h1><p className="mt-2 text-sm text-slate-400">Договорная выручка, акты и контроль расхождений · <span className="text-slate-200">{current.title}</span></p></div><span className="rounded-xl border border-slate-800 bg-slate-900/60 px-3 py-2 text-xs text-slate-400">{current.reconciliation.length} договорных строк</span></div>
        <div className="mt-7 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <Kpi label="Выручка IC Line" value={formatMoney(current.kpi.revenue)} hint="договорные тарифы" sources={revenueSources} icon={ArrowUpRight} tone="emerald" />
          <Kpi label="Выплаты субподрядчикам" value={formatMoney(current.kpi.subcontractorPayout)} hint="акты за сентябрь" sources={payoutSources} icon={WalletCards} tone="slate" />
          <Kpi label="Маржа до выплат операторам" value={formatMoney(current.kpi.marginBeforeOperatorPayout)} hint="требует сверки базы НДС" sources={marginSources} icon={ShieldCheck} tone="emerald" />
          <Kpi label="Вопросы на проверке" value={String(issueCount).padStart(2, "0")} hint={`${openRemarks.length} замечания · ${openDisputes.length} спора`} icon={AlertTriangle} tone="rose" />
        </div>
        <section className="mt-6 rounded-2xl border border-amber-400/20 bg-amber-400/[.06] p-5"><div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between"><div className="flex gap-3"><div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-amber-400/15 text-amber-300"><FileWarning size={19} /></div><div><p className="font-semibold text-amber-100">Непривязанные отметки · {data.unlinkedShiftsCount}</p><p className="mt-1 max-w-2xl text-xs leading-relaxed text-slate-400">Нет источника графика, поэтому смены не распределяются автоматически по ТРЦ и не искажают финансовый отчёт.</p></div></div><div className="flex flex-wrap gap-2"><button onClick={requestSchedule} disabled={scheduleRequested} className="inline-flex items-center gap-2 rounded-xl bg-amber-300 px-3.5 py-2.5 text-xs font-bold text-slate-950 disabled:bg-emerald-300"><Send size={14} />{scheduleRequested ? "Запрос отправлен" : "Запросить график смен"}</button><button onClick={() => setManualOpen((value) => !value)} className="rounded-xl border border-amber-300/20 px-3.5 py-2.5 text-xs text-amber-100">Распределить вручную</button></div></div>{manualOpen && <p className="mt-4 rounded-xl border border-amber-300/15 bg-slate-950/25 p-3 text-xs text-slate-300">Ручное распределение разрешено только для точечных исключений с документальным основанием.</p>}</section>
        <div className="mt-6 grid gap-6 2xl:grid-cols-[minmax(0,1fr)_340px]">
          <section className="overflow-hidden rounded-2xl border border-slate-800/80 bg-slate-900/55 shadow-2xl shadow-black/15"><div className="flex items-center justify-between border-b border-slate-800/80 px-5 py-5"><div><h2 className="font-semibold">Сверка договорных объектов</h2><p className="mt-1 text-xs text-slate-500">Нажмите строку, чтобы открыть подтверждение источников.</p></div><span className="text-xs text-emerald-300"><ShieldCheck size={14} className="mr-1 inline" />Проверяемо</span></div>
            {isSwitching ? <TableSkeleton /> : current.reconciliation.length === 0 ? <EmptyState /> : <div className="overflow-x-auto"><table className="w-full min-w-[880px] text-left"><thead className="bg-slate-950/25 text-[10px] uppercase tracking-[.11em] text-slate-500"><tr><th className="px-5 py-3">Зона / договор</th><th className="px-4 py-3">План смен</th><th className="px-4 py-3">Аномалии</th><th className="px-4 py-3 text-right">Выплата</th><th className="px-4 py-3 text-right">Выручка</th><th className="px-4 py-3">Статус</th></tr></thead><tbody>{current.reconciliation.map((row) => <ReconciliationTableRow key={row.id} row={row} resolved={resolved.includes(`row:${row.id}`)} onResolve={() => resolve(`row:${row.id}`)} onSelect={() => setSelected(row)} />)}</tbody></table></div>}
          </section>
          <aside className="space-y-5"><section className="rounded-2xl border border-rose-400/15 bg-gradient-to-br from-rose-400/[.09] to-slate-900/60 p-5"><p className="flex items-center gap-2 text-xs font-semibold text-rose-300"><AlertTriangle size={15} />Центр конфликтов</p><h2 className="mt-2 text-lg font-semibold">{issueCount} вопросов требуют решения</h2><div className="mt-4 space-y-3">{openRemarks.map((item) => <ConflictCard key={item.id} title={item.id} description={item.description} source={item.sources[0]} onResolve={() => resolve(`remark:${item.id}`)} />)}{openDisputes.slice(0, 3).map((item) => <ConflictCard key={item.id} title={`${item.id} · ${item.topic}`} description={item.description} source={item.sources[0]} onResolve={() => resolve(`dispute:${item.id}`)} />)}{issueCount === 0 && <p className="text-xs text-emerald-300">Все вопросы для выбранного объекта подтверждены.</p>}</div><button onClick={requestSchedule} className="mt-4 flex w-full items-center justify-center gap-2 rounded-xl border border-rose-400/20 py-2.5 text-xs font-medium text-rose-200"><Send size={14} />Запросить данные у IC Group</button></section><section className="rounded-2xl border border-slate-800/80 bg-slate-900/55 p-5"><p className="text-xs font-semibold text-slate-200">Правило расчёта</p><p className="mt-2 text-xs leading-relaxed text-slate-500">{data.sourcePolicy}</p></section></aside>
        </div>
        {selected && <AuditPanel row={selected} onClose={() => setSelected(null)} />}
      </div>
    </section>
    {toast && <div role="status" className="fixed bottom-5 right-5 z-50 flex max-w-sm items-start gap-3 rounded-2xl border border-emerald-400/25 bg-slate-900/95 p-4 text-sm text-emerald-100 shadow-2xl shadow-black/40 backdrop-blur-xl"><ShieldCheck className="mt-0.5 shrink-0 text-emerald-400" size={18} /><p>{toast}</p><button className="text-slate-500 hover:text-white" onClick={() => setToast(null)} aria-label="Закрыть уведомление"><X size={16} /></button></div>}
  </main>;
}

function Brand() { return <div className="flex items-center gap-3 px-2"><div className="grid h-9 w-9 place-items-center rounded-xl bg-emerald-400 text-sm font-black text-slate-950">IC</div><div><p className="text-sm font-bold">IC GROUP</p><p className="text-[10px] tracking-[.16em] text-emerald-400">OPERATIONS</p></div></div>; }
function NavItem({ icon: Icon, children }: { icon: typeof Building2; children: ReactNode }) { return <button className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-slate-400 hover:bg-slate-800/60"><Icon size={17} />{children}</button>; }
function Kpi({ label, value, hint, sources = [], icon: Icon, tone }: { label: string; value: string; hint: string; sources?: SourceRef[]; icon: typeof ArrowUpRight; tone: "emerald" | "slate" | "rose" }) { const colors = { emerald: "text-emerald-300 border-emerald-400/15 bg-emerald-400/[.06]", slate: "text-slate-300 border-slate-700 bg-slate-900/60", rose: "text-rose-300 border-rose-400/15 bg-rose-400/[.06]" }[tone]; return <article className="group relative rounded-2xl border border-slate-800/80 bg-slate-900/55 p-5 shadow-xl shadow-black/10 transition hover:-translate-y-0.5"><div className="flex justify-between"><p className="text-xs text-slate-500">{label}</p><span className={cn("grid h-8 w-8 place-items-center rounded-xl border", colors)}><Icon size={16} /></span></div><p className="mt-4 text-2xl font-semibold">{value}</p><p className="mt-2 text-[11px] text-slate-500">{hint}</p>{sources.length > 0 && <AuditTooltip sources={sources} />}</article>; }
function AuditTooltip({ sources }: { sources: SourceRef[] }) { const unique = [...new Map(sources.map((source) => [sourceLabel(source), source])).values()].slice(0, 3); return <div className="pointer-events-none absolute bottom-[calc(100%+8px)] left-3 z-30 hidden w-72 rounded-xl border border-emerald-400/20 bg-slate-950/95 p-3 text-[10px] leading-relaxed text-slate-300 shadow-2xl group-hover:block"><p className="font-semibold uppercase tracking-wide text-emerald-300">Audit Trail · источники</p><p className="mt-1.5">{unique.map(sourceLabel).join("; ")}</p></div>; }
function ReconciliationTableRow({ row, resolved, onResolve, onSelect }: { row: ReconciliationRow; resolved: boolean; onResolve: () => void; onSelect: () => void }) { const review = row.status === "review" && !resolved; const anomalySources = row.anomalies.flatMap((item) => item.sources); return <tr onClick={onSelect} className={cn("cursor-pointer border-t border-slate-800/70 transition hover:bg-slate-800/50", review ? "bg-rose-400/[.045]" : "bg-emerald-400/[.018]")}><td className="border-l-2 px-5 py-4" style={{ borderColor: review ? "#fb7185" : "#34d399" }}><p className="text-sm font-medium text-slate-200">{row.zone}</p><p className="mt-0.5 text-xs text-slate-500">{row.client} · {row.contract.value}</p></td><td className="px-4 py-4 text-xs text-amber-200">Нет графика</td><td className="px-4 py-4">{review ? <button onClick={(event) => { event.stopPropagation(); onResolve(); }} className="rounded-md bg-emerald-400 px-2 py-1 text-[10px] font-semibold text-slate-950">Подтвердить</button> : <span className="group relative text-xs text-slate-500">{resolved ? "Подтверждено" : "Сверка по акту"}{anomalySources.length > 0 && <AuditTooltip sources={anomalySources} />}</span>}</td><td className="group relative px-4 py-4 text-right text-sm text-slate-200">{formatMoney(row.subcontractorPayout.value)}<AuditTooltip sources={row.subcontractorPayout.sources} /></td><td className="group relative px-4 py-4 text-right text-sm font-medium text-emerald-300">{formatMoney(row.revenue.value)}<AuditTooltip sources={row.revenue.sources} /></td><td className="px-4 py-4"><Status review={review} /></td></tr>; }
function Status({ review }: { review: boolean }) { return <span className={cn("inline-flex items-center gap-1.5 rounded-full border px-2 py-1 text-[10px] font-semibold", review ? "border-rose-400/20 bg-rose-400/10 text-rose-300" : "border-emerald-400/20 bg-emerald-400/10 text-emerald-300")}>{review ? <AlertTriangle size={11} /> : <Check size={11} />}{review ? "Проверка" : "Закрыто"}</span>; }
function ConflictCard({ title, description, source, onResolve }: { title: string; description: string; source?: SourceRef; onResolve: () => void }) { return <div className="rounded-xl border border-rose-400/10 bg-slate-950/30 p-3"><p className="text-xs font-medium text-slate-200">{title}</p><p className="mt-1 line-clamp-2 text-[11px] text-slate-400">{description}</p>{source && <p className="mt-2 text-[10px] text-rose-200/70">Источник: {sourceLabel(source)}</p>}<button onClick={onResolve} className="mt-3 rounded-lg bg-emerald-400 px-2.5 py-1.5 text-[10px] font-semibold text-slate-950">Подтвердить решение</button></div>; }
function AuditPanel({ row, onClose }: { row: ReconciliationRow; onClose: () => void }) { return <section className="mt-6 rounded-2xl border border-emerald-400/15 bg-emerald-400/[.045] p-5"><div className="flex justify-between"><div><p className="flex items-center gap-2 text-xs font-semibold text-emerald-300"><CircleHelp size={14} />AUDIT TRAIL · {row.contract.value}</p><h3 className="mt-2 font-semibold">{row.zone}</h3></div><button onClick={onClose} className="text-xs text-slate-500">Закрыть</button></div><div className="mt-4 grid gap-3 md:grid-cols-3"><AuditValue label="Выручка" value={row.revenue} /><AuditValue label="Выплата" value={row.subcontractorPayout} /><AuditValue label="Маржа" value={row.marginBeforeOperatorPayout} /></div><p className="mt-4 text-[11px] text-amber-200">Основание НДС: {row.vatBasis}</p></section>; }
function AuditValue({ label, value }: { label: string; value: AuditedValue<number> }) { return <div className="rounded-xl border border-slate-700/70 bg-slate-950/30 p-3"><p className="text-[10px] uppercase text-slate-500">{label}</p><p className="mt-1 text-sm font-medium">{formatMoney(value.value)}</p><p className="mt-2 text-[10px] text-slate-500">Источник: {value.sources.map(sourceLabel).join("; ") || "не указан"}</p></div>; }
function TableSkeleton() { return <div className="space-y-px p-5">{Array.from({ length: 5 }).map((_, index) => <div key={index} className="h-16 animate-pulse rounded-lg bg-slate-800/50" />)}</div>; }
function EmptyState() { return <div className="grid min-h-64 place-items-center p-8 text-center"><div><Building2 className="mx-auto text-slate-600" size={28} /><p className="mt-3 text-sm font-medium text-slate-300">Для этого объекта пока нет строк сверки</p><p className="mt-1 text-xs text-slate-500">После импорта данных они появятся здесь с источниками.</p></div></div>; }
function StateScreen({ loading = false }: { loading?: boolean }) { return <main className="grid min-h-screen place-items-center bg-[#0b0f17] text-slate-300"><div className="flex items-center gap-3 text-sm">{loading ? <Loader2 className="animate-spin text-emerald-400" /> : <ShieldAlert className="text-rose-300" />}{loading ? "Загрузка реальных данных…" : "Не удалось загрузить данные. Запустите npm run import:data."}</div></main>; }
