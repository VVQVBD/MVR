-- Откат db/rls_0008_operators.sql.
do $$
declare t text;
begin
  foreach t in array array['operators', 'operator_ratings', 'operator_points_entries'] loop
    execute format('drop policy if exists staff_all on public.%I', t);
    execute format('drop policy if exists subcontractor_select on public.%I', t);
    execute format('drop policy if exists operator_select on public.%I', t);
    execute format('alter table public.%I disable row level security', t);
  end loop;
end
$$;

drop function if exists public.app_operator_id();
