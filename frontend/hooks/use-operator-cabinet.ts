"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { Me } from "@/lib/types";
import { useOperatorSession } from "@/store/operator-session";
import type { BonusRecord, Operator, Order } from "./use-operator-rating";

export function useMyProfile() {
  const token = useOperatorSession((s) => s.token);
  return useQuery({
    queryKey: ["operator-me", token],
    queryFn: async (): Promise<Me> => api.me(token!),
    enabled: Boolean(token),
    retry: false,
  });
}

export function useMyOperator(operatorId: number | undefined) {
  const token = useOperatorSession((s) => s.token);
  return useQuery({
    queryKey: ["operator-self", token, operatorId],
    queryFn: async (): Promise<Operator | undefined> => {
      const list = (await api.operators(token!)) as Operator[];
      return list.find((o) => o.id === operatorId);
    },
    enabled: Boolean(token) && operatorId != null,
  });
}

export function useMyOrders() {
  const token = useOperatorSession((s) => s.token);
  return useQuery({
    queryKey: ["operator-orders", token],
    queryFn: async (): Promise<Order[]> => api.orders(token!) as Promise<Order[]>,
    enabled: Boolean(token),
  });
}

export function useMyBonus() {
  const token = useOperatorSession((s) => s.token);
  return useQuery({
    queryKey: ["operator-bonus", token],
    queryFn: async (): Promise<BonusRecord[]> => api.bonusRecords(token!) as Promise<BonusRecord[]>,
    enabled: Boolean(token),
  });
}

export function useCompleteMyOrder() {
  const token = useOperatorSession((s) => s.token);
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (orderId: number) => api.completeOrder(token!, orderId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["operator-orders"] }),
  });
}

export function useUploadMyPhoto() {
  const token = useOperatorSession((s) => s.token);
  return useMutation({
    mutationFn: ({ orderId, file }: { orderId: number; file: File }) => api.uploadOrderPhoto(token!, orderId, file),
  });
}

export function useSetMyPreferredCity() {
  const token = useOperatorSession((s) => s.token);
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ operatorId, city }: { operatorId: number; city: string | null }) =>
      api.setPreferredCity(token!, operatorId, city),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["operator-self"] }),
  });
}
