"use client";

import { Award, Loader2, ShieldAlert, Trophy } from "lucide-react";
import { useState } from "react";

import { useCloseBonus, useRanking } from "@/hooks/use-operator-rating";
import { cn } from "@/lib/utils";

const money = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 });
const formatMoney = (value: string) => `${money.format(Number(value))} ₸`;

export function RankingPanel() {
  const { data, isLoading, isError } = useRanking();
  const closeBonus = useCloseBonus();
  const [toast, setToast] = useState<string | null>(null);

  const close = (scope: "month" | "quarter") => {
    closeBonus.mutate(scope, {
      onSuccess: (rows) =>
        setToast(
          scope === "month"
            ? `Премия за месяц закрыта: ${(rows as unknown[]).length} операторов`
            : `Премия за квартал закрыта: ${(rows as unknown[]).length} операторов`,
        ),
      onError: (e) => setToast(`Не удалось закрыть период: ${(e as Error).message}`),
    });
  };

  if (isLoading) return <PanelSkeleton />;
  if (isError || !data) return <PanelError />;

  return (
    <div className="space-y-6">
      <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
        <div>
          <span className="rounded-full border border-emerald-400/20 bg-emerald-400/10 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[.13em] text-emerald-300">
            Квартал · {data.quarter_start} — {data.quarter_end}
          </span>
          <h1 className="mt-4 text-3xl font-semibold tracking-tight">Рейтинг операторов</h1>
          <p className="mt-2 text-sm text-slate-400">
            Баллы лояльности за смены и разовые заявки, премия по месту в рейтинге квартала.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => close("month")}
            disabled={closeBonus.isPending}
            className="inline-flex items-center gap-2 rounded-xl border border-emerald-400/20 bg-emerald-400/10 px-3.5 py-2.5 text-xs font-semibold text-emerald-200 disabled:opacity-60"
          >
            {closeBonus.isPending ? <Loader2 size={14} className="animate-spin" /> : <Award size={14} />}
            Закрыть месяц
          </button>
          <button
            onClick={() => close("quarter")}
            disabled={closeBonus.isPending}
            className="inline-flex items-center gap-2 rounded-xl border border-slate-700 bg-slate-900/70 px-3.5 py-2.5 text-xs font-semibold text-slate-200 disabled:opacity-60"
          >
            <Trophy size={14} />
            Закрыть квартал
          </button>
        </div>
      </div>

      <section className="overflow-hidden rounded-2xl border border-slate-800/80 bg-slate-900/55 shadow-2xl shadow-black/15">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-left">
            <thead className="bg-slate-950/25 text-[10px] uppercase tracking-[.11em] text-slate-500">
              <tr>
                <th className="px-5 py-3">#</th>
                <th className="px-4 py-3">Оператор</th>
                <th className="px-4 py-3">Район</th>
                <th className="px-4 py-3 text-right">Баллы</th>
                <th className="px-4 py-3 text-right">Смены</th>
                <th className="px-4 py-3 text-right">Премия</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((row) => {
                const top30 = data.rows.length > 0 && row.rank - 1 <= 0.3 * data.rows.length;
                return (
                  <tr key={row.operator.id} className="border-t border-slate-800/70 hover:bg-slate-800/40">
                    <td className="px-5 py-4 text-sm font-semibold text-slate-200">{row.rank}</td>
                    <td className="px-4 py-4">
                      <p className="text-sm font-medium text-slate-200">{row.operator.display_name ?? row.operator.code}</p>
                      <p className="mt-0.5 text-xs text-slate-500">{row.operator.code}</p>
                    </td>
                    <td className="px-4 py-4 text-xs text-slate-400">
                      {row.operator.preferred_city ?? (top30 ? <span className="text-emerald-300">может выбрать</span> : "—")}
                    </td>
                    <td className="px-4 py-4 text-right text-sm font-medium text-slate-200">{row.points}</td>
                    <td className="px-4 py-4 text-right text-xs text-slate-400">{row.shifts_done}</td>
                    <td className="px-4 py-4 text-right text-sm font-semibold text-emerald-300">{formatMoney(row.bonus)}</td>
                  </tr>
                );
              })}
              {data.rows.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-5 py-10 text-center text-sm text-slate-500">
                    Нет активных операторов с баллами за этот квартал.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {toast && (
        <div className={cn("rounded-xl border px-4 py-3 text-xs", closeBonus.isError ? "border-rose-400/20 bg-rose-400/[.06] text-rose-200" : "border-emerald-400/20 bg-emerald-400/[.06] text-emerald-200")}>
          {toast}
        </div>
      )}
    </div>
  );
}

function PanelSkeleton() {
  return (
    <div className="space-y-4">
      <div className="h-8 w-64 animate-pulse rounded-lg bg-slate-800/50" />
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
      Не удалось загрузить рейтинг операторов.
    </div>
  );
}
