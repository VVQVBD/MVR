drop view if exists public.subcontractor_facility_objects;

drop policy if exists subcontractor_select on public.facility_objects;
create policy subcontractor_select on public.facility_objects for select to authenticated
  using (id in (select public.app_subcontractor_object_ids()));
