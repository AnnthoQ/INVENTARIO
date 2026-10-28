"""Dobles de prueba del cliente de Supabase y del almacén de credenciales."""

from __future__ import annotations

import itertools
from types import SimpleNamespace
from typing import Any

import httpx
from keyring.backend import KeyringBackend
from keyring.errors import NoKeyringError, PasswordDeleteError
from postgrest.exceptions import APIError
from supabase_auth.errors import AuthApiError

ID_ADMIN = "00000000-0000-0000-0000-0000000000a1"
ID_TRABAJADOR = "00000000-0000-0000-0000-0000000000b1"
ID_SIN_ACCESO = "00000000-0000-0000-0000-0000000000c1"
ID_INACTIVO = "00000000-0000-0000-0000-0000000000d1"


class AuthFalso:
    def __init__(self) -> None:
        self.usuarios: dict[str, tuple[str, str]] = {}  # email → (id, contraseña)
        self.baneados: set[str] = set()
        self.refresh_validos: dict[str, str] = {}  # refresh token → id
        self.sesion: SimpleNamespace | None = None
        self.callbacks: list[Any] = []
        self.cierres: list[Any] = []
        self.actualizaciones: list[dict[str, Any]] = []
        self.sin_red = False
        self._contador = itertools.count(1)

    def on_auth_state_change(self, callback: Any) -> None:
        self.callbacks.append(callback)

    def _emitir(self, evento: str) -> None:
        for callback in self.callbacks:
            callback(evento, self.sesion)

    def _nueva_sesion(self, user_id: str) -> SimpleNamespace:
        token = f"rt-{next(self._contador)}"
        self.refresh_validos[token] = user_id
        usuario = SimpleNamespace(id=user_id)
        self.sesion = SimpleNamespace(access_token=f"at-{token}", refresh_token=token, user=usuario)
        return SimpleNamespace(user=usuario, session=self.sesion)

    def sign_in_with_password(self, credenciales: dict[str, str]) -> SimpleNamespace:
        if self.sin_red:
            raise httpx.ConnectError("sin red")
        registro = self.usuarios.get(credenciales["email"])
        if registro is None or registro[1] != credenciales["password"]:
            raise AuthApiError("Invalid login credentials", 400, "invalid_credentials")
        if registro[0] in self.baneados:
            raise AuthApiError("User is banned", 400, "user_banned")
        respuesta = self._nueva_sesion(registro[0])
        self._emitir("SIGNED_IN")
        return respuesta

    def refresh_session(self, token: str) -> SimpleNamespace:
        if self.sin_red:
            raise httpx.ConnectError("sin red")
        user_id = self.refresh_validos.pop(token, None)
        if user_id is None:
            raise AuthApiError("Invalid Refresh Token", 400, "refresh_token_not_found")
        respuesta = self._nueva_sesion(user_id)
        self._emitir("TOKEN_REFRESHED")
        return respuesta

    def renovar_en_segundo_plano(self) -> None:
        """Imita la renovación automática del token que hace supabase-py."""
        assert self.sesion is not None
        self.refresh_session(self.sesion.refresh_token)

    def get_session(self) -> SimpleNamespace | None:
        return self.sesion

    def sign_out(self, opciones: Any = None) -> None:
        self.cierres.append(opciones)
        self.sesion = None
        self._emitir("SIGNED_OUT")

    def update_user(self, atributos: dict[str, Any]) -> None:
        self.actualizaciones.append(atributos)


class ConsultaFalsa:
    def __init__(self, tabla: TablaFalsa) -> None:
        self._tabla = tabla
        self._filtros: dict[str, Any] = {}

    def select(self, _columnas: str) -> ConsultaFalsa:
        return self

    def eq(self, columna: str, valor: Any) -> ConsultaFalsa:
        self._filtros[columna] = valor
        return self

    def limit(self, _n: int) -> ConsultaFalsa:
        return self

    def order(self, _columna: str, **_opciones: Any) -> ConsultaFalsa:
        return self

    def execute(self) -> SimpleNamespace:
        if self._tabla.error is not None:
            raise self._tabla.error
        filas = [dict(f) for f in self._tabla.filas if all(f.get(c) == v for c, v in self._filtros.items())]
        return SimpleNamespace(data=filas)


class TablaFalsa:
    def __init__(self, filas: list[dict[str, Any]]) -> None:
        self.filas = filas
        self.error: Exception | None = None


class FuncionesFalsas:
    def __init__(self) -> None:
        self.invocaciones: list[tuple[str, dict[str, Any]]] = []
        self.error: Exception | None = None

    def invoke(self, nombre: str, invoke_options: dict[str, Any]) -> dict[str, Any]:
        self.invocaciones.append((nombre, invoke_options))
        if self.error is not None:
            raise self.error
        return {"ok": True, "usuario_id": "00000000-0000-0000-0000-0000000000e1"}


class ClienteFalso:
    def __init__(self) -> None:
        self.auth = AuthFalso()
        self.functions = FuncionesFalsas()
        self.perfiles = TablaFalsa([])

    def table(self, nombre: str) -> ConsultaFalsa:
        assert nombre == "profiles"
        return ConsultaFalsa(self.perfiles)

    def agregar_usuario(self, user_id: str, email: str, password: str, rol: str, activo: bool = True) -> None:
        self.auth.usuarios[email] = (user_id, password)
        self.perfiles.filas.append(
            {"id": user_id, "email": email, "full_name": None, "role": rol, "activo": activo}
        )

    def perfil(self, user_id: str) -> dict[str, Any]:
        return next(f for f in self.perfiles.filas if f["id"] == user_id)

    def expirar_jwt(self) -> None:
        self.perfiles.error = APIError({"code": "PGRST303", "message": "JWT expired"})


def cliente_con_usuarios() -> ClienteFalso:
    cliente = ClienteFalso()
    cliente.agregar_usuario(ID_ADMIN, "admin@example.com", "admin2026", "admin")
    cliente.agregar_usuario(ID_TRABAJADOR, "op01@inv.local", "clave2026", "trabajador")
    cliente.agregar_usuario(ID_SIN_ACCESO, "visita@example.com", "visita2026", "usuario")
    cliente.agregar_usuario(ID_INACTIVO, "op02@inv.local", "clave2026", "trabajador", activo=False)
    return cliente


class KeyringMemoria(KeyringBackend):
    priority = 1  # type: ignore[assignment]

    def __init__(self) -> None:
        super().__init__()
        self.datos: dict[tuple[str, str], str] = {}

    def set_password(self, service: str, username: str, password: str) -> None:
        self.datos[(service, username)] = password

    def get_password(self, service: str, username: str) -> str | None:
        return self.datos.get((service, username))

    def delete_password(self, service: str, username: str) -> None:
        if self.datos.pop((service, username), None) is None:
            raise PasswordDeleteError("no existe")

    @property
    def tokens(self) -> list[str]:
        return list(self.datos.values())


class KeyringRoto(KeyringBackend):
    priority = 1  # type: ignore[assignment]

    def set_password(self, service: str, username: str, password: str) -> None:
        raise NoKeyringError("sin almacén")

    def get_password(self, service: str, username: str) -> str | None:
        raise NoKeyringError("sin almacén")

    def delete_password(self, service: str, username: str) -> None:
        raise NoKeyringError("sin almacén")
