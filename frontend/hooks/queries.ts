"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, api } from "@/lib/api";
import type { Role, Severity } from "@/lib/types";
import { useSession } from "@/store/session";

/** Ключи кэша включают роль: данные одной роли никогда не показываются под другой. */
function useAuth() {
  const token = useSession((s) => s.token);
  const role = useSession((s) => s.role);
  return { token, role, enabled: Boolean(token) };
}

function retry(failureCount: number, error: Error): boolean {
  if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false;
  return failureCount < 2;
}

export function useMe() {
  const { token, role, enabled } = useAuth();
  return useQuery({ queryKey: ["me", role], queryFn: () => api.me(token!), enabled, retry });
}

export function useDiscrepancies(filters: { severity?: Severity; clientId?: number }) {
  const { token, role, enabled } = useAuth();
  return useQuery({
    queryKey: ["discrepancies", role, filters.severity ?? "all", filters.clientId ?? "all"],
    queryFn: () => api.discrepancies(token!, filters),
    enabled,
    retry,
  });
}

export function useClients() {
  const { token, role, enabled } = useAuth();
  return useQuery({ queryKey: ["clients", role], queryFn: () => api.clients(token!), enabled, retry });
}

export function useObjects() {
  const { token, role, enabled } = useAuth();
  return useQuery({ queryKey: ["objects", role], queryFn: () => api.objects(token!), enabled, retry });
}

export function useSchedules() {
  const { token, role, enabled } = useAuth();
  return useQuery({ queryKey: ["schedules", role], queryFn: () => api.schedules(token!), enabled, retry });
}

export function useSwitchRole() {
  const setSession = useSession((s) => s.setSession);
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (role: Role) => ({ role, token: (await api.demoToken(role)).access_token }),
    onSuccess: ({ role, token }) => {
      queryClient.removeQueries(); // кэш прошлой роли больше не нужен
      setSession(role, token);
    },
  });
}
