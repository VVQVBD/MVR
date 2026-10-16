export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Severity = "low" | "medium" | "high" | "critical";

export interface Source {
  id: number;
  file: string;
  page?: number | null;
  pages?: number[] | null;
  sheet?: string | null;
  row?: number | null;
  quote?: string | null;
  note?: string | null;
}

export interface Dispute {
  id: string;
  client_name?: string | null;
  topic: string;
  severity: Severity;
  issue: string;
  ask?: string | null;
  status: string;
  sources: Source[];
}

export interface Client {
  id: number;
  code: string;
  name: string;
}

export type Role = "executive" | "manager" | "subcontractor" | "client";

export interface Me {
  id: number;
  email: string;
  role: Role;
}

export interface Schedule {
  id: number;
  facility_object_id: number;
  period_month: string;
  operators_count?: number | null;
  shift_start?: string | null;
  shift_end?: string | null;
  days_pattern?: string | null;
}

export function formatShift(s: Schedule): string {
  const parts = [];
  if (s.operators_count) parts.push(`${s.operators_count} ОПУ`);
  if (s.shift_start && s.shift_end) parts.push(`${s.shift_start.slice(0, 5)}–${s.shift_end.slice(0, 5)}`);
  if (s.days_pattern) parts.push(s.days_pattern);
  return parts.length ? parts.join(" ") : "часы не указаны";
}

// Для субподрядчика API не отдаёт цены, НДС, договор и клиента — эти поля отсутствуют.
export interface FacilityObject {
  id: number;
  client_company_id?: number;
  code: string;
  name: string;
  city: string;
  address?: string | null;
  area_m2?: string | null;
  services?: string | null;
  monthly_tariff?: string | null;
  vat_note?: string | null;
  subcontractor?: { id: number; code?: string | null; name: string } | null;
}

export interface Finding {
  kind: string;
  severity: Severity;
  client_code: string;
  contract_number?: string | null;
  message: string;
  difference?: string | null;
}

export async function login(email: string, password: string): Promise<string> {
  const body = new URLSearchParams({ username: email, password });
  const r = await fetch(`${API_URL}/auth/token`, { method: "POST", body });
  if (!r.ok) throw new Error("Неверный логин или пароль");
  return (await r.json()).access_token;
}

export async function get<T>(path: string, token: string): Promise<T> {
  const r = await fetch(`${API_URL}${path}`, { headers: { Authorization: `Bearer ${token}` } });
  if (r.status === 401) throw new Error("unauthorized");
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}

export function formatSource(s: Source): string {
  const parts = [s.file];
  if (s.sheet) parts.push(`лист «${s.sheet}»`);
  if (s.page != null) parts.push(`стр. ${s.page}`);
  if (s.pages?.length) parts.push(`стр. ${s.pages.join(", ")}`);
  if (s.row != null) parts.push(`строка ${s.row}`);
  return parts.join(", ");
}

const kzt = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 });

export function formatMoney(v?: string | null): string {
  return v == null ? "—" : `${kzt.format(Number(v))} ₸`;
}
