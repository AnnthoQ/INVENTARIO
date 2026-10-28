"""Conversión y formato de importes, fechas y textos para la interfaz y los CSV."""

from __future__ import annotations

import unicodedata
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

# Perú no tiene horario de verano: America/Lima es siempre UTC−5. Un desfase fijo
# evita depender de la base de zonas horarias, que Windows no trae.
ZONA_LIMA = timezone(timedelta(hours=-5), "Lima")

CENTIMOS = Decimal("0.01")


def hoy() -> date:
    return datetime.now(ZONA_LIMA).date()


def a_decimal(valor: Any) -> Decimal | None:
    """PostgREST devuelve los numeric como números JSON; se pasan a Decimal sin perder precisión."""
    if valor is None or valor == "":
        return None
    try:
        return Decimal(str(valor))
    except (InvalidOperation, ValueError):
        return None


def moneda(valor: Decimal | None) -> str:
    return "" if valor is None else f"S/ {valor:,.2f}"


def entero(valor: int | None) -> str:
    return "" if valor is None else f"{valor:,}"


def fecha(valor: date | None) -> str:
    return valor.strftime("%d/%m/%Y") if valor else ""


def fecha_hora(valor: datetime | None) -> str:
    return valor.astimezone(ZONA_LIMA).strftime("%d/%m/%Y %H:%M") if valor else ""


def leer_fecha(texto: str | None) -> date | None:
    return date.fromisoformat(texto) if texto else None


def leer_fecha_hora(texto: str | None) -> datetime | None:
    return datetime.fromisoformat(texto) if texto else None


def inicio_del_dia(dia: date) -> str:
    """Medianoche de ese día en Lima, en ISO 8601, para filtrar columnas timestamptz."""
    return datetime.combine(dia, time.min, ZONA_LIMA).isoformat()


def rango_del_dia(desde: date, hasta: date) -> tuple[str, str]:
    """Límites [desde, hasta + 1 día) en Lima: incluye todo el último día."""
    return inicio_del_dia(desde), inicio_del_dia(hasta + timedelta(days=1))


def normalizar(texto: str) -> str:
    """Minúsculas, sin tildes y con espacios simples: «Lápiz  Azul» → «lapiz azul»."""
    descompuesto = unicodedata.normalize("NFD", texto)
    sin_tildes = "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")
    return " ".join(sin_tildes.casefold().split())
