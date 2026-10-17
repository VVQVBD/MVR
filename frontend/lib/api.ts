import type { ClientCompany, Dispute, FacilityObject, Me, Role, Schedule, Severity, Source, Subcontractor, Token } from "./types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, token: string | null, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");

  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, `Сервер API недоступен (${API_URL})`);
  }
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body: unknown = await response.json();
      if (body && typeof body === "object" && "detail" in body) {
        const d = (body as { detail: unknown }).detail;
        detail = typeof d === "string" ? d : JSON.stringify(d);
      }
    } catch {
      /* тело не JSON — оставляем statusText */
    }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

export const api = {
  demoToken: (role: Role) =>
    request<Token>("/auth/demo-token", null, { method: "POST", body: JSON.stringify({ role }) }),
  /** Обычный вход по email+паролю (для операторов — демо-входа у них нет, см. scripts.create_user). */
  login: async (email: string, password: string): Promise<Token> => {
    const form = new URLSearchParams();
    form.set("username", email);
    form.set("password", password);
    let response: Response;
    try {
      response = await fetch(`${API_URL}/auth/token`, { method: "POST", body: form });
    } catch {
      throw new ApiError(0, `Сервер API недоступен (${API_URL})`);
    }
    if (!response.ok) {
      let detail = response.statusText;
      try {
        const body: unknown = await response.json();
        if (body && typeof body === "object" && "detail" in body) {
          const d = (body as { detail: unknown }).detail;
          detail = typeof d === "string" ? d : JSON.stringify(d);
        }
      } catch {
        /* тело не JSON */
      }
      throw new ApiError(response.status, detail);
    }
    return (await response.json()) as Token;
  },
  me: (token: string) => request<Me>("/auth/me", token),
  discrepancies: (token: string, filters: { severity?: Severity; clientId?: number }) => {
    const q = new URLSearchParams();
    if (filters.severity) q.set("severity", filters.severity);
    if (filters.clientId) q.set("client_id", String(filters.clientId));
    const qs = q.toString();
    return request<Dispute[]>(`/api/v1/contracts/discrepancies${qs ? `?${qs}` : ""}`, token);
  },
  clients: (token: string) => request<ClientCompany[]>("/clients", token),
  subcontractors: (token: string) => request<Subcontractor[]>("/subcontractors", token),
  objects: (token: string) => request<FacilityObject[]>("/objects", token),
  schedules: (token: string) => request<Schedule[]>("/schedules", token),
  monthClose: (token: string, period: string) =>
    request<unknown>(`/api/v1/ops/month-close?period=${period}`, token),

  // ---------- Пилот рейтинга операторов + разовые заявки ----------
  ranking: (token: string, asOf?: string) =>
    request<unknown>(`/api/v1/operators/ranking${asOf ? `?as_of=${asOf}` : ""}`, token),
  operators: (token: string) => request<unknown[]>("/api/v1/operators", token),
  orders: (token: string, params: { status?: string; city?: string } = {}) => {
    const q = new URLSearchParams();
    if (params.status) q.set("status", params.status);
    if (params.city) q.set("city", params.city);
    const qs = q.toString();
    return request<unknown[]>(`/api/v1/orders${qs ? `?${qs}` : ""}`, token);
  },
  createOrder: (token: string, body: Record<string, unknown>) =>
    request<unknown>("/api/v1/orders", token, { method: "POST", body: JSON.stringify(body) }),
  assignOrder: (token: string, orderId: number, operatorId: number) =>
    request<unknown>(`/api/v1/orders/${orderId}/assign`, token, {
      method: "POST",
      body: JSON.stringify({ operator_id: operatorId }),
    }),
  autoAssignOrder: (token: string, orderId: number, redeemDiscount = false) =>
    request<unknown>(`/api/v1/orders/${orderId}/auto-assign?redeem_discount=${redeemDiscount}`, token, {
      method: "POST",
    }),
  completeOrder: (token: string, orderId: number) =>
    request<unknown>(`/api/v1/orders/${orderId}/complete`, token, { method: "POST" }),
  closeBonus: (token: string, scope: "month" | "quarter", asOf?: string) =>
    request<unknown[]>("/api/v1/operators/bonus/close", token, {
      method: "POST",
      body: JSON.stringify({ scope, as_of: asOf }),
    }),
  bonusRecords: (token: string, scope?: "month" | "quarter") =>
    request<unknown[]>(`/api/v1/operators/bonus${scope ? `?scope=${scope}` : ""}`, token),
  rateOrder: (token: string, orderId: number, body: Record<string, unknown>) =>
    request<unknown>(`/api/v1/orders/${orderId}/rating`, token, { method: "POST", body: JSON.stringify(body) }),
  discounts: (token: string, status?: string) =>
    request<unknown[]>(`/api/v1/discounts${status ? `?status=${status}` : ""}`, token),
  setPreferredCity: (token: string, operatorId: number, city: string | null) =>
    request<unknown>(`/api/v1/operators/${operatorId}/preferred-city`, token, {
      method: "PATCH",
      body: JSON.stringify({ preferred_city: city }),
    }),
  orderPhotos: (token: string, orderId: number) => request<unknown[]>(`/api/v1/orders/${orderId}/photos`, token),
  uploadOrderPhoto: async (token: string, orderId: number, file: File): Promise<unknown> => {
    const form = new FormData();
    form.set("file", file);
    let response: Response;
    try {
      response = await fetch(`${API_URL}/api/v1/orders/${orderId}/photos`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: form,
      });
    } catch {
      throw new ApiError(0, `Сервер API недоступен (${API_URL})`);
    }
    if (!response.ok) {
      let detail = response.statusText;
      try {
        const body: unknown = await response.json();
        if (body && typeof body === "object" && "detail" in body) {
          const d = (body as { detail: unknown }).detail;
          detail = typeof d === "string" ? d : JSON.stringify(d);
        }
      } catch {
        /* тело не JSON */
      }
      throw new ApiError(response.status, detail);
    }
    return response.json();
  },
};

// ---------- форматирование ----------
const kzt = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 });
const area = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 1 });

export function formatKzt(v: string | null | undefined): string {
  return v == null ? "—" : `${kzt.format(Number(v))} ₸`;
}

export function formatArea(v: string | null | undefined): string {
  return v == null ? "—" : `${area.format(Number(v))} м²`;
}

/** «стр. 2» / «стр. 1, 3, 4» / «лист «Объекты», строка 3». */
export function formatSourceLocation(s: Source): string {
  const parts: string[] = [];
  if (s.page != null) parts.push(`стр. ${s.page}`);
  if (s.pages?.length) parts.push(`стр. ${s.pages.join(", ")}`);
  if (s.sheet) parts.push(`лист «${s.sheet}»`);
  if (s.row != null) parts.push(`строка ${s.row}`);
  return parts.join(", ");
}

export function sourceKind(file: string): "pdf" | "xlsx" | "json" | "other" {
  const ext = file.split(".").pop()?.toLowerCase();
  if (ext === "pdf") return "pdf";
  if (ext === "xlsx" || ext === "xls") return "xlsx";
  if (ext === "json") return "json";
  return "other";
}
