"""Roles y permisos de la aplicación.

La interfaz usa estos permisos para mostrar u ocultar opciones; la barrera real
son las políticas RLS y los triggers de Supabase (supabase/migrations).
"""

from __future__ import annotations

from enum import StrEnum


class Rol(StrEnum):
    ADMIN = "admin"
    TRABAJADOR = "trabajador"
    # Roles de otras aplicaciones del proyecto, sin acceso al inventario.
    HOST = "host"
    USUARIO = "usuario"

    @property
    def etiqueta(self) -> str:
        return _ETIQUETAS[self]

    @classmethod
    def desde_texto(cls, valor: str | None) -> Rol:
        try:
            return cls(valor)
        except ValueError:
            return cls.USUARIO


_ETIQUETAS = {
    Rol.ADMIN: "Administrador",
    Rol.TRABAJADOR: "Trabajador",
    Rol.HOST: "Host",
    Rol.USUARIO: "Sin acceso",
}

ROLES_CON_ACCESO = frozenset({Rol.ADMIN, Rol.TRABAJADOR})
ROLES_ASIGNABLES = (Rol.TRABAJADOR, Rol.ADMIN)


class Permiso(StrEnum):
    VER_PRODUCTOS = "ver_productos"
    REGISTRAR_MOVIMIENTOS = "registrar_movimientos"
    GESTIONAR_PRODUCTOS = "gestionar_productos"
    EDITAR_PRECIOS = "editar_precios"
    CORREGIR_MOVIMIENTOS = "corregir_movimientos"
    VER_REPORTES = "ver_reportes"
    GESTIONAR_USUARIOS = "gestionar_usuarios"
    VER_AUDITORIA = "ver_auditoria"
    CONFIGURAR_SISTEMA = "configurar_sistema"


PERMISOS_POR_ROL: dict[Rol, frozenset[Permiso]] = {
    Rol.ADMIN: frozenset(Permiso),
    Rol.TRABAJADOR: frozenset({Permiso.VER_PRODUCTOS, Permiso.REGISTRAR_MOVIMIENTOS}),
    Rol.HOST: frozenset(),
    Rol.USUARIO: frozenset(),
}


def permisos_de(rol: Rol) -> frozenset[Permiso]:
    return PERMISOS_POR_ROL.get(rol, frozenset())
