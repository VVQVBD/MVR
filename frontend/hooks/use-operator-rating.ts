"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { useSession } from "@/store/session";

export type Operator = {
  id: number;
  code: string;
  subcontractor_id: number;
  display_name: string | null;
  preferred_city: string | null;
  active: boolean;
};
export type RankingRow = { operator: Operator; points: number; shifts_done: number; rank: number; bonus: string };
export type Ranking = { quarter_start: string; quarter_end: string; rows: RankingRow[] };
export type OrderStatus = "new" | "assigned" | "in_progress" | "done" | "cancelled";
export type Order = {
  id: number;
  client_company_id: number | null;
  client_name: string | null;
  city: string;
  area_m2: string;
  quality: "surface" | "standard" | "general";
  team_mode: "duo" | "team" | "custom";
  custom_operators_count: number | null;
  notes: string | null;
  price_net: string;
  price_before_discount: string | null;
  status: OrderStatus;
  assigned_operator_id: number | null;
  assigned_by_auto_priority: boolean;
  created_at: string;
};
export type BonusRecord = {
  id: number;
  operator_id: number;
  scope: "month" | "quarter";
  period_start: string;
  period_end: string;
  points: number;
  rank: number;
  total_operators: number;
  bonus_amount: string;
};
export type DiscountStatus = "available" | "used" | "expired";
export type Discount = {
  id: number;
  client_company_id: number;
  pct: string;
  source_rating_id: number;
  status: DiscountStatus;
  used_on_order_id: number | null;
  created_at: string;
  used_at: string | null;
};

/** Та же тихая демо-сессия менеджера, что у экрана «Закрытие месяца» (use-month-close.ts) —
 *  общая внутренняя консоль без отдельного логина. */
async function ensureToken(): Promise<string> {
  const session = useSession.getState();
  if (session.token) return session.token;
  const { access_token } = await api.demoToken("manager");
  session.setSession("manager", access_token);
  return access_token;
}

export function useRanking() {
  return useQuery({
    queryKey: ["operator-ranking"],
    queryFn: async (): Promise<Ranking> => api.ranking(await ensureToken()) as Promise<Ranking>,
  });
}

export function useOperatorsList() {
  return useQuery({
    queryKey: ["operators-list"],
    queryFn: async (): Promise<Operator[]> => api.operators(await ensureToken()) as Promise<Operator[]>,
  });
}

export type ClientCompanyLite = { id: number; code: string; name: string };

export function useClientCompaniesList() {
  return useQuery({
    queryKey: ["client-companies-list"],
    queryFn: async (): Promise<ClientCompanyLite[]> => api.clients(await ensureToken()) as Promise<ClientCompanyLite[]>,
  });
}

export function useOrders(params: { status?: string; city?: string } = {}) {
  return useQuery({
    queryKey: ["orders", params.status ?? "all", params.city ?? "all"],
    queryFn: async (): Promise<Order[]> => api.orders(await ensureToken(), params) as Promise<Order[]>,
  });
}

export function useBonusRecords(scope?: "month" | "quarter") {
  return useQuery({
    queryKey: ["bonus-records", scope ?? "all"],
    queryFn: async (): Promise<BonusRecord[]> => api.bonusRecords(await ensureToken(), scope) as Promise<BonusRecord[]>,
  });
}

export function useCreateOrder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: Record<string, unknown>) => api.createOrder(await ensureToken(), body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["orders"] }),
  });
}

export function useAssignOrder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ orderId, operatorId }: { orderId: number; operatorId: number }) =>
      api.assignOrder(await ensureToken(), orderId, operatorId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["orders"] }),
  });
}

export function useAutoAssignOrder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ orderId, redeemDiscount }: { orderId: number; redeemDiscount?: boolean }) =>
      api.autoAssignOrder(await ensureToken(), orderId, redeemDiscount),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["orders"] });
      qc.invalidateQueries({ queryKey: ["discounts"] });
    },
  });
}

export function useDiscounts(status?: DiscountStatus) {
  return useQuery({
    queryKey: ["discounts", status ?? "all"],
    queryFn: async (): Promise<Discount[]> => api.discounts(await ensureToken(), status) as Promise<Discount[]>,
  });
}

export function useRateOrder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ orderId, body }: { orderId: number; body: Record<string, unknown> }) =>
      api.rateOrder(await ensureToken(), orderId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["discounts"] });
      qc.invalidateQueries({ queryKey: ["operator-ranking"] });
    },
  });
}

export function useCompleteOrder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (orderId: number) => api.completeOrder(await ensureToken(), orderId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["orders"] });
      qc.invalidateQueries({ queryKey: ["operator-ranking"] });
    },
  });
}

export function useCloseBonus() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (scope: "month" | "quarter") => api.closeBonus(await ensureToken(), scope),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["bonus-records"] }),
  });
}
