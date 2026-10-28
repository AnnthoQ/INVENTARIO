-- Pruebas pgTAP de la capa 2 (roles, RLS y funciones expuestas).
-- Local: scripts/probar_bd.sh · Con el stack de Supabase: supabase test db

begin;
create extension if not exists pgtap with schema extensions;

select plan(45);

-- Usuarios de la semilla
--   a = op_a  (operador de caja con perfil «usuario»)
--   b = op_b  (operador de caja sin perfil)
--   c = op_c  (operador de caja sin perfil)
--   d = dueno (perfil «usuario», no operaba caja)


-- Migración de datos ----------------------------------------------------------

select is((select role::text from public.profiles where id = '00000000-0000-0000-0000-00000000000a'),
          'trabajador', 'operador con perfil «usuario» pasa a trabajador');
select is((select role::text from public.profiles where id = '00000000-0000-0000-0000-00000000000b'),
          'trabajador', 'operador sin perfil recibe un perfil de trabajador');
select is((select full_name from public.profiles where id = '00000000-0000-0000-0000-00000000000b'),
          'op_b', 'el nombre del perfil creado sale del código de usuario');
select is((select role::text from public.profiles where id = '00000000-0000-0000-0000-00000000000d'),
          'usuario', 'una cuenta que no operaba caja sigue sin acceso');
select set_eq('select user_id from public.caja_operadores',
              array['00000000-0000-0000-0000-00000000000a',
                    '00000000-0000-0000-0000-00000000000b',
                    '00000000-0000-0000-0000-00000000000c']::uuid[],
              'los mismos tres operadores conservan la caja');


-- Primer administrador (se asigna desde el SQL editor) -------------------------

update public.profiles set role = 'admin' where id = '00000000-0000-0000-0000-00000000000d';

select ok(exists(select 1 from public.caja_operadores where user_id = '00000000-0000-0000-0000-00000000000d'),
          'el administrador se sincroniza en caja_operadores');


-- Trabajador ------------------------------------------------------------------

set local role authenticated;
set local request.jwt.claims = '{"sub": "00000000-0000-0000-0000-00000000000a"}';

select ok(public.es_operador(), 'trabajador: es operador');
select ok(not public.es_admin(), 'trabajador: no es administrador');
select is((select count(*)::int from public.productos), 2, 'trabajador: ve los productos');
select is((select count(*)::int from public.profiles), 1, 'trabajador: solo ve su propio perfil (sin recursión)');
select throws_ok($$update public.productos set precio = 9 where id = 1$$,
                 '42501', 'Solo un administrador puede modificar precios',
                 'trabajador: no puede cambiar precios');
select throws_ok($$insert into public.productos (producto, precio) values ('Regla', 2)$$,
                 '42501', 'Solo un administrador puede asignar precios',
                 'trabajador: no puede crear productos con precio');
select lives_ok($$update public.productos set producto = 'Cuaderno A4 rayado' where id = 1$$,
                'trabajador: conserva la edición de los demás campos');
select lives_ok($$insert into public.movimientos_inventario (producto_id, ubicacion, cantidad_cambio, concepto)
                  values (1, 'ALMACEN', -2, 'VENTA')$$,
                'trabajador: registra movimientos');
select is((select saldo_resultante from public.movimientos_inventario where concepto = 'VENTA'),
          18, 'el trigger sigue calculando el saldo');
select lives_ok($$select public.caja_ajustar(2, 3)$$, 'trabajador: la caja sigue funcionando');
select lives_ok($$select * from public.buscar_par_traslado(2)$$, 'trabajador: puede usar buscar_par_traslado');
select is((select count(*)::int from public.auditoria), 0, 'trabajador: no ve la auditoría');
select throws_ok($$insert into public.auditoria (accion, entidad) values ('x', 'y')$$,
                 '42501', null, 'trabajador: no puede escribir en la auditoría');

update public.profiles set role = 'admin' where id = '00000000-0000-0000-0000-00000000000a';
select is(public.rol_actual()::text, 'trabajador', 'trabajador: no puede cambiarse el rol');

reset role;


-- Cuenta nueva sin acceso -----------------------------------------------------

insert into auth.users (id, email) values ('00000000-0000-0000-0000-00000000000e', 'nuevo@example.com');

select is((select role::text from public.profiles where id = '00000000-0000-0000-0000-00000000000e'),
          'usuario', 'una cuenta nueva nace sin acceso');
