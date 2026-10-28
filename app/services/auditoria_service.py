"""Lectura de la bitácora de auditoría (RLS: solo administradores)."""

from __future__ import annotations

from datetime import date
from typing import Any

from supabase import Client

from app.core.formato import rango_del_dia
from app.models.auditoria import COLUMNAS_AUDITORIA, EntradaAuditoria, FiltroAuditoria
from app.services.consultas import todas_las_filas, validar_rango


class AuditoriaService:
    def __init__(self, cliente: Client) -> None:
        self._cliente = cliente

    def listar(
        self, desde: date, hasta: date, filtro: FiltroAuditoria = FiltroAuditoria.TODAS
    ) -> list[EntradaAuditoria]:
        """Entradas del período, de la más reciente a la más antigua."""
        validar_rango(desde, hasta)
        inicio, fin = rango_del_dia(desde, hasta)

        def consulta() -> Any:
            filtrada = (
                self._cliente.table("auditoria")
                .select(COLUMNAS_AUDITORIA)
                .gte("fecha", inicio)
                .lt("fecha", fin)
            )
            if filtro is FiltroAuditoria.USUARIOS:
                filtrada = filtrada.eq("entidad", "usuario")
            elif filtro is FiltroAuditoria.PRODUCTOS:
                filtrada = filtrada.eq("entidad", "producto")
            elif filtro is FiltroAuditoria.PRECIOS:
                filtrada = filtrada.eq("accion", "producto.cambiar_precio")
            return filtrada.order("fecha", desc=True).order("id", desc=True)

        return [EntradaAuditoria.desde_fila(fila) for fila in todas_las_filas(consulta)]
