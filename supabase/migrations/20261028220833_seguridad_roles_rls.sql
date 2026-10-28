-- =============================================================================
-- Capa 2 · Paso 2 de 2: roles, RLS y endurecimiento de funciones
-- Requiere: 20261028220643_rol_trabajador.sql
--
-- Modelo de acceso
--   profiles.role + profiles.activo son la única fuente de permisos:
--     admin        → Administrador: acceso total.
--     trabajador   → Trabajador: consulta productos, registra movimientos y
--                    opera la caja. No puede asignar ni cambiar precios.
--     host/usuario → Sin acceso a inventario ni caja. «usuario» es el rol por
--                    defecto de cualquier cuenta nueva (handle_new_user).
--   caja_operadores se conserva por compatibilidad con la app de caja y se
--   sincroniza automáticamente desde profiles.
--
-- Cambios de usuarios y roles: solo la Edge Function «admin-usuarios»
-- (service_role) o el SQL editor. Los clientes no tienen políticas de escritura
-- sobre profiles.
-- =============================================================================


-- 1. Estado de la cuenta ------------------------------------------------------

alter table public.profiles
  add column if not exists activo boolean not null default true;

comment on column public.profiles.activo is
  'false = cuenta desactivada por un administrador: pierde todo acceso por RLS.';


-- 2. Datos existentes ---------------------------------------------------------

-- Cuentas de Auth sin perfil (p. ej. operadores de caja creados a mano).
insert into public.profiles (id, email, full_name, role)
select u.id,
       coalesce(u.email, u.id::text),
       nullif(split_part(coalesce(u.email, ''), '@', 1), ''),
       case
         when exists (select 1 from public.caja_operadores o where o.user_id = u.id)
           then 'trabajador'::public.user_role
         else 'usuario'::public.user_role
       end
  from auth.users u
 where not exists (select 1 from public.profiles p where p.id = u.id);

-- Los operadores de caja con el rol por defecto pasan a trabajador para que
-- nadie pierda el acceso que ya tenía.
update public.profiles p
   set role = 'trabajador',
       updated_at = now()
 where p.role = 'usuario'
   and exists (select 1 from public.caja_operadores o where o.user_id = p.id);


-- 3. Funciones de autorización ------------------------------------------------

create or replace function public.rol_actual()
returns public.user_role
language sql
stable
security definer
set search_path = ''
as $$
  select p.role
    from public.profiles p
   where p.id = (select auth.uid())
     and p.activo
$$;

comment on function public.rol_actual() is
  'Rol del usuario autenticado; null si no tiene perfil o está desactivado.';

-- es_admin() y es_operador() conservan su nombre porque las políticas de caja
-- ya las usan. Pasan a ser SECURITY INVOKER: la lectura privilegiada de
-- profiles queda concentrada en rol_actual().
create or replace function public.es_admin()
returns boolean
language sql
stable
security invoker
set search_path = ''
as $$
  select coalesce(public.rol_actual() = 'admin', false)
$$;

create or replace function public.es_operador()
returns boolean
language sql
stable
security invoker
set search_path = ''
as $$
  select coalesce(public.rol_actual() in ('admin', 'trabajador'), false)
$$;

revoke execute on function public.rol_actual()  from public, anon;
revoke execute on function public.es_admin()    from public, anon;
revoke execute on function public.es_operador() from public, anon;
grant  execute on function public.rol_actual()  to authenticated, service_role;
grant  execute on function public.es_admin()    to authenticated, service_role;
grant  execute on function public.es_operador() to authenticated, service_role;


-- 4. Políticas de profiles ----------------------------------------------------

-- «Admins can view all» consultaba la propia tabla profiles dentro de su
-- política, lo que provoca recursión infinita en RLS.
drop policy if exists "Admins can view all"        on public.profiles;
drop policy if exists "Users can view own profile" on public.profiles;
drop policy if exists profiles_sel on public.profiles;

create policy profiles_sel on public.profiles
  for select to authenticated
  using (id = (select auth.uid()) or (select public.es_admin()));


-- 5. Siempre debe quedar un administrador activo ------------------------------

create or replace function public.proteger_ultimo_admin()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if old.role = 'admin'
     and old.activo
     and (tg_op = 'DELETE' or new.role <> 'admin' or not new.activo)
     and not exists (
       select 1
         from public.profiles p
        where p.id <> old.id
          and p.role = 'admin'
          and p.activo
     )
  then
    raise exception 'Debe quedar al menos un administrador activo';
  end if;

  if tg_op = 'DELETE' then
    return old;
  end if;
  return new;
end
$$;

drop trigger if exists tr_profiles_proteger_ultimo_admin on public.profiles;
create trigger tr_profiles_proteger_ultimo_admin
  before update of role, activo or delete on public.profiles
  for each row execute function public.proteger_ultimo_admin();


