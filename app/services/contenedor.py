"""Servicios que usan las páginas de la ventana principal."""

from __future__ import annotations

from dataclasses import dataclass

from supabase import Client

from app.services.auditoria_service import AuditoriaService
from app.services.productos_service import ProductosService
from app.services.reportes_service import ReportesService
from app.services.usuarios_service import UsuariosService


@dataclass(frozen=True)
class Servicios:
    usuarios: UsuariosService
    productos: ProductosService
    reportes: ReportesService
    auditoria: AuditoriaService

    @classmethod
    def crear(cls, cliente: Client, dominio_codigos: str) -> Servicios:
        # Comparten el cliente de AuthService: todas las peticiones llevan el JWT de la sesión.
        return cls(
            usuarios=UsuariosService(cliente, dominio_codigos),
            productos=ProductosService(cliente),
            reportes=ReportesService(cliente),
            auditoria=AuditoriaService(cliente),
        )
