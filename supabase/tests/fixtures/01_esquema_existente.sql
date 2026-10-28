-- Réplica de los objetos del proyecto DBL que tocan las migraciones de las
-- capas 2 y 3, tal como estaban el 2026-10-28 antes de aplicarlas.
-- Solo para pruebas locales.

create type public.user_role as enum ('admin', 'host', 'usuario');

create table public.profiles (
  id         uuid primary key references auth.users (id) on delete cascade,
  email      text not null unique,
  full_name  text,
  role       public.user_role not null default 'usuario',
  updated_at timestamptz default now()
);

create table public.caja_operadores (
  user_id uuid primary key references auth.users (id)
);

create table public.productos (
  id       serial primary key,
  pg       integer,
  producto varchar,
  precio   numeric
);

create table public.movimientos_inventario (
  id               serial primary key,
  producto_id      integer references public.productos (id),
  fecha            timestamptz default now(),
  ubicacion        text check (ubicacion = any (array['ALMACEN', 'VITRINA'])),
  cantidad_cambio  integer,
  saldo_resultante integer,
  concepto         text
);

create table public.correcciones_kardex (
  id             serial primary key,
  movimiento_id  integer references public.movimientos_inventario (id),
  campo_editado  text not null,
  valor_anterior integer,
  valor_nuevo    integer,
  editado_por    text,
  fecha          timestamptz default now(),
  ubicacion      text,
  fue_vinculada  boolean default false
);

create table public.caja_items (
  id              bigint generated always as identity primary key,
  producto_id     integer not null references public.productos (id),
  nombre          text not null,
  cantidad        integer not null check (cantidad > 0),
  precio_unitario numeric not null,
  cierre_id       bigint,
  created_by      uuid default auth.uid(),
  created_at      timestamptz default now()
);

create unique index caja_items_abierto_uq on public.caja_items (producto_id) where cierre_id is null;

create table public.caja_cierres (
  id             bigint generated always as identity primary key,
  fecha          date not null default ((now() at time zone 'America/Lima'))::date,
  turno          text not null check (turno = any (array['Mañana', 'Tarde'])),
  operador       text,
  color          numeric,
  a3             numeric,
  scan           numeric,
  espiral        numeric,
  impresion      numeric,
  yape_plin      numeric,
  n_op           text,
  total_manual   numeric,
  libreria_total numeric not null,
  items          jsonb not null,
  created_by     uuid default auth.uid(),
  created_at     timestamptz default now()
);

alter table public.profiles               enable row level security;
alter table public.caja_operadores        enable row level security;
alter table public.productos              enable row level security;
alter table public.movimientos_inventario enable row level security;
alter table public.correcciones_kardex    enable row level security;
alter table public.caja_items             enable row level security;
alter table public.caja_cierres           enable row level security;

-- Funciones -------------------------------------------------------------------

create function public.es_admin()
returns boolean language sql stable security definer set search_path to 'public'
as $$ select exists(select 1 from public.caja_operadores o join public.profiles p on p.id = o.user_id where o.user_id = auth.uid() and p.role = 'admin') $$;

create function public.es_operador()
returns boolean language sql stable security definer set search_path to 'public'
as $$ select exists(select 1 from public.caja_operadores where user_id = auth.uid()) $$;

revoke execute on function public.es_admin()    from public, anon;
revoke execute on function public.es_operador() from public, anon;

create function public.handle_new_user()
returns trigger language plpgsql security definer set search_path to ''
as $$
begin
  insert into public.profiles (id, email, role)
  values (new.id, new.email, 'usuario'::public.user_role);
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

create function public.calcular_saldo_dinamico()
returns trigger language plpgsql
as $$
declare
  ultimo_saldo int;
begin
  select saldo_resultante into ultimo_saldo
    from movimientos_inventario
   where producto_id = new.producto_id and ubicacion = new.ubicacion
   order by fecha desc, id desc limit 1;
  new.saldo_resultante := coalesce(ultimo_saldo, 0) + new.cantidad_cambio;
  return new;
end;
$$;

create trigger tr_actualizar_saldo
  before insert on public.movimientos_inventario
  for each row execute function public.calcular_saldo_dinamico();

-- Huérfana en producción (la tabla kardex_vitrina ya no existe).
create function public.calcular_egreso_kardex()
returns trigger language plpgsql
as $$
declare
  ultimo_total int;
begin
  select stock_fisico_total into ultimo_total
    from kardex_vitrina
   where producto_id = new.producto_id and fecha < new.fecha
   order by fecha desc limit 1;
  new.egreso_ventas := (coalesce(ultimo_total, 0) + new.ingreso_desde_cl) - new.stock_fisico_total;
  return new;
end;
$$;

create function public.buscar_par_traslado(p_mov_id integer)
returns table(par_id integer, par_ubicacion text, par_cantidad integer)
language plpgsql security definer
as $$
declare
  v_producto_id integer;
  v_ubicacion   text;
  v_fecha       timestamptz;
  v_ubi_par     text;
