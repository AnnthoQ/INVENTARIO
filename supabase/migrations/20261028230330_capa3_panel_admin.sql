-- =============================================================================
-- Capa 3: panel de administración
-- Requiere: 20261028220833_seguridad_roles_rls.sql
--
--   1. Catálogo: solo los administradores crean, editan y borran productos
--      (decisión 2.4). Los trabajadores solo los consultan.
--   2. Auditoría de cada alta, edición, cambio de precio y baja de productos.
--   3. Vista stock_actual: stock por ubicación según los movimientos.
--   4. Función reporte_mas_vendidos: ventas por producto según los cierres de caja.
--
-- Las ventas de caja, el kárdex y la auditoría se leen con las políticas que ya
-- existen (es_operador / es_admin).
-- =============================================================================


-- 1. Catálogo: escritura solo para administradores ----------------------------

drop policy if exists productos_ins on public.productos;
drop policy if exists productos_upd on public.productos;
drop policy if exists productos_del on public.productos;

create policy productos_ins on public.productos
  for insert to authenticated
  with check ((select public.es_admin()));

create policy productos_upd on public.productos
  for update to authenticated
  using ((select public.es_admin()))
  with check ((select public.es_admin()));

create policy productos_del on public.productos
  for delete to authenticated
  using ((select public.es_admin()));

alter table public.productos alter column producto set not null;

alter table public.productos drop constraint if exists productos_nombre_requerido;
alter table public.productos
  add constraint productos_nombre_requerido check (btrim(producto) <> '');

alter table public.productos drop constraint if exists productos_precio_no_negativo;
alter table public.productos
  add constraint productos_precio_no_negativo check (precio >= 0);


-- 2. Auditoría del catálogo ---------------------------------------------------

-- detalle: {producto, valores: {pg, producto, precio}} en altas y bajas;
--          {producto, cambios: {campo: {antes, despues}}} en ediciones.
create or replace function public.auditar_producto()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_fila    public.productos;
  v_accion  text;
  v_detalle jsonb;
  v_cambios jsonb := '{}'::jsonb;
begin
  if tg_op = 'INSERT' then
    v_fila := new;
    v_accion := 'producto.crear';
    v_detalle := jsonb_build_object('valores',
      jsonb_build_object('pg', new.pg, 'producto', new.producto, 'precio', new.precio));
  elsif tg_op = 'DELETE' then
    v_fila := old;
    v_accion := 'producto.eliminar';
    v_detalle := jsonb_build_object('valores',
      jsonb_build_object('pg', old.pg, 'producto', old.producto, 'precio', old.precio));
  else
    v_fila := new;
    if new.pg is distinct from old.pg then
      v_cambios := v_cambios || jsonb_build_object('pg',
        jsonb_build_object('antes', old.pg, 'despues', new.pg));
    end if;
    if new.producto is distinct from old.producto then
      v_cambios := v_cambios || jsonb_build_object('producto',
        jsonb_build_object('antes', old.producto, 'despues', new.producto));
    end if;
    if new.precio is distinct from old.precio then
      v_cambios := v_cambios || jsonb_build_object('precio',
        jsonb_build_object('antes', old.precio, 'despues', new.precio));
    end if;
    -- Un UPDATE que no cambia nada no deja rastro.
    if v_cambios = '{}'::jsonb then
      return null;
    end if;
    v_accion := case when v_cambios ? 'precio' then 'producto.cambiar_precio' else 'producto.editar' end;
    v_detalle := jsonb_build_object('cambios', v_cambios);
  end if;

  -- Sin usuario de Auth (SQL editor) el actor queda vacío.
  insert into public.auditoria (actor_id, actor_email, accion, entidad, entidad_id, detalle)
  values ((select auth.uid()),
          (select auth.jwt() ->> 'email'),
          v_accion,
          'producto',
          v_fila.id::text,
          jsonb_build_object('producto', v_fila.producto) || v_detalle);
  return null;
end
$$;

