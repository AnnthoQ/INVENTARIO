-- Pruebas pgTAP de la capa 3: catálogo solo para administradores, auditoría de
-- productos, vista stock_actual y función reporte_mas_vendidos.
-- Local: scripts/probar_bd.sh · Con el stack de Supabase: supabase test db

begin;
create extension if not exists pgtap with schema extensions;

select plan(23);

-- Usuarios de la semilla (tras la migración de la capa 2)
--   a = op_a  (trabajador)
--   d = dueno (se nombra administrador aquí)
update public.profiles set role = 'admin' where id = '00000000-0000-0000-0000-00000000000d';

-- Producto 2 con un ingreso que se borró después: el último saldo registrado
-- (7) deja de coincidir con la suma de los movimientos que quedan (-3).
insert into public.movimientos_inventario (producto_id, ubicacion, cantidad_cambio, concepto, fecha) values
  (2, 'ALMACEN', 10, 'INGRESO', '2026-03-01 10:00-05'),
  (2, 'ALMACEN', -3, 'VENTA',   '2026-03-02 10:00-05');
delete from public.movimientos_inventario where producto_id = 2 and concepto = 'INGRESO';


-- Trabajador ------------------------------------------------------------------

set local role authenticated;
set local request.jwt.claims = '{"sub": "00000000-0000-0000-0000-00000000000a"}';

select throws_ok($$insert into public.productos (pg, producto) values (9, 'Regla')$$,
                 '42501', null, 'trabajador: no crea productos, aunque no tengan precio');
update public.productos set producto = 'Cuaderno A4 rayado' where id = 1;
select is((select producto::text from public.productos where id = 1), 'Cuaderno A4',
          'trabajador: no edita productos');
delete from public.productos where id = 2;
select is((select count(*)::int from public.productos), 2, 'trabajador: no borra productos');
select is((select count(*)::int from public.stock_actual), 2, 'trabajador: consulta el stock');
select throws_ok($$select * from public.reporte_mas_vendidos('2026-01-01', '2026-12-31')$$,
                 '42501', 'Solo un administrador puede ver los reportes',
                 'trabajador: no ve el reporte de más vendidos');
select lives_ok($$select public.caja_ajustar(1, 3)$$, 'trabajador: registra una venta en la caja');
select lives_ok($$select public.caja_cerrar('{"turno": "Mañana", "operador": "op_a"}')$$,
                'trabajador: cierra la caja');

reset role;


-- Administrador ---------------------------------------------------------------

set local role authenticated;
set local request.jwt.claims = '{"sub": "00000000-0000-0000-0000-00000000000d", "email": "dueno@example.com"}';

select lives_ok($$insert into public.productos (pg, producto, precio) values (9, 'Regla 30 cm', 2.50)$$,
                'admin: crea productos');
select lives_ok($$update public.productos set precio = 3 where producto = 'Regla 30 cm'$$,
                'admin: cambia precios');
update public.productos set producto = 'Regla de 30 cm' where producto = 'Regla 30 cm';
update public.productos set precio = precio where producto = 'Regla de 30 cm';
select lives_ok($$delete from public.productos where producto = 'Regla de 30 cm'$$,
                'admin: borra un producto sin movimientos');

select results_eq($$select accion from public.auditoria where entidad = 'producto' order by id$$,
                  array['producto.crear', 'producto.cambiar_precio', 'producto.editar', 'producto.eliminar'],
                  'cada cambio del catálogo queda auditado una vez; un UPDATE sin cambios no');
select is((select detalle -> 'cambios' -> 'precio' from public.auditoria where accion = 'producto.cambiar_precio'),
          '{"antes": 2.50, "despues": 3}'::jsonb, 'la auditoría guarda el precio anterior y el nuevo');
select is((select actor_email from public.auditoria where accion = 'producto.crear'), 'dueno@example.com',
          'la auditoría guarda el correo de quien hizo el cambio');
select ok((select bool_and(actor_id = '00000000-0000-0000-0000-00000000000d')
             from public.auditoria where entidad = 'producto'),
          'la auditoría guarda el id de quien hizo el cambio');
select throws_ok($$delete from public.productos where id = 1$$, '23503', null,
                 'no se borra un producto con movimientos');
select throws_ok($$update public.productos set precio = -1 where id = 1$$, '23514', null,
                 'no se aceptan precios negativos');
select throws_ok($$update public.productos set producto = '  ' where id = 1$$, '23514', null,
                 'el nombre no puede quedar vacío');

select is((select row(almacen, vitrina, total, revisar)::text from public.stock_actual where producto_id = 1),
          '(20,5,25,f)', 'stock: suma los movimientos de cada ubicación');
select is((select row(almacen, almacen_registrado, revisar)::text from public.stock_actual where producto_id = 2),
          '(-3,7,t)', 'stock: marca el producto si el saldo registrado no coincide con la suma');

select results_eq($$select producto, cantidad, importe
                      from public.reporte_mas_vendidos(current_date - 1, current_date + 1)$$,
                  $$values ('Cuaderno A4'::text, 3::bigint, 16.50::numeric)$$,
                  'más vendidos: cantidades e importes de los cierres de caja del período');

reset role;


-- Anónimo y privilegios -------------------------------------------------------

set local role anon;
set local request.jwt.claims = '';

select throws_ok($$select * from public.stock_actual$$, '42501', null, 'anon: no consulta el stock');

reset role;

select ok(not has_function_privilege('anon', 'public.reporte_mas_vendidos(date, date)', 'execute'),
          'anon no ejecuta reporte_mas_vendidos');
select ok(not has_function_privilege('authenticated', 'public.auditar_producto()', 'execute'),
          'authenticated no ejecuta la función de auditoría');

select * from finish();
rollback;
