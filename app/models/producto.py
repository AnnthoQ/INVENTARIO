"""Producto del catálogo."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.core.formato import a_decimal, normalizar

COLUMNAS_PRODUCTO = "id, pg, producto, precio"


@dataclass(frozen=True)
class Producto:
    id: int
    pagina: int | None  # columna «pg»: página del catálogo
    nombre: str
    precio: Decimal | None

    @classmethod
    def desde_fila(cls, fila: Mapping[str, Any]) -> Producto:
        return cls(
            id=int(fila["id"]),
            pagina=fila.get("pg"),
            nombre=(fila.get("producto") or "").strip(),
            precio=a_decimal(fila.get("precio")),
        )


def nombre_repetido(nombre: str, productos: Iterable[Producto], excepto_id: int | None = None) -> bool:
    """True si otro producto ya se llama igual (sin distinguir mayúsculas, tildes ni espacios)."""
    clave = normalizar(nombre)
    return any(normalizar(p.nombre) == clave and p.id != excepto_id for p in productos)
