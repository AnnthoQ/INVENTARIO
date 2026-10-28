-- Datos ficticios con la misma forma que los de producción antes de la
-- migración: 3 operadores de caja (uno con perfil «usuario», dos sin perfil)
-- y una cuenta con perfil «usuario» que no es operadora.

insert into auth.users (id, email) values
  ('00000000-0000-0000-0000-00000000000a', 'op_a@inv.local'),
  ('00000000-0000-0000-0000-00000000000b', 'op_b@inv.local'),
  ('00000000-0000-0000-0000-00000000000c', 'op_c@inv.local'),
  ('00000000-0000-0000-0000-00000000000d', 'dueno@example.com');

-- op_b y op_c se crearon antes de que existiera el trigger de perfiles.
delete from public.profiles
 where id in ('00000000-0000-0000-0000-00000000000b', '00000000-0000-0000-0000-00000000000c');

insert into public.caja_operadores (user_id) values
  ('00000000-0000-0000-0000-00000000000a'),
  ('00000000-0000-0000-0000-00000000000b'),
  ('00000000-0000-0000-0000-00000000000c');

insert into public.productos (id, producto, precio) values
  (1, 'Cuaderno A4', 5.50),
  (2, 'Lapicero azul', 1.20);
select setval('public.productos_id_seq', 2);

insert into public.movimientos_inventario (producto_id, ubicacion, cantidad_cambio, concepto) values
  (1, 'ALMACEN', 20, 'COMPRA'),
  (1, 'VITRINA', 5, 'TRASLADO');
