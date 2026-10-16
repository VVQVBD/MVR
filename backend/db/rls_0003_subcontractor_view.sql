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
grant select on public.subcontractor_facility_objects to authenticated;
