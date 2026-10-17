"use client";

import { BadgePercent, CheckCircle2, Loader2, PlusCircle, ShieldAlert, Sparkles, Star, UserCheck } from "lucide-react";
import { useState } from "react";

import {
  useClientCompaniesList,
  type Discount,
  useAssignOrder,
  useAutoAssignOrder,
  useCompleteOrder,
  useCreateOrder,
  useDiscounts,
  useOperatorsList,
  type Order,
  useOrders,
  useRateOrder,
} from "@/hooks/use-operator-rating";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

const money = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 });
const formatMoney = (value: string) => `${money.format(Number(value))} ₸`;

const QUALITY_LABEL: Record<string, string> = { surface: "Поверхностная", standard: "Средняя", general: "Генеральная" };
const TEAM_LABEL: Record<string, string> = { duo: "1–2 оператора", team: "Команда", custom: "Другое" };
const STATUS_LABEL: Record<string, string> = { new: "Новая", assigned: "Назначена", in_progress: "В работе", done: "Завершена", cancelled: "Отменена" };

export function OrdersPanel() {
  const { data: orders, isLoading, isError } = useOrders();
  const { data: operators } = useOperatorsList();
  const { data: discounts } = useDiscounts("available");
  const [formOpen, setFormOpen] = useState(false);

  return (
    <div className="space-y-6">
      <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
        <div>
          <span className="rounded-full border border-emerald-400/20 bg-emerald-400/10 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[.13em] text-emerald-300">
            Новый слой поверх договоров
          </span>
          <h1 className="mt-4 text-3xl font-semibold tracking-tight">Разовые заявки</h1>
          <p className="mt-2 text-sm text-slate-400">Заявка на уборку с ценой по площади и уровню качества.</p>
        </div>
        <button
          onClick={() => setFormOpen((v) => !v)}
          className="inline-flex items-center gap-2 rounded-xl bg-emerald-400 px-3.5 py-2.5 text-xs font-bold text-slate-950"
        >
          <PlusCircle size={15} />
          {formOpen ? "Скрыть форму" : "Новая заявка"}
        </button>
      </div>

      {formOpen && <OrderForm onDone={() => setFormOpen(false)} />}

      {isLoading && <PanelSkeleton />}
      {isError && <PanelError />}
      {!isLoading && !isError && orders && (
        <section className="overflow-hidden rounded-2xl border border-slate-800/80 bg-slate-900/55 shadow-2xl shadow-black/15">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[920px] text-left">
              <thead className="bg-slate-950/25 text-[10px] uppercase tracking-[.11em] text-slate-500">
                <tr>
                  <th className="px-5 py-3">Заявка</th>
                  <th className="px-4 py-3">Город</th>
                  <th className="px-4 py-3">Качество / бригада</th>
                  <th className="px-4 py-3 text-right">Цена</th>
                  <th className="px-4 py-3">Статус</th>
                  <th className="px-4 py-3">Действие</th>
                </tr>
              </thead>
              <tbody>
                {orders.map((order) => (
                  <OrderRow key={order.id} order={order} operators={operators ?? []} discounts={discounts ?? []} />
                ))}
                {orders.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-5 py-10 text-center text-sm text-slate-500">
                      Заявок пока нет — создайте первую кнопкой выше.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}

function OrderForm({ onDone }: { onDone: () => void }) {
  const createOrder = useCreateOrder();
  const { data: clients } = useClientCompaniesList();
  const [city, setCity] = useState("Алматы");
  const [area, setArea] = useState("100");
  const [quality, setQuality] = useState<"surface" | "standard" | "general">("standard");
  const [teamMode, setTeamMode] = useState<"duo" | "team" | "custom">("duo");
  const [customCount, setCustomCount] = useState("3");
  const [clientCompanyId, setClientCompanyId] = useState("");
  const [clientName, setClientName] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);

  const submit = () => {
    setError(null);
    createOrder.mutate(
      {
        city,
        area_m2: area,
        quality,
        team_mode: teamMode,
        custom_operators_count: teamMode === "custom" ? Number(customCount) : null,
        client_company_id: clientCompanyId ? Number(clientCompanyId) : null,
        client_name: clientName || null,
        notes: notes || null,
      },
      { onSuccess: onDone, onError: (e) => setError((e as Error).message) },
    );
  };

  return (
    <section className="rounded-2xl border border-slate-800/80 bg-slate-900/55 p-5">
      <h2 className="text-sm font-semibold text-slate-200">Новая заявка на уборку</h2>
      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <Field label="Город">
          <input value={city} onChange={(e) => setCity(e.target.value)} className="input" />
        </Field>
        <Field label="Площадь, м²">
          <input value={area} onChange={(e) => setArea(e.target.value)} type="number" min="1" className="input" />
        </Field>
        <Field label="Качество уборки">
          <select value={quality} onChange={(e) => setQuality(e.target.value as typeof quality)} className="input">
            {Object.entries(QUALITY_LABEL).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
        </Field>
        <Field label="Бригада">
          <select value={teamMode} onChange={(e) => setTeamMode(e.target.value as typeof teamMode)} className="input">
            {Object.entries(TEAM_LABEL).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
        </Field>
        {teamMode === "custom" && (
          <Field label="Число операторов">
            <input value={customCount} onChange={(e) => setCustomCount(e.target.value)} type="number" min="1" className="input" />
          </Field>
        )}
        <Field label="Постоянный клиент (для скидки)">
          <select value={clientCompanyId} onChange={(e) => setClientCompanyId(e.target.value)} className="input">
            <option value="">— без привязки —</option>
            {(clients ?? []).map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </Field>
        <Field label="Клиент (свободный текст)">
          <input value={clientName} onChange={(e) => setClientName(e.target.value)} className="input" placeholder="необязательно" />
        </Field>
      </div>
      <Field label="Пожелания / замечания" className="mt-3">
        <textarea value={notes} onChange={(e) => setNotes(e.target.value)} className="input min-h-20" />
      </Field>
      {error && <p className="mt-3 text-xs text-rose-300">{error}</p>}
      <div className="mt-4 flex items-center gap-3">
        <button
          onClick={submit}
          disabled={createOrder.isPending}
          className="inline-flex items-center gap-2 rounded-xl bg-emerald-400 px-3.5 py-2.5 text-xs font-bold text-slate-950 disabled:opacity-60"
        >
          {createOrder.isPending ? <Loader2 size={14} className="animate-spin" /> : <PlusCircle size={14} />}
          Создать заявку
        </button>
        <p className="text-[11px] text-slate-500">
          Цена считается автоматически: площадь × тариф уровня качества (пилотные ставки).
        </p>
      </div>
    </section>
  );
}

function Field({ label, children, className }: { label: string; children: React.ReactNode; className?: string }) {
  return (
    <label className={cn("block text-xs text-slate-400", className)}>
      {label}
      <div className="mt-1">{children}</div>
    </label>
  );
}

function OrderRow({ order, operators, discounts }: { order: Order; operators: { id: number; code: string; display_name: string | null }[]; discounts: Discount[] }) {
  const assign = useAssignOrder();
  const autoAssign = useAutoAssignOrder();
  const complete = useCompleteOrder();
  const [operatorId, setOperatorId] = useState<string>("");
  const [redeemDiscount, setRedeemDiscount] = useState(false);
  const [ratingOpen, setRatingOpen] = useState(false);

  const availableDiscount = order.client_company_id != null
    ? discounts.find((d) => d.client_company_id === order.client_company_id)
    : undefined;

  return (
    <tr className="border-t border-slate-800/70 hover:bg-slate-800/40">
      <td className="px-5 py-4">
        <p className="text-sm font-medium text-slate-200">№{order.id}{order.client_name ? ` · ${order.client_name}` : ""}</p>
        <p className="mt-0.5 text-xs text-slate-500">{order.area_m2} м²</p>
      </td>
      <td className="px-4 py-4 text-sm text-slate-300">{order.city}</td>
      <td className="px-4 py-4 text-xs text-slate-400">
        {QUALITY_LABEL[order.quality]} · {TEAM_LABEL[order.team_mode]}
      </td>
      <td className="px-4 py-4 text-right text-sm font-medium text-emerald-300">
        {order.price_before_discount && (
          <span className="mr-1.5 text-xs text-slate-500 line-through">{formatMoney(order.price_before_discount)}</span>
        )}
        {formatMoney(order.price_net)}
        {order.price_before_discount && (
          <span className="ml-1.5 inline-flex items-center gap-1 rounded-full border border-emerald-400/20 bg-emerald-400/10 px-1.5 py-0.5 text-[9px] font-semibold text-emerald-300" title="Скидка клиенту за низкую оценку">
            <BadgePercent size={10} />скидка
          </span>
        )}
      </td>
      <td className="px-4 py-4">
        <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-700 bg-slate-900/60 px-2 py-1 text-[10px] font-semibold text-slate-300">
          {STATUS_LABEL[order.status]}
        </span>
      </td>
      <td className="px-4 py-4">
        {order.status === "new" && (
          <div className="flex flex-col gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <select value={operatorId} onChange={(e) => setOperatorId(e.target.value)} className="input !py-1.5 !text-[11px]">
                <option value="">Оператор…</option>
                {operators.map((o) => (
                  <option key={o.id} value={o.id}>{o.display_name ?? o.code}</option>
                ))}
              </select>
              <button
                disabled={!operatorId || assign.isPending}
                onClick={() => assign.mutate({ orderId: order.id, operatorId: Number(operatorId) })}
                className="rounded-lg border border-slate-700 px-2.5 py-1.5 text-[10px] font-semibold text-slate-200 disabled:opacity-50"
              >
                <UserCheck size={12} className="mr-1 inline" />Назначить
              </button>
              <button
                disabled={autoAssign.isPending}
                onClick={() => autoAssign.mutate({ orderId: order.id, redeemDiscount })}
                className="rounded-lg bg-emerald-400/15 px-2.5 py-1.5 text-[10px] font-semibold text-emerald-200 disabled:opacity-50"
                title="По приоритету рейтинга текущего квартала"
              >
                <Sparkles size={12} className="mr-1 inline" />Авто
              </button>
            </div>
            {availableDiscount && (
              <label className="flex items-center gap-1.5 text-[10px] text-emerald-300">
                <input type="checkbox" checked={redeemDiscount} onChange={(e) => setRedeemDiscount(e.target.checked)} />
                Потратить скидку клиента ({availableDiscount.pct}%) — назначит оператора из нижних 30% рейтинга
              </label>
            )}
            {autoAssign.isError && <span className="text-[10px] text-rose-300">{(autoAssign.error as Error).message}</span>}
          </div>
        )}
        {(order.status === "assigned" || order.status === "in_progress") && (
          <button
            disabled={complete.isPending}
            onClick={() => complete.mutate(order.id)}
            className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-400 px-2.5 py-1.5 text-[10px] font-bold text-slate-950 disabled:opacity-50"
          >
            <CheckCircle2 size={12} />Завершить
          </button>
        )}
        {order.status === "done" && (
          <div className="flex flex-col items-start gap-1.5">
            <span className="text-[11px] text-emerald-300">Готово</span>
            <button
              onClick={() => setRatingOpen((v) => !v)}
              className="inline-flex items-center gap-1 rounded-lg border border-slate-700 px-2 py-1 text-[10px] text-slate-300"
            >
              <Star size={11} />Оценить
            </button>
            {ratingOpen && <RatingForm orderId={order.id} onDone={() => setRatingOpen(false)} />}
          </div>
        )}
      </td>
    </tr>
  );
}

function RatingForm({ orderId, onDone }: { orderId: number; onDone: () => void }) {
  const rateOrder = useRateOrder();
  const [scores, setScores] = useState({ cleanliness: 9, quality: 9, promptness: 9, courtesy: 9 });
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);

  const set = (key: keyof typeof scores, value: number) => setScores((s) => ({ ...s, [key]: value }));

  const submit = () => {
    setError(null);
    rateOrder.mutate(
      { orderId, body: { ...scores, comment: comment || null } },
      {
        onSuccess: () => {
          const low = Object.values(scores).some((v) => v < 6);
          setResult(low ? "Оценка сохранена — клиенту начислена скидка." : "Оценка сохранена.");
          window.setTimeout(onDone, 1500);
        },
        onError: (e) => setError(e instanceof ApiError ? e.message : (e as Error).message),
      },
    );
  };

  return (
    <div className="w-72 rounded-xl border border-slate-700 bg-slate-950/60 p-3">
      {(["cleanliness", "quality", "promptness", "courtesy"] as const).map((key) => (
        <label key={key} className="mb-1.5 flex items-center justify-between text-[10px] text-slate-400">
          {{ cleanliness: "Чистота", quality: "Качество", promptness: "Оперативность", courtesy: "Вежливость" }[key]}
          <input
            type="number" min={1} max={10} value={scores[key]}
            onChange={(e) => set(key, Number(e.target.value))}
            className="input !w-14 !py-1 !text-center !text-[11px]"
          />
        </label>
      ))}
      <textarea
        value={comment} onChange={(e) => setComment(e.target.value)}
        placeholder="Комментарий (обязателен при низкой оценке)"
        className="input mt-1 min-h-14 !text-[11px]"
      />
      {error && <p className="mt-1.5 text-[10px] text-rose-300">{error}</p>}
      {result && <p className="mt-1.5 text-[10px] text-emerald-300">{result}</p>}
      <button
        onClick={submit}
        disabled={rateOrder.isPending}
        className="mt-2 w-full rounded-lg bg-emerald-400 py-1.5 text-[10px] font-bold text-slate-950 disabled:opacity-50"
      >
        Сохранить оценку
      </button>
    </div>
  );
}

function PanelSkeleton() {
  return (
    <div className="space-y-4">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="h-14 animate-pulse rounded-lg bg-slate-800/50" />
      ))}
    </div>
  );
}

function PanelError() {
  return (
    <div className="flex items-center gap-3 rounded-2xl border border-rose-400/20 bg-rose-400/[.06] p-5 text-sm text-rose-200">
      <ShieldAlert size={18} />
      Не удалось загрузить заявки.
    </div>
  );
}
