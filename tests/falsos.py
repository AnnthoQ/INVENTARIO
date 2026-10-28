"""Dobles de prueba del cliente de Supabase y del almacén de credenciales."""

from __future__ import annotations

import copy
import itertools
from datetime import datetime
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


def _comparable(valor: Any) -> Any:
    # Las fechas llegan como texto ISO; se comparan como fechas para respetar el huso horario.
    if isinstance(valor, str):
        try:
            return datetime.fromisoformat(valor)
        except ValueError:
            return valor
    return valor


_COMPARACIONES = {
    "eq": lambda a, b: a == b,
    "gte": lambda a, b: a is not None and a >= b,
    "lte": lambda a, b: a is not None and a <= b,
    "lt": lambda a, b: a is not None and a < b,
}


class ConsultaFalsa:
    """Imita el constructor de consultas de postgrest-py y guarda lo que se pidió."""

    def __init__(self, tabla: TablaFalsa) -> None:
        self._tabla = tabla
        self.operacion = "select"
        self.datos: dict[str, Any] | None = None
        self.filtros: list[tuple[str, str, Any]] = []
        self.orden: list[tuple[str, bool]] = []
        self.rango: tuple[int, int] | None = None

    def select(self, *_columnas: str) -> ConsultaFalsa:
        return self

    def insert(self, datos: dict[str, Any]) -> ConsultaFalsa:
        self.operacion, self.datos = "insert", datos
        return self

    def update(self, datos: dict[str, Any]) -> ConsultaFalsa:
        self.operacion, self.datos = "update", datos
        return self

    def delete(self) -> ConsultaFalsa:
        self.operacion = "delete"
        return self

    def _filtrar(self, operador: str, columna: str, valor: Any) -> ConsultaFalsa:
        self.filtros.append((operador, columna, valor))
        return self

    def eq(self, columna: str, valor: Any) -> ConsultaFalsa:
        return self._filtrar("eq", columna, valor)

    def gte(self, columna: str, valor: Any) -> ConsultaFalsa:
        return self._filtrar("gte", columna, valor)

    def lte(self, columna: str, valor: Any) -> ConsultaFalsa:
        return self._filtrar("lte", columna, valor)

    def lt(self, columna: str, valor: Any) -> ConsultaFalsa:
        return self._filtrar("lt", columna, valor)

    def limit(self, _n: int) -> ConsultaFalsa:
        return self

    def order(self, columna: str, *, desc: bool = False, **_opciones: Any) -> ConsultaFalsa:
        self.orden.append((columna, desc))
        return self

    def range(self, inicio: int, fin: int) -> ConsultaFalsa:
        self.rango = (inicio, fin)
        return self

    def _coincide(self, fila: dict[str, Any]) -> bool:
        return all(
            _COMPARACIONES[operador](_comparable(fila.get(columna)), _comparable(valor))
            for operador, columna, valor in self.filtros
        )

    def execute(self) -> SimpleNamespace:
        tabla = self._tabla
        tabla.consultas.append(self)
        if tabla.error is not None:
            raise tabla.error
        if self.operacion == "insert":
            fila = {"id": max((f.get("id", 0) for f in tabla.filas), default=0) + 1, **(self.datos or {})}
            tabla.filas.append(fila)
            return SimpleNamespace(data=[dict(fila)])

        coincidentes = [f for f in tabla.filas if self._coincide(f)]
        if self.operacion in {"update", "delete"}:
            if tabla.solo_lectura:
                return SimpleNamespace(data=[])
            for fila in coincidentes:
                if self.operacion == "update":
                    fila.update(self.datos or {})
                else:
                    tabla.filas.remove(fila)
            return SimpleNamespace(data=[dict(f) for f in coincidentes])

        filas = [dict(f) for f in coincidentes]
        if self.rango is not None:
            filas = filas[self.rango[0] : self.rango[1] + 1]
        return SimpleNamespace(data=filas)


class TablaFalsa:
    def __init__(self, filas: list[dict[str, Any]]) -> None:
        self.filas = filas
        self.error: Exception | None = None
        # Como RLS: los UPDATE y DELETE no fallan, pero no afectan ninguna fila.
        self.solo_lectura = False
        self.consultas: list[ConsultaFalsa] = []

    @property
    def ultima(self) -> ConsultaFalsa:
        return self.consultas[-1]


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
        self.tablas: dict[str, TablaFalsa] = {"profiles": TablaFalsa([])}
        self.llamadas_rpc: list[tuple[str, dict[str, Any]]] = []
        self.respuestas_rpc: dict[str, list[dict[str, Any]]] = {}
        self.error_rpc: Exception | None = None

    @property
    def perfiles(self) -> TablaFalsa:
        return self.tablas["profiles"]

    def tabla(self, nombre: str) -> TablaFalsa:
        return self.tablas.setdefault(nombre, TablaFalsa([]))

    def table(self, nombre: str) -> ConsultaFalsa:
        return ConsultaFalsa(self.tabla(nombre))

    def rpc(self, nombre: str, parametros: dict[str, Any]) -> SimpleNamespace:
        self.llamadas_rpc.append((nombre, parametros))

        def execute() -> SimpleNamespace:
            if self.error_rpc is not None:
                raise self.error_rpc
            return SimpleNamespace(data=[dict(f) for f in self.respuestas_rpc.get(nombre, [])])

        return SimpleNamespace(execute=execute)

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


# Datos de la capa 3, con la forma que devuelve PostgREST ---------------------

