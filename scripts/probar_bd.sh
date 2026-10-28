#!/usr/bin/env bash
# Prueba las migraciones sin tocar Supabase:
#   1. levanta un PostgreSQL temporal,
#   2. recrea el esquema actual de DBL (supabase/tests/fixtures),
#   3. aplica supabase/migrations en orden, cada una en su transacción,
#   4. ejecuta las pruebas pgTAP de supabase/tests/database.
#
# Requisitos: PostgreSQL 15+ con pgTAP (Debian/Ubuntu: postgresql-16-pgtap).
# Uso: scripts/probar_bd.sh
set -euo pipefail

RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
PG_BIN="${PG_BIN:-$(pg_config --bindir)}"
PUERTO="${PUERTO:-54329}"
DATOS="$(mktemp -d)"

# initdb y postgres no se ejecutan como root.
como_servidor() {
  if [ "$(id -u)" -eq 0 ]; then
    runuser -u postgres -- "$@"
  else
    "$@"
  fi
}

limpiar() {
  como_servidor "$PG_BIN/pg_ctl" -D "$DATOS" -m fast stop >/dev/null 2>&1 || true
  rm -rf "$DATOS"
}
trap limpiar EXIT

[ "$(id -u)" -eq 0 ] && chown postgres "$DATOS"

como_servidor "$PG_BIN/initdb" -D "$DATOS" -U postgres -A trust >/dev/null
como_servidor "$PG_BIN/pg_ctl" -D "$DATOS" -w -l "$DATOS/servidor.log" \
  -o "-p $PUERTO -k $DATOS -c listen_addresses=''" start >/dev/null

psql_bd() {
  psql -X -q -v ON_ERROR_STOP=1 -h "$DATOS" -p "$PUERTO" -U postgres -d postgres "$@"
}

echo "== Esquema existente"
for f in "$RAIZ"/supabase/tests/fixtures/*.sql; do
  echo "   $(basename "$f")"
  psql_bd -1 -f "$f"
done

echo "== Migraciones"
for f in "$RAIZ"/supabase/migrations/*.sql; do
  echo "   $(basename "$f")"
  psql_bd -1 -f "$f"
done

echo "== Pruebas"
fallos=0
for f in "$RAIZ"/supabase/tests/database/*.test.sql; do
  echo "-- $(basename "$f")"
  salida="$(psql_bd -t -A -f "$f" 2>&1)" || fallos=1
  echo "$salida"
  if grep -qE '^not ok|Looks like' <<<"$salida"; then
    fallos=1
  fi
done

if [ "$fallos" -ne 0 ]; then
  echo "== FALLARON PRUEBAS" >&2
  exit 1
fi
echo "== Todas las pruebas pasaron"
