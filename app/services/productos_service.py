"""Catálogo de productos.

Solo los administradores escriben: lo garantizan las políticas RLS de la capa 3
y el trigger de auditoría deja constancia de cada cambio.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from postgrest.exceptions import APIError
from supabase import Client

from app.core.errores import DatosInvalidos, PermisoDenegado, traducir_error
from app.core.formato import CENTIMOS, moneda
from app.models.producto import COLUMNAS_PRODUCTO, Producto
from app.services.consultas import todas_las_filas

PAGINA_MAXIMA = 9999
PRECIO_MAXIMO = Decimal("99999.99")
LONGITUD_MAXIMA_NOMBRE = 120

_SIN_FILAS = "El producto ya no existe o no tienes permiso para modificarlo."


def validar_producto(pagina: int | None, nombre: str, precio: Decimal | None) -> dict[str, Any]:
    """Devuelve la fila lista para enviar a PostgREST o lanza DatosInvalidos."""
    nombre = " ".join(nombre.split())
    if not nombre:
        raise DatosInvalidos("Ingresa el nombre del producto.")
    if len(nombre) > LONGITUD_MAXIMA_NOMBRE:
        raise DatosInvalidos(f"El nombre no puede tener más de {LONGITUD_MAXIMA_NOMBRE} caracteres.")
    if pagina is None or not 1 <= pagina <= PAGINA_MAXIMA:
        raise DatosInvalidos(f"La página del catálogo debe estar entre 1 y {PAGINA_MAXIMA}.")
    if precio is None:
        raise DatosInvalidos("Ingresa el precio.")
    if not Decimal(0) <= precio <= PRECIO_MAXIMO:
        raise DatosInvalidos(f"El precio debe estar entre {moneda(Decimal(0))} y {moneda(PRECIO_MAXIMO)}.")
    # PostgREST recibe los numeric como números JSON.
    return {"pg": pagina, "producto": nombre, "precio": float(precio.quantize(CENTIMOS))}


class ProductosService:
    def __init__(self, cliente: Client) -> None:
        self._cliente = cliente

    def listar(self) -> list[Producto]:
        filas = todas_las_filas(
            lambda: (
                self._cliente.table("productos")
                .select(COLUMNAS_PRODUCTO)
                .order("pg")
                .order("producto")
                .order("id")
            )
        )
        return [Producto.desde_fila(fila) for fila in filas]

    def crear(self, pagina: int | None, nombre: str, precio: Decimal | None) -> Producto:
        datos = validar_producto(pagina, nombre, precio)
        try:
            respuesta = self._cliente.table("productos").insert(datos).execute()
        except Exception as exc:  # noqa: BLE001
            raise traducir_error(exc) from exc
        return Producto.desde_fila(respuesta.data[0])

    def actualizar(
        self, producto_id: int, pagina: int | None, nombre: str, precio: Decimal | None
    ) -> Producto:
        datos = validar_producto(pagina, nombre, precio)
        try:
            respuesta = self._cliente.table("productos").update(datos).eq("id", producto_id).execute()
        except Exception as exc:  # noqa: BLE001
            raise traducir_error(exc) from exc
        # RLS no da error al bloquear un UPDATE: simplemente no actualiza filas.
        if not respuesta.data:
            raise PermisoDenegado(_SIN_FILAS)
        return Producto.desde_fila(respuesta.data[0])

    def eliminar(self, producto: Producto) -> None:
        try:
            respuesta = self._cliente.table("productos").delete().eq("id", producto.id).execute()
        except APIError as exc:
            if exc.code == "23503":
                raise DatosInvalidos(
                    f"No se puede eliminar «{producto.nombre}» porque tiene movimientos o ventas registradas."
                ) from exc
            raise traducir_error(exc) from exc
        except Exception as exc:  # noqa: BLE001
            raise traducir_error(exc) from exc
        if not respuesta.data:
            raise PermisoDenegado(_SIN_FILAS)
