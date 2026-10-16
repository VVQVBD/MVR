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

revoke all on public.alembic_version from authenticated;