select ok(not exists(select 1 from public.caja_operadores where user_id = '00000000-0000-0000-0000-00000000000e'),
          'una cuenta nueva no opera caja');

set local role authenticated;
set local request.jwt.claims = '{"sub": "00000000-0000-0000-0000-00000000000e"}';

select ok(not public.es_operador(), 'sin acceso: no es operador');
select is((select count(*)::int from public.productos), 0, 'sin acceso: no ve productos');
select throws_ok($$insert into public.movimientos_inventario (producto_id, ubicacion, cantidad_cambio, concepto)
                   values (1, 'ALMACEN', 1, 'X')$$,
                 '42501', null, 'sin acceso: no registra movimientos');

reset role;


-- Anónimo ---------------------------------------------------------------------

set local role anon;
set local request.jwt.claims = '';

select is((select count(*)::int from public.productos), 0, 'anon: no ve productos');
select is((select count(*)::int from public.profiles), 0, 'anon: no ve perfiles');

reset role;


-- Administrador ---------------------------------------------------------------

set local role authenticated;
set local request.jwt.claims = '{"sub": "00000000-0000-0000-0000-00000000000d"}';

select ok(public.es_admin(), 'admin: es administrador');
select is((select count(*)::int from public.profiles), 5, 'admin: ve todos los perfiles');
select lives_ok($$update public.productos set precio = 6 where id = 1$$, 'admin: cambia precios');
select is((select precio from public.productos where id = 1), 6::numeric, 'admin: el precio queda guardado');
select lives_ok($$select count(*) from public.auditoria$$, 'admin: lee la auditoría');

reset role;


-- Desactivación ---------------------------------------------------------------

update public.profiles set activo = false where id = '00000000-0000-0000-0000-00000000000b';

select ok(not exists(select 1 from public.caja_operadores where user_id = '00000000-0000-0000-0000-00000000000b'),
          'desactivar una cuenta le quita la caja');

set local role authenticated;
set local request.jwt.claims = '{"sub": "00000000-0000-0000-0000-00000000000b"}';

select ok(not public.es_operador(), 'desactivado: pierde el acceso al instante');
select is((select count(*)::int from public.productos), 0, 'desactivado: no ve productos');

reset role;


-- Último administrador --------------------------------------------------------

select throws_ok($$update public.profiles set role = 'trabajador' where id = '00000000-0000-0000-0000-00000000000d'$$,
                 'P0001', 'Debe quedar al menos un administrador activo',
                 'no se puede quitar el rol al único administrador');
select throws_ok($$update public.profiles set activo = false where id = '00000000-0000-0000-0000-00000000000d'$$,
                 'P0001', 'Debe quedar al menos un administrador activo',
                 'no se puede desactivar al único administrador');

update public.profiles set role = 'admin' where id = '00000000-0000-0000-0000-00000000000c';

select lives_ok($$update public.profiles set role = 'trabajador' where id = '00000000-0000-0000-0000-00000000000d'$$,
                'con otro administrador activo sí se puede');


-- Funciones expuestas por la API ----------------------------------------------

select ok(not has_function_privilege('anon', 'public.verificar_login(text, text)', 'execute'),
          'anon no ejecuta verificar_login');
select ok(not has_function_privilege('authenticated', 'public.verificar_login(text, text)', 'execute'),
          'authenticated no ejecuta verificar_login');
select ok(not has_function_privilege('anon', 'public.buscar_par_traslado(integer)', 'execute'),
          'anon no ejecuta buscar_par_traslado');
select ok(not has_function_privilege('anon', 'public.rol_actual()', 'execute'),
          'anon no ejecuta rol_actual');
select ok(not has_function_privilege('authenticated', 'public.sincronizar_caja_operadores()', 'execute'),
          'authenticated no ejecuta funciones de trigger');
select is((select count(*)::int
             from pg_proc p
             join pg_namespace n on n.oid = p.pronamespace
            where n.nspname = 'public'
              and p.proname in ('calcular_saldo_dinamico', 'calcular_egreso_kardex',
                                'buscar_par_traslado', 'verificar_login')
              and p.proconfig is null),
          0, 'las funciones heredadas tienen search_path fijo');
select is((select prosecdef from pg_proc where oid = 'public.buscar_par_traslado(integer)'::regprocedure),
          false, 'buscar_par_traslado respeta RLS');

select * from finish();
rollback;
