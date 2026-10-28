# Inventario

Aplicación de escritorio para gestionar inventario con dos roles, **Administrador** y **Trabajador**,
sobre Supabase (PostgreSQL + Auth + RLS). Está hecha en Python 3.11+ con PySide6 (Qt 6).

## Estado

| Capa | Contenido | Estado |
|---|---|---|
| 2 · Autenticación y seguridad | Roles, RLS, Edge Function de usuarios, login, sesión, bloqueo por inactividad | **Hecha** (migraciones pendientes de aplicar en Supabase) |
| 3 · Panel de administración | Usuarios, productos y precios, reportes, auditoría | Pendiente |
| 4 · Panel del trabajador | Consulta de productos, entradas y salidas, lector de códigos | Pendiente |

El modelo de seguridad, las decisiones tomadas y los pasos de despliegue están en
[`docs/seguridad.md`](docs/seguridad.md).

## Estructura

```
app/
├── main.py                  # punto de entrada (python -m app)
├── config.py                # .env → Config; rechaza claves service_role
├── core/                    # cliente Supabase, autenticación, errores, roles, tareas en segundo plano
├── models/                  # Perfil, SesionUsuario
├── services/                # UsuariosService (Edge Function admin-usuarios)
├── controllers/             # flujo de sesión e inactividad
└── views/                   # login, bloqueo, cambio de contraseña, ventana principal
supabase/
├── migrations/              # SQL de la capa 2 (aplicar en orden)
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
