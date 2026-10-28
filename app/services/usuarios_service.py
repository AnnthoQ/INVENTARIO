"""Gestión de usuarios para administradores.

La lectura va directo a la tabla profiles (RLS deja a un admin ver todos los
perfiles). Las escrituras pasan por la Edge Function «admin-usuarios», que es
la única con la service_role key.
"""

from __future__ import annotations

from typing import Any

from supabase import Client

from app.core.errores import DatosInvalidos, traducir_error
from app.core.roles import ROLES_ASIGNABLES, Rol
from app.core.validaciones import identificador_a_email, validar_password
from app.models.perfil import COLUMNAS_PERFIL, Perfil

FUNCION_ADMIN_USUARIOS = "admin-usuarios"


class UsuariosService:
    def __init__(self, cliente: Client, dominio_codigos: str) -> None:
        self._cliente = cliente
        self._dominio_codigos = dominio_codigos

    def listar(self) -> list[Perfil]:
        try:
            respuesta = (
                self._cliente.table("profiles")
                .select(COLUMNAS_PERFIL)
                .order("full_name", nullsfirst=False)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            raise traducir_error(exc) from exc
        return [Perfil.desde_fila(fila) for fila in respuesta.data]

    def crear(self, identificador: str, nombre: str, password: str, rol: Rol) -> str:
        """Crea la cuenta y devuelve su id. «identificador» puede ser un código o un correo."""
        email = identificador_a_email(identificador, self._dominio_codigos)
        nombre = nombre.strip()
        if not nombre:
            raise DatosInvalidos("Ingresa el nombre del usuario.")
        validar_password(password)
        resultado = self._invocar(
            {
                "accion": "crear",
                "email": email,
                "password": password,
                "nombre": nombre,
                "rol": self._rol_asignable(rol),
            }
        )
        return resultado["usuario_id"]

    def cambiar_rol(self, usuario_id: str, rol: Rol) -> None:
        self._invocar({"accion": "cambiar_rol", "usuario_id": usuario_id, "rol": self._rol_asignable(rol)})

    def cambiar_estado(self, usuario_id: str, activo: bool) -> None:
        self._invocar({"accion": "cambiar_estado", "usuario_id": usuario_id, "activo": activo})

    def restablecer_password(self, usuario_id: str, password: str) -> None:
        validar_password(password)
        self._invocar({"accion": "restablecer_password", "usuario_id": usuario_id, "password": password})

    @staticmethod
    def _rol_asignable(rol: Rol) -> str:
        if rol not in ROLES_ASIGNABLES:
            raise DatosInvalidos("Solo se pueden asignar los roles Administrador o Trabajador.")
        return rol.value

    def _invocar(self, cuerpo: dict[str, Any]) -> dict[str, Any]:
        try:
            return self._cliente.functions.invoke(
                FUNCION_ADMIN_USUARIOS,
                invoke_options={"body": cuerpo, "responseType": "json"},
            )
        except Exception as exc:  # noqa: BLE001
            raise traducir_error(exc) from exc
