-- Сгенерировано: DATABASE_URL=postgresql+psycopg://... alembic upgrade head --sql
-- Полная схема IC Group + RLS для Supabase SQL Editor. Источник истины — migrations/versions.
BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001

CREATE TABLE client_companies (
    id SERIAL NOT NULL, 
    code VARCHAR(64) NOT NULL, 
    name VARCHAR(255) NOT NULL, 
    bin VARCHAR(12), 
    notes TEXT, 
    CONSTRAINT pk_client_companies PRIMARY KEY (id), 
    CONSTRAINT uq_client_companies_code UNIQUE (code)
);

CREATE TABLE document_source_references (
    id SERIAL NOT NULL, 
    file VARCHAR(500) NOT NULL, 
    page INTEGER, 
    pages JSONB, 
    sheet VARCHAR(100), 
    row INTEGER, 
    quote TEXT, 
    note TEXT, 
    CONSTRAINT pk_document_source_references PRIMARY KEY (id)
);

CREATE INDEX ix_document_source_references_file ON document_source_references (file);

CREATE TABLE subcontractors (
    id SERIAL NOT NULL, 
    code VARCHAR(10) NOT NULL, 
    name VARCHAR(255) NOT NULL, 
    bin VARCHAR(12), 
    CONSTRAINT pk_subcontractors PRIMARY KEY (id), 
    CONSTRAINT uq_subcontractors_code UNIQUE (code)
);

CREATE TABLE contracts (
    id SERIAL NOT NULL, 
    client_company_id INTEGER NOT NULL, 
    number VARCHAR(100) NOT NULL, 
    signed_at DATE, 
    valid_from DATE, 
    valid_to DATE, 
    renewal VARCHAR(20), 
    renewal_note TEXT, 
    status VARCHAR(20) NOT NULL, 
    status_as_of DATE, 
    status_note TEXT, 
    currency VARCHAR(3) NOT NULL, 
    vat_basis VARCHAR(10) NOT NULL, 
    vat_rate NUMERIC(5, 2), 
    vat_note TEXT, 
    stated_monthly_total NUMERIC(18, 2), 
    terms JSONB, 
    raw_text TEXT, 
    injection_flags JSONB, 
    CONSTRAINT pk_contracts PRIMARY KEY (id), 
    CONSTRAINT ck_contracts_renewal CHECK (renewal IN ('auto_annual', 'by_agreement', 'none')), 
    CONSTRAINT ck_contracts_status CHECK (status IN ('active', 'auto_renewed', 'expiring', 'expired', 'unknown')), 
    CONSTRAINT ck_contracts_vat_basis CHECK (vat_basis IN ('included', 'excluded', 'unknown')), 
    CONSTRAINT fk_contracts_client_company_id_client_companies FOREIGN KEY(client_company_id) REFERENCES client_companies (id) ON DELETE CASCADE, 
    CONSTRAINT uq_contracts_company_number UNIQUE (client_company_id, number)
);

CREATE INDEX ix_contracts_client_company_id ON contracts (client_company_id);

CREATE TABLE users (
    id SERIAL NOT NULL, 
    auth_user_id UUID, 
    email VARCHAR(255) NOT NULL, 
    password_hash VARCHAR(255), 
    role VARCHAR(20) NOT NULL, 
    client_company_id INTEGER, 
    subcontractor_id INTEGER, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_users PRIMARY KEY (id), 
    CONSTRAINT ck_users_client_has_company CHECK (role <> 'client' OR client_company_id IS NOT NULL), 
    CONSTRAINT ck_users_subcontractor_has_id CHECK (role <> 'subcontractor' OR subcontractor_id IS NOT NULL), 
    CONSTRAINT ck_users_role CHECK (role IN ('executive', 'manager', 'subcontractor', 'client')), 
    CONSTRAINT fk_users_client_company_id_client_companies FOREIGN KEY(client_company_id) REFERENCES client_companies (id) ON DELETE CASCADE, 
    CONSTRAINT fk_users_subcontractor_id_subcontractors FOREIGN KEY(subcontractor_id) REFERENCES subcontractors (id) ON DELETE CASCADE, 
    CONSTRAINT uq_users_auth_user_id UNIQUE (auth_user_id)
);

CREATE UNIQUE INDEX ix_users_email ON users (email);

