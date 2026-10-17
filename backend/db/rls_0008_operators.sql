-- RLS для пилота рейтинга операторов (миграция 0007): operators, operator_ratings,
-- operator_points_entries. Та же модель доступа, что в db/rls.sql:
--   executive, manager  — всё (staff_all);
--   subcontractor       — свои операторы (operators), но не их оценки и баллы;
--   operator            — только свои строки в operators / operator_ratings / operator_points_entries.
-- Идемпотентно, как и db/rls.sql.

create or replace function public.app_operator_id() returns integer
language sql stable security definer set search_path = public, pg_temp as $$
  select operator_id from public.users where auth_user_id = auth.uid() and role = 'operator'
$$;

alter table public.operators enable row level security;
alter table public.operator_ratings enable row level security;
alter table public.operator_points_entries enable row level security;

drop policy if exists staff_all on public.operators;
create policy staff_all on public.operators for all to authenticated
  using (public.app_is_staff()) with check (public.app_is_staff());

drop policy if exists staff_all on public.operator_ratings;
create policy staff_all on public.operator_ratings for all to authenticated
  using (public.app_is_staff()) with check (public.app_is_staff());

drop policy if exists staff_all on public.operator_points_entries;
create policy staff_all on public.operator_points_entries for all to authenticated
  using (public.app_is_staff()) with check (public.app_is_staff());

drop policy if exists subcontractor_select on public.operators;
create policy subcontractor_select on public.operators for select to authenticated
  using (subcontractor_id = public.app_subcontractor_id());

drop policy if exists operator_select on public.operators;
create policy operator_select on public.operators for select to authenticated
  using (id = public.app_operator_id());

drop policy if exists operator_select on public.operator_ratings;
create policy operator_select on public.operator_ratings for select to authenticated
  using (operator_id = public.app_operator_id());

drop policy if exists operator_select on public.operator_points_entries;
create policy operator_select on public.operator_points_entries for select to authenticated
  using (operator_id = public.app_operator_id());

grant select, insert, update, delete on public.operators to authenticated;
grant select, insert, update, delete on public.operator_ratings to authenticated;
grant select, insert, update, delete on public.operator_points_entries to authenticated;
grant usage, select on all sequences in schema public to authenticated;
