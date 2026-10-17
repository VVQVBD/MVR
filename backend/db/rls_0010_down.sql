-- Откат db/rls_0010_orders.sql.
do $$
declare t text;
begin
  foreach t in array array['cleaning_orders', 'order_photos', 'operator_bonus_records'] loop
    execute format('drop policy if exists staff_all on public.%I', t);
    execute format('drop policy if exists client_select on public.%I', t);
    execute format('drop policy if exists subcontractor_select on public.%I', t);
    execute format('drop policy if exists operator_select on public.%I', t);
    execute format('drop policy if exists operator_update on public.%I', t);
    execute format('alter table public.%I disable row level security', t);
  end loop;
end
$$;