-- 6. caja_operadores sincronizada desde profiles ------------------------------

create or replace function public.sincronizar_caja_operadores()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if new.activo and new.role in ('admin', 'trabajador') then
    insert into public.caja_operadores (user_id)
    values (new.id)
    on conflict (user_id) do nothing;
  else
    delete from public.caja_operadores where user_id = new.id;
  end if;
  return null;
end
$$;

drop trigger if exists tr_profiles_sincronizar_caja on public.profiles;
create trigger tr_profiles_sincronizar_caja
  after insert or update of role, activo on public.profiles
  for each row execute function public.sincronizar_caja_operadores();

-- Alinear el estado actual con la nueva regla.
insert into public.caja_operadores (user_id)
select p.id
  from public.profiles p
 where p.activo
   and p.role in ('admin', 'trabajador')
on conflict (user_id) do nothing;

delete from public.caja_operadores o
 where not exists (
   select 1
     from public.profiles p
    where p.id = o.user_id
      and p.activo
      and p.role in ('admin', 'trabajador')
 );

comment on table public.caja_operadores is
  'Derivada de profiles (rol admin/trabajador y activo) por el trigger '
  'tr_profiles_sincronizar_caja. No editar a mano: cambiar el rol en profiles.';


-- 7. Precios: solo administradores --------------------------------------------

-- RLS filtra filas, no columnas: la restricción sobre «precio» va en un trigger.
-- Los trabajadores conservan, por ahora, el resto de permisos sobre productos
-- que ya tenían (pendiente de definir en la capa 3).
create or replace function public.proteger_precio_producto()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  -- Sin usuario de Auth (SQL editor, service_role) no se restringe; los
  -- clientes anónimos ya están bloqueados por RLS.
  if (select auth.uid()) is null or public.es_admin() then
    return new;
  end if;

  if tg_op = 'INSERT' and new.precio is not null then
    raise exception 'Solo un administrador puede asignar precios'
      using errcode = '42501';
  end if;

  if tg_op = 'UPDATE' and new.precio is distinct from old.precio then
    raise exception 'Solo un administrador puede modificar precios'
      using errcode = '42501';
  end if;

  return new;
end
$$;

drop trigger if exists tr_productos_proteger_precio on public.productos;
create trigger tr_productos_proteger_precio
  before insert or update on public.productos
  for each row execute function public.proteger_precio_producto();

revoke execute on function public.proteger_ultimo_admin()       from public, anon, authenticated;
revoke execute on function public.sincronizar_caja_operadores() from public, anon, authenticated;
revoke execute on function public.proteger_precio_producto()    from public, anon, authenticated;


-- 8. Funciones heredadas expuestas por la API ---------------------------------

-- verificar_login comprobaba contraseñas contra auth.users fuera de Supabase
-- Auth (sin límite de intentos) y cualquiera podía llamarla sin sesión.
-- Se conserva la función, pero ya no es invocable desde la API.
revoke execute on function public.verificar_login(text, text) from public, anon, authenticated;
alter function public.verificar_login(text, text) set search_path = public, extensions;

-- buscar_par_traslado devolvía movimientos sin pasar por RLS, incluso a anon.
alter function public.buscar_par_traslado(integer) security invoker;
alter function public.buscar_par_traslado(integer) set search_path = public;
revoke execute on function public.buscar_par_traslado(integer) from public, anon;
grant  execute on function public.buscar_par_traslado(integer) to authenticated, service_role;

alter function public.calcular_saldo_dinamico() set search_path = public;
alter function public.calcular_egreso_kardex()  set search_path = public;


-- 9. Auditoría ----------------------------------------------------------------

create table if not exists public.auditoria (
  id          bigint generated always as identity primary key,
  fecha       timestamptz not null default now(),
  actor_id    uuid references auth.users (id) on delete set null,
  actor_email text,
  accion      text not null,
  entidad     text not null,
  entidad_id  text,
  detalle     jsonb not null default '{}'::jsonb
);

comment on table public.auditoria is
  'Bitácora inmutable. Solo escriben la Edge Function admin-usuarios '
  '(service_role) y funciones SECURITY DEFINER; solo los administradores leen.';

create index if not exists auditoria_fecha_idx on public.auditoria (fecha desc);
create index if not exists auditoria_actor_idx on public.auditoria (actor_id);

alter table public.auditoria enable row level security;

drop policy if exists auditoria_sel on public.auditoria;
create policy auditoria_sel on public.auditoria
  for select to authenticated
  using ((select public.es_admin()));

revoke insert, update, delete, truncate on public.auditoria from anon, authenticated;