drop trigger if exists tr_productos_auditar on public.productos;
create trigger tr_productos_auditar
  after insert or update or delete on public.productos
  for each row execute function public.auditar_producto();

revoke execute on function public.auditar_producto() from public, anon, authenticated;


-- 3. Stock por ubicación ------------------------------------------------------

-- El stock es la suma de los movimientos. saldo_resultante es el saldo que el
-- trigger calculó al registrar cada movimiento: si después se borraron o
-- editaron movimientos, deja de coincidir con la suma y la fila se marca para
-- revisar.
create or replace view public.stock_actual
with (security_invoker = true)
as
with suma as (
  select m.producto_id,
         coalesce(sum(m.cantidad_cambio) filter (where m.ubicacion = 'ALMACEN'), 0) as almacen,
         coalesce(sum(m.cantidad_cambio) filter (where m.ubicacion = 'VITRINA'), 0) as vitrina,
         max(m.fecha) as ultimo_movimiento
    from public.movimientos_inventario m
   group by m.producto_id
), ultimo as (
  select distinct on (m.producto_id, m.ubicacion)
         m.producto_id, m.ubicacion, m.saldo_resultante
    from public.movimientos_inventario m
   order by m.producto_id, m.ubicacion, m.fecha desc, m.id desc
)
select p.id as producto_id,
       p.pg,
       p.producto,
       coalesce(s.almacen, 0)::integer as almacen,
       coalesce(s.vitrina, 0)::integer as vitrina,
       (coalesce(s.almacen, 0) + coalesce(s.vitrina, 0))::integer as total,
       s.ultimo_movimiento,
       ua.saldo_resultante as almacen_registrado,
       uv.saldo_resultante as vitrina_registrado,
       (coalesce(ua.saldo_resultante, 0) <> coalesce(s.almacen, 0)
         or coalesce(uv.saldo_resultante, 0) <> coalesce(s.vitrina, 0)) as revisar
  from public.productos p
  left join suma s on s.producto_id = p.id
  left join ultimo ua on ua.producto_id = p.id and ua.ubicacion = 'ALMACEN'
  left join ultimo uv on uv.producto_id = p.id and uv.ubicacion = 'VITRINA';

comment on view public.stock_actual is
  'Stock por producto y ubicación (suma de movimientos). revisar = el último '
  'saldo_resultante registrado no coincide con la suma.';

revoke all on public.stock_actual from anon, authenticated;
grant select on public.stock_actual to authenticated;

create index if not exists movimientos_producto_ubicacion_fecha_idx
  on public.movimientos_inventario (producto_id, ubicacion, fecha desc, id desc);


-- 4. Productos más vendidos ---------------------------------------------------

-- Cuenta los productos de los cierres de caja del período (fecha del cierre).
create or replace function public.reporte_mas_vendidos(p_desde date, p_hasta date)
returns table (
  producto_id integer,
  producto    text,
  pg          integer,
  cantidad    bigint,
  importe     numeric,
  cierres     bigint
)
language plpgsql
stable
security invoker
set search_path = ''
as $$
#variable_conflict use_column
begin
  if not public.es_admin() then
    raise exception 'Solo un administrador puede ver los reportes'
      using errcode = '42501';
  end if;

  return query
  select i.producto_id,
         coalesce(p.producto::text, max(i.nombre)),
         p.pg,
         sum(i.cantidad)::bigint,
         sum(i.cantidad * i.precio_unitario),
         count(distinct i.cierre_id)
    from public.caja_items i
    join public.caja_cierres c on c.id = i.cierre_id
    left join public.productos p on p.id = i.producto_id
   where c.fecha between p_desde and p_hasta
   group by i.producto_id, p.producto, p.pg
   order by 4 desc, 5 desc, 2;
end
$$;

revoke execute on function public.reporte_mas_vendidos(date, date) from public, anon;
grant  execute on function public.reporte_mas_vendidos(date, date) to authenticated, service_role;

create index if not exists caja_items_cierre_idx on public.caja_items (cierre_id);