begin
  select producto_id, ubicacion, fecha
    into v_producto_id, v_ubicacion, v_fecha
    from movimientos_inventario
   where id = p_mov_id and concepto = 'TRASLADO';
  if not found then return; end if;
  v_ubi_par := case when v_ubicacion = 'ALMACEN' then 'VITRINA' else 'ALMACEN' end;
  return query
  select m.id, m.ubicacion::text, m.cantidad_cambio
    from movimientos_inventario m
   where m.producto_id = v_producto_id
     and m.concepto = 'TRASLADO'
     and m.ubicacion = v_ubi_par
     and m.fecha between v_fecha - interval '10 seconds' and v_fecha + interval '10 seconds'
   order by abs(extract(epoch from (m.fecha - v_fecha)))
   limit 1;
end;
$$;

create function public.verificar_login(p_codigo text, p_password text)
returns table(user_id uuid, user_role text, user_nombre text)
language plpgsql security definer
as $$
declare
  v_user_id   uuid;
  v_encrypted text;
  v_role      text;
  v_nombre    text;
begin
  select u.id, u.encrypted_password into v_user_id, v_encrypted
    from auth.users u
   where u.email = p_codigo || '@inv.local' and u.banned_until is null;
  if v_user_id is null then return; end if;
  if v_encrypted != crypt(p_password, v_encrypted) then return; end if;
  select p.role::text, p.full_name into v_role, v_nombre from public.profiles p where p.id = v_user_id;
  return query select v_user_id, coalesce(v_role, 'usuario'), coalesce(v_nombre, p_codigo);
end;
$$;

create function public.caja_ajustar(p_producto integer, p_delta integer)
returns void language plpgsql set search_path to 'public'
as $$
declare p public.productos;
begin
  update public.caja_items set cantidad = cantidad + p_delta
   where producto_id = p_producto and cierre_id is null and cantidad + p_delta > 0;
  if found then return; end if;
  delete from public.caja_items
   where producto_id = p_producto and cierre_id is null and cantidad + p_delta <= 0;
  if found then return; end if;
  if p_delta > 0 then
    select * into p from public.productos where id = p_producto;
    if not found then raise exception 'Producto no existe'; end if;
    insert into public.caja_items(producto_id, nombre, cantidad, precio_unitario)
    values (p.id, p.producto, p_delta, coalesce(p.precio, 0));
  end if;
end $$;

create function public.caja_cerrar(p jsonb)
returns jsonb language plpgsql set search_path to 'public'
as $$
declare v_id bigint; v_items jsonb; v_tot numeric;
begin
  select coalesce(jsonb_agg(jsonb_build_object('nombre',nombre,'cantidad',cantidad,'subtotal',cantidad*precio_unitario) order by id),'[]'::jsonb),
         coalesce(sum(cantidad*precio_unitario),0)
    into v_items, v_tot from public.caja_items where cierre_id is null;
  if jsonb_array_length(v_items) = 0 then raise exception 'No hay ventas registradas'; end if;
  insert into public.caja_cierres(turno,operador,color,a3,scan,espiral,impresion,yape_plin,n_op,total_manual,libreria_total,items)
  values (p->>'turno', p->>'operador', (p->>'color')::numeric, (p->>'a3')::numeric, (p->>'scan')::numeric,
          (p->>'espiral')::numeric, (p->>'impresion')::numeric, (p->>'yape_plin')::numeric, p->>'n_op',
          (p->>'total_manual')::numeric, v_tot, v_items) returning id into v_id;
  update public.caja_items set cierre_id = v_id where cierre_id is null;
  return jsonb_build_object('id', v_id, 'items', v_items);
end $$;

-- Políticas -------------------------------------------------------------------

create policy "Admins can view all" on public.profiles for select
  using ((select profiles_1.role from public.profiles profiles_1 where profiles_1.id = auth.uid()) = 'admin'::public.user_role);
create policy "Users can view own profile" on public.profiles for select
  using (auth.uid() = id);

create policy operadores_own on public.caja_operadores for select to authenticated
  using (user_id = auth.uid());

create policy productos_sel on public.productos for select to authenticated using (es_operador());
create policy productos_ins on public.productos for insert to authenticated with check (es_operador());
create policy productos_upd on public.productos for update to authenticated using (es_operador()) with check (es_operador());
create policy productos_del on public.productos for delete to authenticated using (es_admin());

create policy mov_sel on public.movimientos_inventario for select to authenticated using (es_operador());
create policy mov_ins on public.movimientos_inventario for insert to authenticated with check (es_operador());
create policy mov_upd on public.movimientos_inventario for update to authenticated using (es_admin()) with check (es_admin());
create policy mov_del on public.movimientos_inventario for delete to authenticated using (es_admin());

create policy items_all on public.caja_items for all to authenticated using (es_operador()) with check (es_operador());

create policy cierres_sel on public.caja_cierres for select to authenticated using (es_operador());
create policy cierres_ins on public.caja_cierres for insert to authenticated with check (es_operador());
create policy cierres_upd on public.caja_cierres for update to authenticated using (es_admin()) with check (es_admin());
create policy cierres_del on public.caja_cierres for delete to authenticated using (es_admin());
