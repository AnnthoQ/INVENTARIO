# Seguridad: autenticación, roles y RLS (capas 2 y 3)

## Modelo de acceso

La fuente única de permisos es `public.profiles` (`role` + `activo`):

| Rol | Etiqueta | Acceso |
|---|---|---|
| `admin` | Administrador | Todo: usuarios, catálogo y precios, reportes, corrección de movimientos, auditoría |
| `trabajador` | Trabajador | Consulta productos y stock, registra movimientos y opera la caja. **No crea, edita ni borra productos** (capa 3) |
| `host`, `usuario` | Sin acceso | `usuario` es el rol por defecto de cualquier cuenta nueva |

Una cuenta con `activo = false` pierde todo acceso al instante por RLS y queda bloqueada en Supabase Auth.

### Dónde se aplica cada regla

| Regla | Dónde |
|---|---|
| Quién ve y escribe cada tabla | Políticas RLS que usan `es_admin()` y `es_operador()` |
| Solo el admin crea, edita o borra productos (capa 3) | Políticas `productos_ins`, `productos_upd` y `productos_del` con `es_admin()` |
| Solo el admin asigna o cambia precios | Trigger `tr_productos_proteger_precio`: queda como segunda barrera desde la capa 3 |
| Precio no negativo y nombre no vacío | Restricciones `productos_precio_no_negativo` y `productos_nombre_requerido` |
| Siempre queda un administrador activo | Trigger `tr_profiles_proteger_ultimo_admin` |
| Crear usuarios, cambiar rol o estado, restablecer contraseñas | Edge Function `admin-usuarios`, la única con la clave `service_role` |
| Registro de esas acciones | Tabla `auditoria`: la escriben la Edge Function y el trigger `tr_productos_auditar` (altas, ediciones, cambios de precio y bajas de productos). Solo la leen los administradores |
| Reportes | Vista `stock_actual` con `security_invoker` (aplica el RLS de quien consulta) y función `reporte_mas_vendidos()`, que rechaza a quien no es administrador |
| Compatibilidad con la app de caja | `caja_operadores` se sincroniza desde `profiles` con un trigger |
| Menús según el rol | `app/core/roles.py`. Es solo para la interfaz; la barrera real es la base de datos |

### En la aplicación de escritorio

- El login acepta un código (`op01`, que se convierte en `op01@inv.local`) o un correo completo.
- Tras 3 contraseñas incorrectas en el equipo, la espera crece (5 s, 10 s, 20 s… hasta 5 min).
  Esto se suma al límite propio de Supabase Auth.
- «Recordar sesión» guarda solo el refresh token, en el almacén de credenciales del sistema operativo
  (Windows: Administrador de credenciales; macOS: Llavero). Nunca se guarda en un archivo.
- La pantalla se bloquea tras 15 minutos sin actividad. Tres intentos fallidos al desbloquear cierran la sesión.
- Cada 2 minutos la aplicación comprueba que la cuenta siga activa. Si un administrador la desactiva,
  la sesión se cierra.
- La aplicación no arranca si `SUPABASE_KEY` es una clave secreta (`service_role`).

## Hallazgos corregidos en el proyecto DBL

1. **Recursión infinita en RLS.** La política «Admins can view all» de `profiles` consultaba la propia
   tabla `profiles`. Hoy cualquier lectura de `profiles` falla con
   `42P17 infinite recursion detected in policy`, comprobado en producción el 2026-10-28.
2. **Los trabajadores podían cambiar precios.** `productos_upd` permitía a cualquier operador modificar
   todas las columnas.
3. **No había ningún administrador efectivo.** `es_admin()` exigía `role = 'admin'` y estar en
   `caja_operadores`, y ningún perfil cumplía ambas condiciones.
4. **Había dos operadores de caja sin perfil.** La migración les crea un perfil de trabajador.
5. **`verificar_login` estaba expuesta sin sesión.** Comprobaba contraseñas contra `auth.users` fuera de
   Supabase Auth, sin límite de intentos. Ahora no se puede invocar desde la API; la función se conserva.
6. **`buscar_par_traslado` saltaba RLS** (era `SECURITY DEFINER` y la podía llamar `anon`).
   Ahora es `SECURITY INVOKER` y solo la pueden llamar usuarios autenticados.
7. **Funciones con `search_path` mutable.** Se corrigieron `calcular_saldo_dinamico`,
   `calcular_egreso_kardex`, `buscar_par_traslado` y `verificar_login`.

## Decisiones tomadas por defecto

Las preguntas del diagnóstico no se respondieron, así que se aplicaron las opciones recomendadas:

| Pregunta | Decisión |
|---|---|
| A1 | Se amplía el esquema existente de DBL sin borrar nada, manteniendo la app de caja |
| 1.1 | Python + PySide6 (licencia LGPL) |
| 2.1 | Correo o código + contraseña con Supabase Auth, reutilizando las cuentas `@inv.local` que ya existen |
| 2.2 | Edge Function `admin-usuarios` |
| 2.3 | `profiles.role` es la fuente única de roles (ver nota) |
| 2.4 | Los trabajadores solo consultan el catálogo (respondida el 2026-10-28, capa 3) |
| 2.5 | «Recordar sesión» opcional; bloqueo a los 15 min; verificación cada 2 min |
| 2.7 | Contraseñas de 8 a 72 caracteres con letras y números |

