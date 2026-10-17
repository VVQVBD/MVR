"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { useSession } from "@/store/session";

export type SourceRef = { file: string; sheet?: string; row?: number; page?: number | number[]; field?: string };
export type AuditedValue<T> = { value: T; sources: SourceRef[]; calculation?: string };
export type ReconciliationRow = {
  id: string; client: string; zone: string; subcontractor: string | null; vatBasis: string;
  contract: AuditedValue<string>; revenue: AuditedValue<number>; subcontractorPayout: AuditedValue<number>;
  operatorPayout: AuditedValue<number | null>; marginBeforeOperatorPayout: AuditedValue<number>;
  anomalies: { code: string; severity: string; message: string; sources: SourceRef[] }[]; status: "closed" | "review";
};
export type MonthCloseData = {
  period: string; currency: string; sourcePolicy: string;
  objects: { id: "nord" | "samal-city"; title: string; reconciliation: ReconciliationRow[]; clientRemarks: ClientRemark[]; kpi: Kpi }[];
  unlinkedShiftsCount: number;
  disputes: Dispute[];
};
export type ClientRemark = { id: string; description: string; detectedAt: string; dueAt: string; resolvedAt: string | null; status: "open" | "resolved"; sources: SourceRef[] };
export type Dispute = { id: string; severity: "low" | "medium" | "high"; topic: string; description: string; request: string | null; status: string; sources: SourceRef[] };
export type Kpi = { revenue: number; subcontractorPayout: number; marginBeforeOperatorPayout: number; discrepancies: number; operatorPayout: null; operatorPayoutStatus: string };

const PERIOD = "2026-09-01"; // первое число месяца закрытия, как ждёт бекенд

// Деньги бекенд отдаёт строками (Decimal), чтобы не терять копейки в JSON — здесь переводим
// в number, потому что остальной экран уже верстался под числа (формат, суммирование KPI).
function num(value: string | number | null): number | null {
  return value === null ? null : Number(value);
}
function money<T extends string | number | null>(a: { value: T; sources: SourceRef[]; calculation?: string }): AuditedValue<number> {
  return { ...a, value: num(a.value as string | number | null) as number };
}

type RawReconciliationRow = Omit<ReconciliationRow, "revenue" | "subcontractorPayout" | "operatorPayout" | "marginBeforeOperatorPayout"> & {
  revenue: { value: string; sources: SourceRef[]; calculation?: string };
  subcontractorPayout: { value: string; sources: SourceRef[]; calculation?: string };
  operatorPayout: { value: string | null; sources: SourceRef[]; calculation?: string };
  marginBeforeOperatorPayout: { value: string; sources: SourceRef[]; calculation?: string };
};
type RawKpi = Omit<Kpi, "revenue" | "subcontractorPayout" | "marginBeforeOperatorPayout"> & {
  revenue: string; subcontractorPayout: string; marginBeforeOperatorPayout: string;
};
type RawMonthClose = Omit<MonthCloseData, "objects"> & {
  objects: { id: "nord" | "samal-city"; title: string; reconciliation: RawReconciliationRow[]; clientRemarks: ClientRemark[]; kpi: RawKpi }[];
};

function mapRow(row: RawReconciliationRow): ReconciliationRow {
  return {
    ...row,
    revenue: money(row.revenue),
    subcontractorPayout: money(row.subcontractorPayout),
    operatorPayout: money(row.operatorPayout),
    marginBeforeOperatorPayout: money(row.marginBeforeOperatorPayout),
  };
}

function mapKpi(kpi: RawKpi): Kpi {
  return {
    ...kpi,
    revenue: Number(kpi.revenue),
    subcontractorPayout: Number(kpi.subcontractorPayout),
    marginBeforeOperatorPayout: Number(kpi.marginBeforeOperatorPayout),
  };
}

/** Токен берётся из общей сессии (как у остальных экранов); если его ещё нет — тихо
 *  входим демо-пользователем «менеджер». Эта консоль внутренняя, отдельного логина у неё нет. */
async function ensureToken(): Promise<string> {
  const session = useSession.getState();
  if (session.token) return session.token;
  const { access_token } = await api.demoToken("manager");
  session.setSession("manager", access_token);
  return access_token;
}

export function useMonthClose() {
  return useQuery({
    queryKey: ["month-close", PERIOD],
    queryFn: async (): Promise<MonthCloseData> => {
      const token = await ensureToken();
      const raw = (await api.monthClose(token, PERIOD)) as RawMonthClose;
      return {
        ...raw,
        objects: raw.objects.map((o) => ({ ...o, reconciliation: o.reconciliation.map(mapRow), kpi: mapKpi(o.kpi) })),
      };
    },
  });
}
