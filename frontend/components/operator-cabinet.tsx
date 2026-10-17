"use client";

import { Camera, CheckCircle2, LogOut, MapPin, ShieldAlert, ShieldCheck } from "lucide-react";
import { useRef, useState } from "react";

import {
  useCompleteMyOrder,
  useMyBonus,
  useMyOperator,
  useMyOrders,
  useMyProfile,
  useSetMyPreferredCity,
  useUploadMyPhoto,
} from "@/hooks/use-operator-cabinet";
import { ApiError } from "@/lib/api";
import { useOperatorSession } from "@/store/operator-session";

const money = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 });
const formatMoney = (value: string) => `${money.format(Number(value))} ₸`;

const QUALITY_LABEL: Record<string, string> = { surface: "Поверхностная", standard: "Средняя", general: "Генеральная" };
const STATUS_LABEL: Record<string, string> = { new: "Новая", assigned: "Назначена", in_progress: "В работе", done: "Завершена", cancelled: "Отменена" };

export function OperatorCabinet() {
  const email = useOperatorSession((s) => s.email);
  const clear = useOperatorSession((s) => s.clear);
  const { data: me, isLoading: meLoading, isError: meError } = useMyProfile();
  const { data: operator } = useMyOperator(me?.operator_id ?? undefined);
  const { data: orders, isLoading: ordersLoading } = useMyOrders();
  const { data: bonus } = useMyBonus();

  if (meLoading) return <CabinetScreen loading />;
  if (meError || !me) return <CabinetScreen onLogout={clear} error />;

  return (
    <main className="min-h-screen bg-[#0b0f17] text-slate-100">
      <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(circle_at_76%_-5%,rgba(16,185,129,.14),transparent_25%),radial-gradient(circle_at_5%_90%,rgba(13,148,136,.08),transparent_24%)]" />
      <header className="sticky top-0 z-20 flex h-[74px] items-center justify-between border-b border-slate-800/80 bg-[#0b0f17]/85 px-5 backdrop-blur-xl sm:px-8">
        <div className="flex items-center gap-3">
          <div className="grid h-9 w-9 place-items-center rounded-xl bg-emerald-400 text-sm font-black text-slate-950">IC</div>
          <div>
            <p className="text-xs text-slate-500">Личный кабинет оператора</p>
            <p className="text-sm font-semibold text-slate-200">{operator?.display_name ?? operator?.code ?? email}</p>
          </div>
        </div>
        <button onClick={clear} className="inline-flex items-center gap-2 rounded-xl border border-slate-700 px-3 py-2 text-xs text-slate-300">
          <LogOut size={14} />Выйти
        </button>
      </header>
      <div className="mx-auto max-w-[1100px] space-y-6 px-5 py-7 sm:px-8">
        {operator && <ProfileCard operator={operator} />}
        <section>
          <h2 className="text-sm font-semibold text-slate-200">Мои заявки</h2>
          <div className="mt-3 overflow-hidden rounded-2xl border border-slate-800/80 bg-slate-900/55">
            {ordersLoading ? (
              <div className="space-y-px p-5">
                {Array.from({ length: 2 }).map((_, i) => <div key={i} className="h-14 animate-pulse rounded-lg bg-slate-800/50" />)}
              </div>
            ) : !orders || orders.length === 0 ? (
              <p className="p-6 text-center text-sm text-slate-500">Заявок пока не назначено.</p>
            ) : (
              <div className="divide-y divide-slate-800/70">
                {orders.map((order) => <OrderCard key={order.id} order={order} />)}
              </div>
            )}
          </div>
        </section>
        <section>
          <h2 className="text-sm font-semibold text-slate-200">Моя премия</h2>
          <div className="mt-3 overflow-hidden rounded-2xl border border-slate-800/80 bg-slate-900/55">
            {!bonus || bonus.length === 0 ? (
              <p className="p-6 text-center text-sm text-slate-500">Премия ещё не начислялась.</p>
            ) : (
              <table className="w-full text-left">
                <thead className="bg-slate-950/25 text-[10px] uppercase tracking-[.11em] text-slate-500">
                  <tr><th className="px-5 py-3">Период</th><th className="px-4 py-3">Место</th><th className="px-4 py-3 text-right">Баллы</th><th className="px-4 py-3 text-right">Премия</th></tr>
                </thead>
                <tbody>
                  {bonus.map((b) => (
                    <tr key={b.id} className="border-t border-slate-800/70">
                      <td className="px-5 py-3 text-sm text-slate-300">{b.period_start} — {b.period_end} · {b.scope === "month" ? "месяц" : "квартал"}</td>
                      <td className="px-4 py-3 text-sm text-slate-300">{b.rank} из {b.total_operators}</td>
                      <td className="px-4 py-3 text-right text-sm text-slate-300">{b.points}</td>
                      <td className="px-4 py-3 text-right text-sm font-semibold text-emerald-300">{formatMoney(b.bonus_amount)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>
      </div>
    </main>
  );
}

function ProfileCard({ operator }: { operator: { id: number; code: string; preferred_city: string | null; active: boolean } }) {
  const setCity = useSetMyPreferredCity();
  const [city, setCityInput] = useState(operator.preferred_city ?? "");
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState(false);

  const save = () => {
    setError(null);
    setOk(false);
    setCity.mutate(
      { operatorId: operator.id, city: city.trim() || null },
      {
        onSuccess: () => setOk(true),
        onError: (e) => setError(e instanceof ApiError && e.status === 403 ? "Выбор района доступен только топ-30% рейтинга текущего квартала" : (e as Error).message),
      },
    );
  };

  return (
    <section className="rounded-2xl border border-slate-800/80 bg-slate-900/55 p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs text-slate-500">Код оператора</p>
          <p className="text-sm font-semibold text-slate-200">{operator.code}</p>
        </div>
        <div className="flex items-end gap-2">
          <label className="block text-xs text-slate-400">
            Предпочитаемый район
            <input value={city} onChange={(e) => setCityInput(e.target.value)} placeholder="напр. Алматы" className="input mt-1 w-44" />
          </label>
          <button onClick={save} disabled={setCity.isPending} className="inline-flex items-center gap-2 rounded-xl border border-emerald-400/20 bg-emerald-400/10 px-3 py-2 text-xs font-semibold text-emerald-200 disabled:opacity-60">
            <MapPin size={13} />Сохранить
          </button>
        </div>
      </div>
      {error && <p className="mt-2 text-xs text-rose-300">{error}</p>}
      {ok && !error && <p className="mt-2 text-xs text-emerald-300">Сохранено.</p>}
    </section>
  );
}

function OrderCard({ order }: { order: { id: number; city: string; area_m2: string; quality: string; price_net: string; status: string; client_name: string | null; notes: string | null } }) {
  const complete = useCompleteMyOrder();
  const upload = useUploadMyPhoto();
  const fileRef = useRef<HTMLInputElement>(null);
  const [photoMsg, setPhotoMsg] = useState<string | null>(null);

  const onFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setPhotoMsg(null);
    upload.mutate(
      { orderId: order.id, file },
      {
        onSuccess: () => setPhotoMsg("Фото загружено"),
        onError: (err) => setPhotoMsg(`Ошибка: ${(err as Error).message}`),
      },
    );
    e.target.value = "";
  };

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 p-5">
      <div>
        <p className="text-sm font-medium text-slate-200">№{order.id}{order.client_name ? ` · ${order.client_name}` : ""} · {order.city}</p>
        <p className="mt-0.5 text-xs text-slate-500">{order.area_m2} м² · {QUALITY_LABEL[order.quality]} · {formatMoney(order.price_net)}</p>
        {order.notes && <p className="mt-1 max-w-md text-xs text-slate-400">{order.notes}</p>}
        <span className="mt-2 inline-flex items-center gap-1.5 rounded-full border border-slate-700 bg-slate-900/60 px-2 py-1 text-[10px] font-semibold text-slate-300">
          {STATUS_LABEL[order.status]}
        </span>
      </div>
      {(order.status === "assigned" || order.status === "in_progress") && (
        <div className="flex flex-col items-end gap-2">
          <div className="flex gap-2">
            <button onClick={() => fileRef.current?.click()} disabled={upload.isPending} className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 px-2.5 py-1.5 text-[11px] text-slate-200 disabled:opacity-50">
              <Camera size={13} />Фото
            </button>
            <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={onFile} />
            <button onClick={() => complete.mutate(order.id)} disabled={complete.isPending} className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-400 px-2.5 py-1.5 text-[11px] font-bold text-slate-950 disabled:opacity-50">
              <CheckCircle2 size={13} />Завершить
            </button>
          </div>
          {photoMsg && <p className="text-[10px] text-slate-400">{photoMsg}</p>}
        </div>
      )}
      {order.status === "done" && <span className="text-xs text-emerald-300">Готово</span>}
    </div>
  );
}

function CabinetScreen({ loading, error, onLogout }: { loading?: boolean; error?: boolean; onLogout?: () => void }) {
  return (
    <main className="grid min-h-screen place-items-center bg-[#0b0f17] text-slate-300">
      <div className="flex flex-col items-center gap-3 text-sm">
        {loading ? <ShieldCheck className="animate-pulse text-emerald-400" /> : <ShieldAlert className="text-rose-300" />}
        {loading ? "Загрузка кабинета…" : "Сессия недействительна, войдите заново."}
        {error && onLogout && (
          <button onClick={onLogout} className="mt-2 rounded-xl border border-slate-700 px-3 py-2 text-xs">Выйти</button>
        )}
      </div>
    </main>
  );
}
