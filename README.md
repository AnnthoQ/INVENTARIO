# Inventario

Aplicación de escritorio para gestionar inventario con dos roles, **Administrador** y **Trabajador**,
sobre Supabase (PostgreSQL + Auth + RLS). Está hecha en Python 3.11+ con PySide6 (Qt 6).

## Estado

| Capa | Contenido | Estado |
|---|---|---|
| 2 · Autenticación y seguridad | Roles, RLS, Edge Function de usuarios, login, sesión, bloqueo por inactividad | **Hecha** y desplegada en Supabase el 2026-10-28 (faltan los ajustes de Auth del panel) |
| 3 · Panel de administración | Usuarios, productos y precios, reportes, auditoría | **Hecha** y desplegada en Supabase el 2026-10-28 (sus pruebas pgTAP aún no se han ejecutado) |
| 4 · Panel del trabajador | Consulta de productos, entradas y salidas, lector de códigos | Pendiente |

- Qué hace cada módulo del panel de administración y cómo leer los reportes:
  [`docs/panel_admin.md`](docs/panel_admin.md).
- Modelo de seguridad, decisiones tomadas y pasos de despliegue: [`docs/seguridad.md`](docs/seguridad.md).

## Estructura

```
app/
├── main.py                  # punto de entrada (python -m app)
├── config.py                # .env → Config; rechaza claves service_role
├── core/                    # cliente Supabase, autenticación, errores, roles, formato, tareas en segundo plano
├── models/                  # perfil y sesión, producto, filas de reportes, entradas de auditoría
├── services/                # usuarios (Edge Function), productos, reportes y auditoría
├── controllers/             # flujo de sesión e inactividad
└── views/                   # login, bloqueo, ventana principal y páginas del panel de administración
supabase/
├── migrations/              # SQL de las capas 2 y 3 (aplicar en orden)
├── functions/admin-usuarios # Edge Function (Deno) para crear y administrar usuarios
└── tests/                   # réplica del esquema actual + pruebas pgTAP
scripts/probar_bd.sh         # prueba las migraciones en un PostgreSQL temporal
tests/                       # pruebas de Python (pytest + pytest-qt)
```

## Puesta en marcha

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env               # completa SUPABASE_KEY con la clave publishable
python -m app
```

Los usuarios con código, por ejemplo `op01`, inician sesión con ese código: la aplicación lo convierte
en `op01@inv.local`, que es el formato de las cuentas que ya existen en el proyecto.

## Pruebas

```bash
# Python (sin pantalla)
QT_QPA_PLATFORM=offscreen pytest

# Migraciones + RLS (PostgreSQL 15+ con pgTAP)
scripts/probar_bd.sh

# Edge Function
deno test supabase/functions/admin-usuarios/
```

En Linux sin entorno gráfico, Qt necesita `libegl1`, `libgl1`, `libxkbcommon0` y `libfontconfig1`.