PRODUCTOS = [
    {"id": 1, "pg": 1, "producto": "Fille", "precio": 1},
    {"id": 2, "pg": 2, "producto": "Lápiz", "precio": 0.5},
    {"id": 3, "pg": 3, "producto": "Folder transparente", "precio": 5.5},
]

_CIERRE = {
    "operador": "Roy",
    "color": None,
    "a3": None,
    "scan": None,
    "espiral": None,
    "impresion": None,
    "yape_plin": None,
    "total_manual": None,
    "n_op": "",
    "created_at": None,
}
# El 24/10 el turno mañana se cerró dos veces (10 y 11), como en producción.
CIERRES = [
    {**_CIERRE, "id": 3, "fecha": "2026-09-30", "turno": "Mañana", "libreria_total": 50},
    {
        **_CIERRE,
        "id": 7,
        "fecha": "2026-10-16",
        "turno": "Tarde",
        "operador": "ANNTHO",
        "libreria_total": 28,
        "color": 21,
        "a3": 5,
        "scan": 0.2,
        "espiral": 12,
        "yape_plin": 15,
        "total_manual": 125.6,
        "n_op": "12",
    },
    {
        **_CIERRE,
        "id": 10,
        "fecha": "2026-10-24",
        "turno": "Mañana",
        "libreria_total": 33.9,
        "color": 30,
        "yape_plin": 113.8,
        "total_manual": 155.49,
    },
    {
        **_CIERRE,
        "id": 11,
        "fecha": "2026-10-24",
        "turno": "Mañana",
        "libreria_total": 78.9,
        "color": 30,
        "yape_plin": 113.8,
        "total_manual": 155.49,
    },
]

_FILLE = {"producto": "Fille", "pg": 1}
_LAPIZ = {"producto": "Lápiz", "pg": 2}
MOVIMIENTOS = [
    {"id": 1, "fecha": "2026-03-14T13:30:25+00:00", "producto_id": 1, "ubicacion": "ALMACEN",
     "concepto": "INGRESO", "cantidad_cambio": 100, "saldo_resultante": 100, "productos": _FILLE},
    {"id": 2, "fecha": "2026-03-23T18:41:12+00:00", "producto_id": 1, "ubicacion": "ALMACEN",
     "concepto": "TRASLADO", "cantidad_cambio": -50, "saldo_resultante": 50, "productos": _FILLE},
    {"id": 3, "fecha": "2026-03-23T18:41:14+00:00", "producto_id": 1, "ubicacion": "VITRINA",
     "concepto": "TRASLADO", "cantidad_cambio": 50, "saldo_resultante": 50, "productos": _FILLE},
    {"id": 4, "fecha": "2026-03-23T18:43:32+00:00", "producto_id": 2, "ubicacion": "VITRINA",
     "concepto": "VENTA", "cantidad_cambio": -8, "saldo_resultante": 9, "productos": _LAPIZ},
]  # fmt: skip

STOCK = [
    {"producto_id": 1, "pg": 1, "producto": "Fille", "almacen": 50, "vitrina": 50, "total": 100,
     "ultimo_movimiento": "2026-03-23T18:41:14+00:00", "almacen_registrado": 50, "vitrina_registrado": 50,
     "revisar": False},
    {"producto_id": 2, "pg": 2, "producto": "Lápiz", "almacen": 0, "vitrina": -8, "total": -8,
     "ultimo_movimiento": "2026-03-23T18:43:32+00:00", "almacen_registrado": None, "vitrina_registrado": 9,
     "revisar": True},
    {"producto_id": 3, "pg": 3, "producto": "Folder transparente", "almacen": 0, "vitrina": 0, "total": 0,
     "ultimo_movimiento": None, "almacen_registrado": None, "vitrina_registrado": None, "revisar": False},
]  # fmt: skip

AUDITORIA = [
    {
        "id": 1,
        "fecha": "2026-10-28T22:13:58+00:00",
        "actor_email": None,
        "accion": "usuario.cambiar_rol",
        "entidad": "usuario",
        "entidad_id": ID_ADMIN,
        "detalle": {
            "email": "admin@example.com",
            "rol_anterior": "usuario",
            "rol_nuevo": "admin",
            "origen": "SQL al desplegar la capa 2",
        },
    },
    {
        "id": 2,
        "fecha": "2026-10-29T15:00:00+00:00",
        "actor_email": "admin@example.com",
        "accion": "producto.cambiar_precio",
        "entidad": "producto",
        "entidad_id": "1",
        "detalle": {"producto": "Fille", "cambios": {"precio": {"antes": 1.0, "despues": 1.2}}},
    },
]

MAS_VENDIDOS = [
    {"producto_id": 1, "producto": "Fille", "pg": 1, "cantidad": 21, "importe": 21, "cierres": 1},
    {"producto_id": 2, "producto": "Lápiz", "pg": 2, "cantidad": 8, "importe": 4, "cierres": 2},
]


def cliente_con_datos() -> ClienteFalso:
    cliente = cliente_con_usuarios()
    for nombre, filas in (
        ("productos", PRODUCTOS),
        ("caja_cierres", CIERRES),
        ("movimientos_inventario", MOVIMIENTOS),
        ("stock_actual", STOCK),
        ("auditoria", AUDITORIA),
    ):
        cliente.tabla(nombre).filas.extend(copy.deepcopy(filas))
    cliente.respuestas_rpc["reporte_mas_vendidos"] = copy.deepcopy(MAS_VENDIDOS)
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
