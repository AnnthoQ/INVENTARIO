"""Perfil de usuario y sesión activa."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.core.roles import ROLES_CON_ACCESO, Permiso, Rol, permisos_de

COLUMNAS_PERFIL = "id, email, full_name, role, activo"


@dataclass(frozen=True)
class Perfil:
    id: str
    email: str
    nombre: str | None
    rol: Rol
    activo: bool

    @classmethod
    def desde_fila(cls, fila: Mapping[str, Any]) -> Perfil:
        return cls(
            id=str(fila["id"]),
            email=fila["email"],
            nombre=fila.get("full_name"),
            rol=Rol.desde_texto(fila.get("role")),
            activo=bool(fila.get("activo", True)),
        )

    @property
    def nombre_visible(self) -> str:
        return self.nombre or self.email.split("@", 1)[0]

    @property
    def tiene_acceso(self) -> bool:
        return self.activo and self.rol in ROLES_CON_ACCESO


@dataclass(frozen=True)
class SesionUsuario:
    perfil: Perfil
    inicio: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def permisos(self) -> frozenset[Permiso]:
        return permisos_de(self.perfil.rol)

    def puede(self, permiso: Permiso) -> bool:
        return permiso in self.permisos

    @property
    def es_admin(self) -> bool:
        return self.perfil.rol is Rol.ADMIN
