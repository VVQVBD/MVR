"use client";

import { useQuery } from "@tanstack/react-query";

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
  unlinkedShifts: { id: string }[];
  disputes: Dispute[];
};
export type ClientRemark = { id: string; description: string; detectedAt: string; dueAt: string; resolvedAt: string | null; status: "open" | "resolved"; sources: SourceRef[] };
export type Dispute = { id: string; severity: "low" | "medium" | "high"; topic: string; description: string; request: string; status: string; sources: SourceRef[] };
export type Kpi = { revenue: number; subcontractorPayout: number; marginBeforeOperatorPayout: number; discrepancies: number; operatorPayout: null; operatorPayoutStatus: string };

export function useMonthClose() {
  return useQuery({
    queryKey: ["month-close", "2026-09"],
    queryFn: async (): Promise<MonthCloseData> => {
      const response = await fetch("/data/month-close-september-2026.json");
      if (!response.ok) throw new Error("Не удалось загрузить данные закрытия месяца");
      return response.json();
    },
  });
}