CREATE TABLE billing_acts (
    id SERIAL NOT NULL, 
    kind VARCHAR(20) NOT NULL, 
    number VARCHAR(50), 
    period_month DATE NOT NULL, 
    client_company_id INTEGER, 
    contract_id INTEGER, 
    subcontractor_id INTEGER, 
    status VARCHAR(10) NOT NULL, 
    amount_net NUMERIC(18, 2), 
    vat_rate NUMERIC(5, 2), 
    vat_amount NUMERIC(18, 2), 
    amount_gross NUMERIC(18, 2), 
    source_id INTEGER, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_billing_acts PRIMARY KEY (id), 
    CONSTRAINT ck_billing_acts_avr_has_client CHECK (kind <> 'client_avr' OR client_company_id IS NOT NULL), 
    CONSTRAINT ck_billing_acts_act_has_subcontractor CHECK (kind <> 'subcontractor_act' OR subcontractor_id IS NOT NULL), 
    CONSTRAINT ck_billing_acts_kind CHECK (kind IN ('client_avr', 'subcontractor_act')), 
    CONSTRAINT ck_billing_acts_status CHECK (status IN ('draft', 'issued', 'signed', 'disputed')), 
    CONSTRAINT fk_billing_acts_client_company_id_client_companies FOREIGN KEY(client_company_id) REFERENCES client_companies (id) ON DELETE CASCADE, 
    CONSTRAINT fk_billing_acts_contract_id_contracts FOREIGN KEY(contract_id) REFERENCES contracts (id) ON DELETE SET NULL, 
    CONSTRAINT fk_billing_acts_source_id_document_source_references FOREIGN KEY(source_id) REFERENCES document_source_references (id) ON DELETE SET NULL, 
    CONSTRAINT fk_billing_acts_subcontractor_id_subcontractors FOREIGN KEY(subcontractor_id) REFERENCES subcontractors (id) ON DELETE CASCADE
);

CREATE INDEX ix_billing_acts_client_company_id ON billing_acts (client_company_id);

CREATE INDEX ix_billing_acts_subcontractor_id ON billing_acts (subcontractor_id);

CREATE TABLE contract_addenda (
    id SERIAL NOT NULL, 
    contract_id INTEGER NOT NULL, 
    number VARCHAR(50) NOT NULL, 
    signed_at DATE, 
    effective_from DATE, 
    summary TEXT, 
    vat_basis VARCHAR(10) NOT NULL, 
    vat_rate NUMERIC(5, 2), 
    stated_monthly_total NUMERIC(18, 2), 
    raw_text TEXT, 
    injection_flags JSONB, 
    CONSTRAINT pk_contract_addenda PRIMARY KEY (id), 
    CONSTRAINT ck_contract_addenda_vat_basis CHECK (vat_basis IN ('included', 'excluded', 'unknown')), 
    CONSTRAINT fk_contract_addenda_contract_id_contracts FOREIGN KEY(contract_id) REFERENCES contracts (id) ON DELETE CASCADE, 
    CONSTRAINT uq_contract_addenda_contract_number UNIQUE (contract_id, number)
);

CREATE INDEX ix_contract_addenda_contract_id ON contract_addenda (contract_id);

CREATE TABLE contract_sources (
    contract_id INTEGER NOT NULL, 
    source_id INTEGER NOT NULL, 
    CONSTRAINT pk_contract_sources PRIMARY KEY (contract_id, source_id), 
    CONSTRAINT fk_contract_sources_contract_id_contracts FOREIGN KEY(contract_id) REFERENCES contracts (id) ON DELETE CASCADE, 
    CONSTRAINT fk_contract_sources_source_id_document_source_references FOREIGN KEY(source_id) REFERENCES document_source_references (id) ON DELETE CASCADE
);

