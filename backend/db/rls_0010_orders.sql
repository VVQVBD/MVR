-- RLS для разовых заявок (миграция 0009): cleaning_orders, order_photos, operator_bonus_records.
-- Та же модель доступа, что в app/access.py:
--   executive, manager  — всё (staff_all);
--   client               — свои заявки (по client_company_id);
--   subcontractor        — заявки, назначенные его операторам;
--   operator             — свои назначенные заявки / свои фото / свои премии.
-- Идемпотентно, как и db/rls.sql и db/rls_0008_operators.sql.

alter table public.cleaning_orders enable row level security;
alter table public.order_photos enable row level security;
alter table public.operator_bonus_records enable row level security;

drop policy if exists staff_all on public.cleaning_orders;
create policy staff_all on public.cleaning_orders for all to authenticated
  using (public.app_is_staff()) with check (public.app_is_staff());

drop policy if exists staff_all on public.order_photos;
create policy staff_all on public.order_photos for all to authenticated
  using (public.app_is_staff()) with check (public.app_is_staff());

drop policy if exists staff_all on public.operator_bonus_records;
create policy staff_all on public.operator_bonus_records for all to authenticated
  using (public.app_is_staff()) with check (public.app_is_staff());

drop policy if exists client_select on public.cleaning_orders;
create policy client_select on public.cleaning_orders for select to authenticated
  using (client_company_id = public.app_client_company_id());

drop policy if exists subcontractor_select on public.cleaning_orders;
create policy subcontractor_select on public.cleaning_orders for select to authenticated
  using (
    assigned_operator_id in (
      select id from public.operators where subcontractor_id = public.app_subcontractor_id()
    )
  );

drop policy if exists operator_select on public.cleaning_orders;
create policy operator_select on public.cleaning_orders for select to authenticated
  using (assigned_operator_id = public.app_operator_id());

drop policy if exists operator_update on public.cleaning_orders;
create policy operator_update on public.cleaning_orders for update to authenticated
  using (assigned_operator_id = public.app_operator_id())
  with check (assigned_operator_id = public.app_operator_id());

drop policy if exists operator_select on public.order_photos;
create policy operator_select on public.order_photos for all to authenticated
  using (operator_id = public.app_operator_id())
  with check (operator_id = public.app_operator_id());

drop policy if exists client_select on public.order_photos;
create policy client_select on public.order_photos for select to authenticated
  using (
    order_id in (select id from public.cleaning_orders where client_company_id = public.app_client_company_id())
  );

drop policy if exists subcontractor_select on public.order_photos;
create policy subcontractor_select on public.order_photos for select to authenticated
  using (
    operator_id in (select id from public.operators where subcontractor_id = public.app_subcontractor_id())
  );

drop policy if exists operator_select on public.operator_bonus_records;
create policy operator_select on public.operator_bonus_records for select to authenticated
  using (operator_id = public.app_operator_id());

drop policy if exists subcontractor_select on public.operator_bonus_records;
create policy subcontractor_select on public.operator_bonus_records for select to authenticated
  using (
    operator_id in (select id from public.operators where subcontractor_id = public.app_subcontractor_id())
  );

grant select, insert, update, delete on public.cleaning_orders to authenticated;
grant select, insert, update, delete on public.order_photos to authenticated;
grant select, insert, update, delete on public.operator_bonus_records to authenticated;
grant usage, select on all sequences in schema public to authenticated;
