// Типы ответов API IC Group. Поля и литералы — как в backend/app/schemas.py.

export type Role = "executive" | "manager" | "client" | "subcontractor";
export type Severity = "low" | "medium" | "high";
export type DisputeStatus = "open" | "resolved" | "rejected";
export type VatBasis = "included" | "excluded" | "unknown";

/** Деньги и площади приходят строками (Decimal) — чтобы не терять копейки. */
export type DecimalString = string;

export interface Me {
  id: number;
  email: string;
  role: Role;
  client_company_id: number | null;
  subcontractor_id: number | null;
}

export interface Source {
  id: number;
  file: string;
  page: number | null;
  pages: number[] | null;
  sheet: string | null;
  row: number | null;
  quote: string | null;
  note: string | null;
}

export interface Dispute {
  id: string; // Q-01
  client_company_id: number | null;
  client_name: string | null;
  severity: Severity;
  topic: string;
  issue: string;
  ask: string | null;
  status: DisputeStatus;
  resolution: string | null;
  resolved_at: string | null;
  sources: Source[];
}

export interface ClientCompany {
  id: number;
  code: string;
  name: string;
  bin: string | null;
  notes: string | null;
}

export interface Subcontractor {
  id: number;
  code: string;
  name: string;
  bin: string | null;
}

/** Объект глазами субподрядчика: без цен, НДС, договора и клиента. */
export interface FacilityObjectBasic {
  id: number;
  code: string;
  city: string;
  name: string;
  area_m2: DecimalString | null;
  external_area_m2: DecimalString | null;
  facade_area_m2: DecimalString | null;
  services: string | null;
  subcontractor_id: number | null;
}

/** Полный объект — для руководителя, менеджера и клиента. */
export interface FacilityObjectFull extends FacilityObjectBasic {
  client_company_id: number;
  contract_id: number;
  addendum_id: number | null;
  pricing_group: string | null;
  monthly_tariff: DecimalString | null;
  price_per_m2: DecimalString | null;
  vat_basis: VatBasis;
  vat_rate: DecimalString | null;
  vat_note: string | null;
  subcontractor: Subcontractor | null;
}

export type FacilityObject = FacilityObjectBasic | FacilityObjectFull;

export function hasPricing(o: FacilityObject): o is FacilityObjectFull {
  return "contract_id" in o;
}

export interface Schedule {
  id: number;
  facility_object_id: number;
  subcontractor_id: number;
  period_month: string; // YYYY-MM-01
  operators_count: number | null;
  shift_start: string | null;
  shift_end: string | null;
  days_pattern: string | null;
  note: string | null;
}

export interface Token {
  access_token: string;
  token_type: string;
}