**Nota sobre 2.3.** No se usa el Custom Access Token Hook. Las políticas RLS consultan `profiles` en cada
petición, así que desactivar una cuenta o cambiarle el rol tiene efecto inmediato. Un rol guardado en el
JWT tardaría hasta una hora en caducar y además habría que activar el hook a mano en el panel.

### Pendiente de tu decisión

- **2.6.** MFA (TOTP) para administradores: no implementado.

## Despliegue en Supabase

> Las migraciones cambian políticas que usa la app de caja en producción. Revisa primero la sección
> «Impacto en la app de caja».

1. **Aplicar las migraciones en orden**, con el MCP de Supabase, `supabase db push` o el SQL editor:
   1. `supabase/migrations/20261028220643_rol_trabajador.sql` (aplicada el 2026-10-28)
   2. `supabase/migrations/20261028220833_seguridad_roles_rls.sql` (aplicada el 2026-10-28)
   3. `supabase/migrations/20261028230330_capa3_panel_admin.sql` (aplicada el 2026-10-28)

   Al aplicar una migración con el MCP, Supabase usa la hora de aplicación como versión: renombra el
   archivo para que el historial local coincida con el remoto.
2. **Nombrar el primer administrador** desde el SQL editor:
   ```sql
   update public.profiles set role = 'admin' where email = 'tu-correo@ejemplo.com';
   ```
3. **Desplegar la Edge Function**, dejando activa la verificación de JWT:
   ```bash
   supabase functions deploy admin-usuarios --project-ref pvgdkcadqakfercyguhd
   ```
4. **Configurar en el panel** (Authentication → Policies / Providers):
   - Activar *Leaked password protection*.
   - Longitud mínima de contraseña: 8.
   - Si ninguna otra app necesita registro público, desactivar *Allow new users to sign up*.
     Las cuentas nuevas se crean desde el panel de administración.
5. **Configurar `.env`** en cada equipo con la clave *publishable* (`sb_publishable_…`).

### Impacto en la app de caja

- Los mismos tres operadores conservan el acceso. Un administrador también opera la caja.
- Un trabajador ya no puede crear un producto con precio ni cambiar precios: verá
  «Solo un administrador puede asignar/modificar precios».
- Con la capa 3, un trabajador tampoco puede crear productos sin precio ni editar su nombre o página.
  Desde el 3 de octubre la app de caja creó un producto con precio por la API; ese paso queda para el
  administrador. La caja sigue vendiendo y cerrando turnos igual que antes.
- Si la app de caja llamaba a `verificar_login` o a `buscar_par_traslado` sin sesión, dejará de funcionar.
- `caja_operadores` ya no se edita a mano: para dar o quitar acceso a la caja se cambia el rol o el estado
  en `profiles` (o en el panel de usuarios de la capa 3).

### Reversión

Las políticas y funciones anteriores están documentadas en `supabase/tests/fixtures/01_esquema_existente.sql`.
El valor `trabajador` del enum no se puede quitar sin recrear el tipo, pero si nadie lo usa no afecta a nada.

## Cómo se probó

- `scripts/probar_bd.sh`: 45 pruebas pgTAP sobre una réplica del esquema actual con datos ficticios de la
  misma forma (operadores con y sin perfil, cuenta sin acceso, administrador, cuenta desactivada, anónimo).
  Sin la migración, las mismas pruebas fallan con la recursión infinita.
- `deno test`: 16 pruebas de la Edge Function con un backend falso (permisos, validaciones, reversión
  ante fallos, la contraseña nunca llega a la auditoría).
- `pytest`: 79 pruebas del cliente (configuración, traducción de errores, login, restauración y rotación
  de tokens, límite de intentos, interfaz sin pantalla y flujo completo de sesión).
- Antes de aplicar las migraciones de la capa 2 en producción se ensayaron dentro de una transacción
  revertida, con los datos reales y simulando a cada cuenta (2026-10-28).

### Capa 3

- `pytest`: 144 pruebas en total, 63 nuevas (servicios contra un cliente falso, formato, modelos y páginas
  con Qt sin pantalla: búsqueda sin tildes, orden por valor, diálogos, confirmaciones y exportación a CSV).
- `supabase/tests/database/capa3.test.sql`: 23 pruebas pgTAP nuevas, y `seguridad.test.sql` ajustada a la
  regla 2.4. **No se ejecutaron**: el equipo de desarrollo (Windows) no tiene PostgreSQL. Hay que correr
  `scripts/probar_bd.sh` en Linux antes de dar la capa por cerrada.
- La migración se ensayó en producción dentro de un solo bloque revertido, con las cuentas reales: el
  trabajador no puede escribir en el catálogo ni ver el reporte de más vendidos; cada cambio del
  administrador queda auditado una vez; se rechazan precios negativos, nombres vacíos y el borrado de
  productos con movimientos; el reporte de octubre suma S/ 755.10, igual que los cierres de caja.
- Se aplicó el 2026-10-28 y se repitieron esas comprobaciones sobre la versión aplicada. Desde la API
  pública y sin sesión, `stock_actual`, `reporte_mas_vendidos` y `productos` responden «permission
  denied», y `auditoria` devuelve una lista vacía. El asesor de seguridad de Supabase no muestra avisos
  nuevos.
