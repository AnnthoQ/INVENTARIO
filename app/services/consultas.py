"""Utilidades comunes de las consultas a PostgREST."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

from app.core.errores import DatosInvalidos, traducir_error

# Supabase devuelve como máximo 1000 filas por petición (db-max-rows).
TAMANO_PAGINA = 1000


def todas_las_filas(construir: Callable[[], Any]) -> list[dict[str, Any]]:
    """Ejecuta la consulta por páginas hasta traer todas las filas.

    «construir» devuelve una consulta nueva en cada llamada: los constructores de
    postgrest-py acumulan parámetros y no se pueden reutilizar.
    """
    filas: list[dict[str, Any]] = []
    inicio = 0
    while True:
        try:
            lote = construir().range(inicio, inicio + TAMANO_PAGINA - 1).execute().data
        except Exception as exc:  # noqa: BLE001
            raise traducir_error(exc) from exc
        filas.extend(lote)
        if len(lote) < TAMANO_PAGINA:
            return filas
        inicio += TAMANO_PAGINA


def validar_rango(desde: date, hasta: date) -> None:
    if desde > hasta:
        raise DatosInvalidos("La fecha inicial no puede ser posterior a la final.")
