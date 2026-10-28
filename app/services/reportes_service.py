"""Reportes del panel de administración: ventas de caja, más vendidos, stock y kárdex."""

from __future__ import annotations

from datetime import date
from typing import Any

from supabase import Client

from app.core.errores import traducir_error
from app.core.formato import rango_del_dia
from app.models.reportes import (
    COLUMNAS_CIERRE,
    COLUMNAS_MOVIMIENTO,
    CierreCaja,
    Movimiento,
    ProductoVendido,
    StockProducto,
)
from app.services.consultas import todas_las_filas, validar_rango


class ReportesService:
    def __init__(self, cliente: Client) -> None:
        self._cliente = cliente

    def ventas_caja(self, desde: date, hasta: date) -> list[CierreCaja]:
        """Cierres de caja del período; «fecha» es el día del cierre en Lima."""
        validar_rango(desde, hasta)
        filas = todas_las_filas(
            lambda: (
                self._cliente.table("caja_cierres")
                .select(COLUMNAS_CIERRE)
                .gte("fecha", desde.isoformat())
                .lte("fecha", hasta.isoformat())
                .order("fecha")
                .order("id")
            )
        )
        return [CierreCaja.desde_fila(fila) for fila in filas]

    def mas_vendidos(self, desde: date, hasta: date) -> list[ProductoVendido]:
        validar_rango(desde, hasta)
        try:
            respuesta = self._cliente.rpc(
                "reporte_mas_vendidos", {"p_desde": desde.isoformat(), "p_hasta": hasta.isoformat()}
            ).execute()
        except Exception as exc:  # noqa: BLE001
            raise traducir_error(exc) from exc
        return [ProductoVendido.desde_fila(fila) for fila in respuesta.data]

    def stock_actual(self) -> list[StockProducto]:
        filas = todas_las_filas(
            lambda: self._cliente.table("stock_actual").select("*").order("pg").order("producto")
        )
        return [StockProducto.desde_fila(fila) for fila in filas]

    def movimientos(self, desde: date, hasta: date, producto_id: int | None = None) -> list[Movimiento]:
        validar_rango(desde, hasta)
        inicio, fin = rango_del_dia(desde, hasta)

        def consulta() -> Any:
            filtro = (
                self._cliente.table("movimientos_inventario")
                .select(COLUMNAS_MOVIMIENTO)
                .gte("fecha", inicio)
                .lt("fecha", fin)
            )
            if producto_id is not None:
                filtro = filtro.eq("producto_id", producto_id)
            return filtro.order("fecha").order("id")

        return [Movimiento.desde_fila(fila) for fila in todas_las_filas(consulta)]
