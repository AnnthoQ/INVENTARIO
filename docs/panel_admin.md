# Panel de administración (capa 3)

Solo lo ven los administradores. Cada página consulta sus datos la primera vez que se abre, y
«Actualizar» o «Consultar» los vuelven a pedir. Todas las tablas permiten:

- ordenar con un clic en el encabezado, por el valor real (importes, fechas, cantidades);
- filtrar con «Buscar…», sin importar tildes ni mayúsculas («lapiz» encuentra «Lápiz»);
- exportar a CSV para Excel. El archivo incluye solo las filas visibles, en el orden en que se ven.

Las filas resaltadas en ámbar tienen algo que conviene revisar. El motivo aparece al pasar el ratón.

## Productos y precios

- Alta, edición y baja de productos: página del catálogo (columna `pg`), nombre y precio.
- La aplicación rechaza nombres repetidos (sin distinguir mayúsculas ni tildes). La base de datos rechaza
  precios negativos y nombres vacíos.
- Un producto con movimientos o ventas no se puede borrar.
- Cada cambio queda en la auditoría. Los cambios de precio guardan el valor anterior y el nuevo.
- Los trabajadores solo consultan el catálogo (decisión 2.4).

## Usuarios

- Alta de cuentas con un código (`op05` inicia sesión como `op05@inv.local`) o con un correo. También se
  puede cambiar el rol, activar o desactivar una cuenta y restablecer su contraseña. Todo pasa por la
  Edge Function `admin-usuarios`.
- Las cuentas sin acceso al inventario, como las de la app de presentaciones, están ocultas.
  «Mostrar cuentas sin acceso» las muestra, y «Dar acceso» les asigna un rol.
- Desactivar una cuenta o restablecer su contraseña solo se ofrece para cuentas del inventario, para no
  bloquear cuentas de otras aplicaciones del mismo proyecto.
- Nadie puede cambiar su propio rol ni desactivar su propia cuenta, y siempre queda un administrador activo.

## Reportes

### Ventas de caja

Muestra una fila por cierre de caja del período.

- **Total registrado** es la suma de Librería y los servicios (Color, A3, Scan, Espiral e Impresión), tal
  como los anotó quien cerró la caja.
- **Yape/Plin**, **Total manual** y **N.º op.** se muestran tal como se registraron, sin recalcular nada.

Los turnos con más de un cierre se resaltan y los totales suman todos los cierres. En producción, el turno
mañana del 24/10/2026 se cerró dos veces: el cierre 11 repite los productos del 10 y agrega dos más.
Revisa esos casos antes de usar las sumas.

### Más vendidos

Productos vendidos en los cierres del período, por cantidad y por importe (al precio cobrado en la caja).
Si en el período hay turnos con más de un cierre, el reporte lo advierte, porque esos productos se cuentan
dos veces.

### Stock actual

Es la suma de los movimientos de inventario de cada producto, por ubicación (almacén y vitrina). Al
28/10/2026 conviene tener en cuenta tres cosas:

- **Sin movimientos recientes:** el último movimiento es del 23/03/2026. La app de caja, que se usa desde
  octubre, registra ventas y cierres pero no movimientos de inventario. Por eso el stock no descuenta esas
  ventas.
- **Saldos que no cuadran:** 66 de los 129 productos tienen un saldo registrado distinto de la suma de sus
  movimientos. Se borraron unos 119 movimientos sin recalcular los saldos.
- **Stock negativo:** un producto queda en negativo.

Esos productos llevan «Sí» en la columna «Revisar»; conviene confirmarlos con un conteo físico.

### Movimientos (kárdex)

Ingresos, ventas y traslados por producto y período. «Saldo registrado» es el saldo que se guardó al
registrar cada movimiento. Un traslado aparece dos veces: como salida de una ubicación y como entrada en la
otra.

## Auditoría

Muestra quién hizo cada cambio, cuándo y qué cambió:

- **Usuarios:** altas, cambios de rol, activaciones y contraseñas restablecidas.
- **Productos:** altas, ediciones, cambios de precio y bajas.

«Sistema» indica un cambio hecho desde el SQL editor de Supabase. Nadie puede editar ni borrar la bitácora
desde la aplicación.