CREATE TABLE disputed_conditions (
    id VARCHAR(10) NOT NULL, 
    client_company_id INTEGER, 
    severity VARCHAR(10) NOT NULL, 
    topic VARCHAR(255) NOT NULL, 
    issue TEXT NOT NULL, 
    ask TEXT, 
    status VARCHAR(10) NOT NULL, 
    resolution TEXT, 
    resolved_by_id INTEGER, 
    resolved_at TIMESTAMP WITH TIME ZONE, 
    CONSTRAINT pk_disputed_conditions PRIMARY KEY (id), 
    CONSTRAINT ck_disputed_conditions_severity CHECK (severity IN ('low', 'medium', 'high')), 
    CONSTRAINT ck_disputed_conditions_status CHECK (status IN ('open', 'resolved', 'rejected')), 
    CONSTRAINT fk_disputed_conditions_client_company_id_client_companies FOREIGN KEY(client_company_id) REFERENCES client_companies (id) ON DELETE SET NULL, 
    CONSTRAINT fk_disputed_conditions_resolved_by_id_users FOREIGN KEY(resolved_by_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_disputed_conditions_client_company_id ON disputed_conditions (client_company_id);

CREATE INDEX ix_disputed_conditions_severity ON disputed_conditions (severity);

CREATE TABLE addendum_sources (
    addendum_id INTEGER NOT NULL, 
    source_id INTEGER NOT NULL, 
    CONSTRAINT pk_addendum_sources PRIMARY KEY (addendum_id, source_id), 
    CONSTRAINT fk_addendum_sources_addendum_id_contract_addenda FOREIGN KEY(addendum_id) REFERENCES contract_addenda (id) ON DELETE CASCADE, 
    CONSTRAINT fk_addendum_sources_source_id_document_source_references FOREIGN KEY(source_id) REFERENCES document_source_references (id) ON DELETE CASCADE
);

CREATE TABLE dispute_sources (
    dispute_id VARCHAR(10) NOT NULL, 
    source_id INTEGER NOT NULL, 
    CONSTRAINT pk_dispute_sources PRIMARY KEY (dispute_id, source_id), 
    CONSTRAINT fk_dispute_sources_dispute_id_disputed_conditions FOREIGN KEY(dispute_id) REFERENCES disputed_conditions (id) ON DELETE CASCADE, 
    CONSTRAINT fk_dispute_sources_source_id_document_source_references FOREIGN KEY(source_id) REFERENCES document_source_references (id) ON DELETE CASCADE
);

CREATE TABLE facility_objects (
    id SERIAL NOT NULL, 
    code VARCHAR(64) NOT NULL, 
    client_company_id INTEGER NOT NULL, 
    contract_id INTEGER NOT NULL, 
    addendum_id INTEGER, 
    city VARCHAR(100) NOT NULL, 
    name VARCHAR(500) NOT NULL, 
    area_m2 NUMERIC(12, 2), 
    external_area_m2 NUMERIC(12, 2), 
    facade_area_m2 NUMERIC(12, 2), 
    pricing_group VARCHAR(10), 
    services TEXT, 
    monthly_tariff NUMERIC(18, 2), 
    price_per_m2 NUMERIC(18, 2), 
    vat_basis VARCHAR(10) NOT NULL, 
    vat_rate NUMERIC(5, 2), 
    vat_note TEXT, 
    subcontractor_id INTEGER, 
    CONSTRAINT pk_facility_objects PRIMARY KEY (id), 
    CONSTRAINT ck_facility_objects_vat_basis CHECK (vat_basis IN ('included', 'excluded', 'unknown')), 
    CONSTRAINT ck_facility_objects_area_non_negative CHECK (area_m2 IS NULL OR area_m2 >= 0), 
    CONSTRAINT ck_facility_objects_tariff_non_negative CHECK (monthly_tariff IS NULL OR monthly_tariff >= 0), 
    CONSTRAINT fk_facility_objects_addendum_id_contract_addenda FOREIGN KEY(addendum_id) REFERENCES contract_addenda (id) ON DELETE SET NULL, 
    CONSTRAINT fk_facility_objects_client_company_id_client_companies FOREIGN KEY(client_company_id) REFERENCES client_companies (id) ON DELETE CASCADE, 
    CONSTRAINT fk_facility_objects_contract_id_contracts FOREIGN KEY(contract_id) REFERENCES contracts (id) ON DELETE CASCADE, 
    CONSTRAINT fk_facility_objects_subcontractor_id_subcontractors FOREIGN KEY(subcontractor_id) REFERENCES subcontractors (id) ON DELETE SET NULL, 
    CONSTRAINT uq_facility_objects_code UNIQUE (code)
);

CREATE INDEX ix_facility_objects_city ON facility_objects (city);

CREATE INDEX ix_facility_objects_client_company_id ON facility_objects (client_company_id);

CREATE INDEX ix_facility_objects_contract_id ON facility_objects (contract_id);

CREATE INDEX ix_facility_objects_subcontractor_id ON facility_objects (subcontractor_id);

CREATE TABLE billing_act_lines (
    id SERIAL NOT NULL, 
    act_id INTEGER NOT NULL, 
    facility_object_id INTEGER, 
    description TEXT NOT NULL, 
    amount_net NUMERIC(18, 2) NOT NULL, 
    note TEXT, 
    CONSTRAINT pk_billing_act_lines PRIMARY KEY (id), 
    CONSTRAINT fk_billing_act_lines_act_id_billing_acts FOREIGN KEY(act_id) REFERENCES billing_acts (id) ON DELETE CASCADE, 
    CONSTRAINT fk_billing_act_lines_facility_object_id_facility_objects FOREIGN KEY(facility_object_id) REFERENCES facility_objects (id) ON DELETE SET NULL
);

CREATE INDEX ix_billing_act_lines_act_id ON billing_act_lines (act_id);

CREATE TABLE facility_sources (
    facility_object_id INTEGER NOT NULL, 
    source_id INTEGER NOT NULL, 
    CONSTRAINT pk_facility_sources PRIMARY KEY (facility_object_id, source_id), 
    CONSTRAINT fk_facility_sources_facility_object_id_facility_objects FOREIGN KEY(facility_object_id) REFERENCES facility_objects (id) ON DELETE CASCADE, 
    CONSTRAINT fk_facility_sources_source_id_document_source_references FOREIGN KEY(source_id) REFERENCES document_source_references (id) ON DELETE CASCADE
);

CREATE TABLE shift_schedules (
    id SERIAL NOT NULL, 
    facility_object_id INTEGER NOT NULL, 
    subcontractor_id INTEGER NOT NULL, 
    period_month DATE NOT NULL, 
    operators_count INTEGER, 
    shift_start TIME WITHOUT TIME ZONE, 
    shift_end TIME WITHOUT TIME ZONE, 
    days_pattern VARCHAR(50), 
    note TEXT, 
    source_id INTEGER, 
    CONSTRAINT pk_shift_schedules PRIMARY KEY (id), 
    CONSTRAINT ck_shift_schedules_operators_positive CHECK (operators_count IS NULL OR operators_count > 0), 
    CONSTRAINT fk_shift_schedules_facility_object_id_facility_objects FOREIGN KEY(facility_object_id) REFERENCES facility_objects (id) ON DELETE CASCADE, 
    CONSTRAINT fk_shift_schedules_source_id_document_source_references FOREIGN KEY(source_id) REFERENCES document_source_references (id) ON DELETE SET NULL, 
    CONSTRAINT fk_shift_schedules_subcontractor_id_subcontractors FOREIGN KEY(subcontractor_id) REFERENCES subcontractors (id) ON DELETE CASCADE
);

CREATE INDEX ix_shift_schedules_facility_object_id ON shift_schedules (facility_object_id);

CREATE INDEX ix_shift_schedules_subcontractor_id ON shift_schedules (subcontractor_id);

CREATE TABLE shift_reports (
    id SERIAL NOT NULL, 
    schedule_id INTEGER NOT NULL, 
    work_date DATE NOT NULL, 
    operator_code VARCHAR(32) NOT NULL, 
    status VARCHAR(10) NOT NULL, 
    started_at TIME WITHOUT TIME ZONE, 
    ended_at TIME WITHOUT TIME ZONE, 
    hours NUMERIC(5, 2), 
    note TEXT, 
    reported_by_id INTEGER, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_shift_reports PRIMARY KEY (id), 
    CONSTRAINT ck_shift_reports_status CHECK (status IN ('done', 'partial', 'missed', 'replaced')), 
    CONSTRAINT ck_shift_reports_hours_range CHECK (hours IS NULL OR (hours >= 0 AND hours <= 24)), 
    CONSTRAINT fk_shift_reports_reported_by_id_users FOREIGN KEY(reported_by_id) REFERENCES users (id) ON DELETE SET NULL, 
    CONSTRAINT fk_shift_reports_schedule_id_shift_schedules FOREIGN KEY(schedule_id) REFERENCES shift_schedules (id) ON DELETE CASCADE, 
    CONSTRAINT uq_shift_reports_day_operator UNIQUE (schedule_id, work_date, operator_code)
);

CREATE INDEX ix_shift_reports_schedule_id ON shift_reports (schedule_id);

INSERT INTO alembic_version (version_num) VALUES ('0001') RETURNING alembic_version.version_num;

-- Running upgrade 0001 -> 0002

-- Row Level Security для IC Group (Supabase / PostgreSQL 15+).
--
-- Кто есть кто: public.users.auth_user_id = auth.uid() (Supabase Auth).
--   executive, manager — сквозной доступ ко всему;
--   client            — только строки своей компании (users.client_company_id);
--   subcontractor     — только объекты, на которые он назначен в графике смен (shift_schedules),
--                       свои графики, отметки смен и свои акты.
--                       С миграции 0003 объекты — только через вью subcontractor_facility_objects,
--                       без цен и НДС клиента (db/rls_0003_subcontractor_view.sql).
-- Роль anon не получает ни одной политики — без входа данных не видно.
-- Подключения владельца таблиц и service_role RLS обходят: так работает FastAPI-бекенд,
-- где те же правила продублированы в app/access.py.
--
-- Скрипт идемпотентен: можно применять повторно.

-- ---------------------------------------------------------------------------
-- Вспомогательные функции. SECURITY DEFINER — чтобы чтение users внутри политик
-- не упиралось в RLS самой users (иначе рекурсия).
-- ---------------------------------------------------------------------------
create or replace function public.app_current_user_id() returns integer
language sql stable security definer set search_path = public, pg_temp as $$
  select id from public.users where auth_user_id = auth.uid()
$$;

create or replace function public.app_role() returns text
language sql stable security definer set search_path = public, pg_temp as $$
  select role from public.users where auth_user_id = auth.uid()
$$;

create or replace function public.app_is_staff() returns boolean
language sql stable security definer set search_path = public, pg_temp as $$
  select coalesce((select role in ('executive', 'manager') from public.users where auth_user_id = auth.uid()), false)
$$;

create or replace function public.app_client_company_id() returns integer
language sql stable security definer set search_path = public, pg_temp as $$
  select client_company_id from public.users where auth_user_id = auth.uid() and role = 'client'
$$;

create or replace function public.app_subcontractor_id() returns integer
language sql stable security definer set search_path = public, pg_temp as $$
  select subcontractor_id from public.users where auth_user_id = auth.uid() and role = 'subcontractor'
$$;

create or replace function public.app_subcontractor_object_ids() returns setof integer
language sql stable security definer set search_path = public, pg_temp as $$
  select distinct facility_object_id from public.shift_schedules where subcontractor_id = public.app_subcontractor_id()
$$;

-- ---------------------------------------------------------------------------
-- Включаем RLS на всех таблицах приложения (и на alembic_version — без политик).
-- ---------------------------------------------------------------------------
alter table public.users enable row level security;
alter table public.client_companies enable row level security;
alter table public.subcontractors enable row level security;
alter table public.document_source_references enable row level security;
alter table public.contracts enable row level security;
alter table public.contract_addenda enable row level security;
alter table public.facility_objects enable row level security;
alter table public.disputed_conditions enable row level security;
alter table public.shift_schedules enable row level security;
alter table public.shift_reports enable row level security;
alter table public.billing_acts enable row level security;
alter table public.billing_act_lines enable row level security;
alter table public.contract_sources enable row level security;
alter table public.addendum_sources enable row level security;
alter table public.facility_sources enable row level security;
alter table public.dispute_sources enable row level security;
alter table public.alembic_version enable row level security;

-- ---------------------------------------------------------------------------
-- Руководитель и менеджер: полный доступ ко всем таблицам, кроме users.
-- ---------------------------------------------------------------------------
do $$
declare t text;
begin
  foreach t in array array[
    'client_companies', 'subcontractors', 'document_source_references', 'contracts', 'contract_addenda',
    'facility_objects', 'disputed_conditions', 'shift_schedules', 'shift_reports', 'billing_acts',
    'billing_act_lines', 'contract_sources', 'addendum_sources', 'facility_sources', 'dispute_sources'
  ] loop
    execute format('drop policy if exists staff_all on public.%I', t);
    execute format(
      'create policy staff_all on public.%I for all to authenticated using (public.app_is_staff()) with check (public.app_is_staff())',
      t
    );
  end loop;
end
$$;

-- ---------------------------------------------------------------------------
-- users: каждый видит себя; персонал видит всех; менять может только руководитель.
-- ---------------------------------------------------------------------------
drop policy if exists users_self_select on public.users;
create policy users_self_select on public.users for select to authenticated
  using (auth_user_id = auth.uid());

drop policy if exists users_staff_select on public.users;
create policy users_staff_select on public.users for select to authenticated
  using (public.app_is_staff());

drop policy if exists users_executive_write on public.users;
create policy users_executive_write on public.users for all to authenticated
  using (public.app_role() = 'executive') with check (public.app_role() = 'executive');

-- ---------------------------------------------------------------------------
-- Клиент: только своя компания.
-- ---------------------------------------------------------------------------
drop policy if exists client_select on public.client_companies;
create policy client_select on public.client_companies for select to authenticated
  using (id = public.app_client_company_id());

drop policy if exists client_select on public.contracts;
create policy client_select on public.contracts for select to authenticated
  using (client_company_id = public.app_client_company_id());

drop policy if exists client_select on public.contract_addenda;
create policy client_select on public.contract_addenda for select to authenticated
  using (exists (
    select 1 from public.contracts c
    where c.id = contract_addenda.contract_id and c.client_company_id = public.app_client_company_id()
  ));

drop policy if exists client_select on public.facility_objects;
create policy client_select on public.facility_objects for select to authenticated
  using (client_company_id = public.app_client_company_id());

drop policy if exists client_select on public.disputed_conditions;
create policy client_select on public.disputed_conditions for select to authenticated
  using (client_company_id = public.app_client_company_id());

drop policy if exists client_select on public.shift_schedules;
create policy client_select on public.shift_schedules for select to authenticated
  using (facility_object_id in (
    select f.id from public.facility_objects f where f.client_company_id = public.app_client_company_id()
  ));

drop policy if exists client_select on public.shift_reports;
create policy client_select on public.shift_reports for select to authenticated
  using (schedule_id in (
    select s.id from public.shift_schedules s
    join public.facility_objects f on f.id = s.facility_object_id
    where f.client_company_id = public.app_client_company_id()
  ));

drop policy if exists client_select on public.billing_acts;
create policy client_select on public.billing_acts for select to authenticated
  using (kind = 'client_avr' and client_company_id = public.app_client_company_id());

-- Клиент видит субподрядчиков, назначенных на его объекты.
drop policy if exists client_select on public.subcontractors;
create policy client_select on public.subcontractors for select to authenticated
  using (id in (
    select f.subcontractor_id from public.facility_objects f
    where f.client_company_id = public.app_client_company_id()
  ));

-- ---------------------------------------------------------------------------
-- Субподрядчик: только объекты из своего графика смен.
-- ---------------------------------------------------------------------------
drop policy if exists subcontractor_select on public.subcontractors;
create policy subcontractor_select on public.subcontractors for select to authenticated
  using (id = public.app_subcontractor_id());

drop policy if exists subcontractor_select on public.facility_objects;
create policy subcontractor_select on public.facility_objects for select to authenticated
  using (id in (select public.app_subcontractor_object_ids()));

drop policy if exists subcontractor_select on public.shift_schedules;
create policy subcontractor_select on public.shift_schedules for select to authenticated
  using (subcontractor_id = public.app_subcontractor_id());

drop policy if exists subcontractor_select on public.shift_reports;
create policy subcontractor_select on public.shift_reports for select to authenticated
  using (schedule_id in (select s.id from public.shift_schedules s where s.subcontractor_id = public.app_subcontractor_id()));

drop policy if exists subcontractor_insert on public.shift_reports;
create policy subcontractor_insert on public.shift_reports for insert to authenticated
  with check (
    schedule_id in (select s.id from public.shift_schedules s where s.subcontractor_id = public.app_subcontractor_id())
    and reported_by_id = public.app_current_user_id()
  );

drop policy if exists subcontractor_update on public.shift_reports;
create policy subcontractor_update on public.shift_reports for update to authenticated
  using (schedule_id in (select s.id from public.shift_schedules s where s.subcontractor_id = public.app_subcontractor_id()))
  with check (
    schedule_id in (select s.id from public.shift_schedules s where s.subcontractor_id = public.app_subcontractor_id())
    and reported_by_id = public.app_current_user_id()
  );

drop policy if exists subcontractor_select on public.billing_acts;
create policy subcontractor_select on public.billing_acts for select to authenticated
  using (kind = 'subcontractor_act' and subcontractor_id = public.app_subcontractor_id());

-- ---------------------------------------------------------------------------
-- Подчинённые таблицы: строка видна, если видна родительская (подзапрос сам проходит RLS родителя).
-- ---------------------------------------------------------------------------
drop policy if exists party_select on public.billing_act_lines;
create policy party_select on public.billing_act_lines for select to authenticated
  using (act_id in (select a.id from public.billing_acts a));

drop policy if exists party_select on public.contract_sources;
create policy party_select on public.contract_sources for select to authenticated
  using (contract_id in (select c.id from public.contracts c));

drop policy if exists party_select on public.addendum_sources;
create policy party_select on public.addendum_sources for select to authenticated
  using (addendum_id in (select a.id from public.contract_addenda a));

drop policy if exists party_select on public.facility_sources;
create policy party_select on public.facility_sources for select to authenticated
  using (facility_object_id in (select f.id from public.facility_objects f));

drop policy if exists party_select on public.dispute_sources;
create policy party_select on public.dispute_sources for select to authenticated
  using (dispute_id in (select d.id from public.disputed_conditions d));

drop policy if exists party_select on public.document_source_references;
create policy party_select on public.document_source_references for select to authenticated
  using (
    id in (select x.source_id from public.contract_sources x)
    or id in (select x.source_id from public.addendum_sources x)
    or id in (select x.source_id from public.facility_sources x)
    or id in (select x.source_id from public.dispute_sources x)
    or id in (select s.source_id from public.shift_schedules s where s.source_id is not null)
    or id in (select a.source_id from public.billing_acts a where a.source_id is not null)
  );

-- ---------------------------------------------------------------------------
-- Привилегии. Строки ограничивает RLS; хеш пароля не отдаём никому через PostgREST.
-- ---------------------------------------------------------------------------
grant usage on schema public to authenticated;
grant select, insert, update, delete on all tables in schema public to authenticated;
grant usage, select on all sequences in schema public to authenticated;

revoke all on public.users from authenticated;
grant select (id, auth_user_id, email, role, client_company_id, subcontractor_id, created_at) on public.users to authenticated;
grant insert (auth_user_id, email, role, client_company_id, subcontractor_id) on public.users to authenticated;
grant update (auth_user_id, email, role, client_company_id, subcontractor_id) on public.users to authenticated;
grant delete on public.users to authenticated;

revoke all on public.alembic_version from authenticated;;

UPDATE alembic_version SET version_num='0002' WHERE alembic_version.version_num = '0001';

-- Running upgrade 0002 -> 0003

-- Субподрядчик не видит цены клиента (monthly_tariff, price_per_m2, НДС), договор и клиента.
--
-- RLS ограничивает строки, а не столбцы, а привилегии на столбцы в Supabase общие для всех
-- пользователей роли authenticated. Поэтому прямой доступ субподрядчика к facility_objects
-- закрыт, а свои объекты он читает через вью только с разрешёнными столбцами.
-- Вью выполняется с правами владельца (security_invoker = false) и само фильтрует строки
-- по графику смен; security_barrier не даёт обойти фильтр через функции в WHERE.

drop policy if exists subcontractor_select on public.facility_objects;

create or replace view public.subcontractor_facility_objects
with (security_barrier = true, security_invoker = false) as
select f.id, f.code, f.city, f.name, f.area_m2, f.external_area_m2, f.facade_area_m2, f.services, f.subcontractor_id
from public.facility_objects f
where f.id in (select public.app_subcontractor_object_ids());

comment on view public.subcontractor_facility_objects is
  'Объекты субподрядчика из графика смен: адрес, площадь, услуги. Без цен и НДС клиента.';

revoke all on public.subcontractor_facility_objects from public, anon, authenticated;
grant select on public.subcontractor_facility_objects to authenticated;;

UPDATE alembic_version SET version_num='0003' WHERE alembic_version.version_num = '0002';

COMMIT;

