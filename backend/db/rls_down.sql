-- Откат db/rls.sql: удалить все политики и функции, выключить RLS.
do $$
declare r record;
begin
  for r in select policyname, tablename from pg_policies where schemaname = 'public' loop
    execute format('drop policy if exists %I on public.%I', r.policyname, r.tablename);
  end loop;
  for r in select tablename from pg_tables where schemaname = 'public' loop
    execute format('alter table public.%I disable row level security', r.tablename);
  end loop;
end
$$;

drop function if exists public.app_subcontractor_object_ids();
drop function if exists public.app_subcontractor_id();
drop function if exists public.app_client_company_id();
drop function if exists public.app_is_staff();
drop function if exists public.app_role();
drop function if exists public.app_current_user_id();
