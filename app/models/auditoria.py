"""Entradas de la bitácora de auditoría y su descripción legible."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from app.core.formato import a_decimal, leer_fecha_hora, moneda
from app.core.roles import Rol

COLUMNAS_AUDITORIA = "id, fecha, actor_email, accion, entidad, entidad_id, detalle"

ACCIONES = {
    "usuario.crear": "Alta de usuario",
    "usuario.cambiar_rol": "Cambio de rol",
    "usuario.activar": "Activación de cuenta",
    "usuario.desactivar": "Desactivación de cuenta",
    "usuario.restablecer_password": "Contraseña restablecida",
    "producto.crear": "Alta de producto",
    "producto.editar": "Edición de producto",
    "producto.cambiar_precio": "Cambio de precio",
    "producto.eliminar": "Baja de producto",
}


class FiltroAuditoria(StrEnum):
    TODAS = "todas"
    USUARIOS = "usuarios"
    PRODUCTOS = "productos"
    PRECIOS = "precios"

    @property
    def etiqueta(self) -> str:
        return _ETIQUETAS_FILTRO[self]


_ETIQUETAS_FILTRO = {
    FiltroAuditoria.TODAS: "Todas las acciones",
    FiltroAuditoria.USUARIOS: "Usuarios",
    FiltroAuditoria.PRODUCTOS: "Productos",
    FiltroAuditoria.PRECIOS: "Solo cambios de precio",
}


def _rol(valor: Any) -> str:
    return Rol.desde_texto(valor).etiqueta if valor else "?"


def _valor_producto(campo: str, valor: Any) -> str:
    if campo == "precio":
        return moneda(a_decimal(valor)) or "sin precio"
    if campo == "producto":
        return f"«{valor}»"
    return "—" if valor is None else str(valor)


_CAMPOS_PRODUCTO = {"producto": "nombre", "pg": "página", "precio": "precio"}


@dataclass(frozen=True)
class EntradaAuditoria:
    id: int
    fecha: datetime
    actor_email: str | None
    accion: str
    entidad: str
    entidad_id: str | None
    detalle: Mapping[str, Any]

    @classmethod
    def desde_fila(cls, fila: Mapping[str, Any]) -> EntradaAuditoria:
        return cls(
            id=int(fila["id"]),
            fecha=leer_fecha_hora(fila["fecha"]),  # type: ignore[arg-type]
            actor_email=fila.get("actor_email"),
            accion=fila.get("accion") or "",
            entidad=fila.get("entidad") or "",
            entidad_id=fila.get("entidad_id"),
            detalle=fila.get("detalle") or {},
        )

    @property
    def actor(self) -> str:
        # Sin actor: el cambio se hizo desde el SQL editor de Supabase.
        return self.actor_email or "Sistema"

    @property
    def titulo(self) -> str:
        return ACCIONES.get(self.accion, self.accion)

    @property
    def descripcion(self) -> str:
        d = self.detalle
        if self.entidad == "usuario":
            texto = self._descripcion_usuario(d)
        elif self.entidad == "producto":
            texto = self._descripcion_producto(d)
        else:
            texto = json.dumps(dict(d), ensure_ascii=False)
        if d.get("origen"):
            texto += f" · {d['origen']}"
        return texto

    def _descripcion_usuario(self, d: Mapping[str, Any]) -> str:
        email = d.get("email", "")
        if self.accion == "usuario.crear":
            return f"{email} · {d.get('nombre', '')} · {_rol(d.get('rol'))}"
        if self.accion == "usuario.cambiar_rol":
            return f"{email}: {_rol(d.get('rol_anterior'))} → {_rol(d.get('rol_nuevo'))}"
        return str(email)

    def _descripcion_producto(self, d: Mapping[str, Any]) -> str:
        nombre = f"«{d.get('producto', '')}»"
        if "cambios" in d:
            cambios = []
            for campo, valores in d["cambios"].items():
                antes = _valor_producto(campo, valores.get("antes"))
                despues = _valor_producto(campo, valores.get("despues"))
                cambios.append(f"{_CAMPOS_PRODUCTO.get(campo, campo)} {antes} → {despues}")
            return f"{nombre}: " + "; ".join(cambios)
        valores = d.get("valores", {})
        partes = [nombre]
        if valores.get("pg") is not None:
            partes.append(f"pág. {valores['pg']}")
        partes.append(_valor_producto("precio", valores.get("precio")))
        return " · ".join(partes)
