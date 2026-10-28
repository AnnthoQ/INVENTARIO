"""Errores, roles, validaciones, limitador de intentos y almacén de credenciales."""

from __future__ import annotations

import httpx
import pytest
from postgrest.exceptions import APIError
from supabase_auth.errors import AuthApiError
from supabase_functions.errors import FunctionsHttpError

from app.core.almacen_tokens import AlmacenTokens
from app.core.errores import (
    CredencialesInvalidas,
    DatosInvalidos,
    DemasiadosIntentos,
    ErrorServidor,
    PermisoDenegado,
    SesionExpirada,
    SinConexion,
    UsuarioInactivo,
    traducir_error,
)
from app.core.limitador_intentos import LimitadorIntentos
from app.core.roles import ROLES_CON_ACCESO, Permiso, Rol, permisos_de
from app.core.validaciones import identificador_a_email, validar_password
from tests.falsos import KeyringRoto

# Traducción de errores ---------------------------------------------------------


@pytest.mark.parametrize(
    ("excepcion", "esperado"),
    [
        (AuthApiError("Invalid login credentials", 400, "invalid_credentials"), CredencialesInvalidas),
        (AuthApiError("User is banned", 400, "user_banned"), UsuarioInactivo),
        (AuthApiError("Too many", 429, "over_request_rate_limit"), DemasiadosIntentos),
        (AuthApiError("Invalid Refresh Token", 400, "refresh_token_not_found"), SesionExpirada),
        (APIError({"code": "PGRST303", "message": "JWT expired"}), SesionExpirada),
        (APIError({"code": "XX000", "message": "boom"}), ErrorServidor),
        (FunctionsHttpError("Sesión inválida", 401), SesionExpirada),
        (httpx.ConnectError("sin red"), SinConexion),
        (httpx.ReadTimeout("lento"), SinConexion),
    ],
)
def test_traducir_error(excepcion: Exception, esperado: type) -> None:
    assert isinstance(traducir_error(excepcion), esperado)


def test_el_mensaje_del_trigger_de_precios_llega_al_usuario() -> None:
    error = traducir_error(
        APIError({"code": "42501", "message": "Solo un administrador puede modificar precios"})
    )
    assert isinstance(error, PermisoDenegado)
    assert error.mensaje == "Solo un administrador puede modificar precios"


def test_permission_denied_de_postgres_usa_un_mensaje_propio() -> None:
    error = traducir_error(APIError({"code": "42501", "message": "permission denied for table auditoria"}))
    assert error.mensaje == PermisoDenegado.mensaje_por_defecto


def test_las_politicas_rls_usan_un_mensaje_propio() -> None:
    error = traducir_error(
        APIError(
            {"code": "42501", "message": 'new row violates row-level security policy for table "productos"'}
        )
    )
    assert error.mensaje == PermisoDenegado.mensaje_por_defecto


def test_borrar_algo_con_registros_dependientes() -> None:
    error = traducir_error(APIError({"code": "23503", "message": "violates foreign key constraint"}))
    assert isinstance(error, DatosInvalidos)
    assert "dependen" in error.mensaje


@pytest.mark.parametrize("codigo", ["PGRST202", "PGRST205", "42P01"])
def test_falta_una_migracion(codigo: str) -> None:
    error = traducir_error(APIError({"code": codigo, "message": "not found"}))
    assert isinstance(error, ErrorServidor)
    assert "aún no tiene los cambios" in error.mensaje


def test_errores_de_la_edge_function_conservan_su_mensaje() -> None:
    error = traducir_error(FunctionsHttpError("Ya existe un usuario con ese correo o código", 409))
    assert isinstance(error, DatosInvalidos)
    assert "Ya existe" in error.mensaje


# Roles -------------------------------------------------------------------------


def test_el_trabajador_no_edita_precios_ni_usuarios() -> None:
    permisos = permisos_de(Rol.TRABAJADOR)
    assert permisos == {Permiso.VER_PRODUCTOS, Permiso.REGISTRAR_MOVIMIENTOS}
    assert Permiso.EDITAR_PRECIOS not in permisos
    assert Permiso.GESTIONAR_USUARIOS not in permisos


def test_el_admin_tiene_todos_los_permisos() -> None:
    assert permisos_de(Rol.ADMIN) == set(Permiso)


def test_roles_sin_acceso() -> None:
    assert {Rol.ADMIN, Rol.TRABAJADOR} == ROLES_CON_ACCESO
    assert permisos_de(Rol.USUARIO) == set()
    assert Rol.desde_texto("desconocido") is Rol.USUARIO


# Validaciones ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("op01", "op01@inv.local"),
        (" OP01 ", "op01@inv.local"),
        ("ana.perez", "ana.perez@inv.local"),
        ("Dueno@Example.com", "dueno@example.com"),
    ],
)
def test_identificador_a_email(entrada: str, esperado: str) -> None:
    assert identificador_a_email(entrada, "inv.local") == esperado


@pytest.mark.parametrize("entrada", ["", "op 01", "op01@", "a", "op01;drop"])
def test_identificadores_invalidos(entrada: str) -> None:
    with pytest.raises(DatosInvalidos):
        identificador_a_email(entrada, "inv.local")


@pytest.mark.parametrize("password", ["corta1", "sololetras", "12345678", "a1" * 40])
def test_passwords_invalidas(password: str) -> None:
    with pytest.raises(DatosInvalidos):
        validar_password(password)


def test_password_valida() -> None:
    validar_password("clave2026")


# Limitador ---------------------------------------------------------------------


def test_limitador_duplica_la_espera_hasta_el_maximo() -> None:
    ahora = [0.0]
    limitador = LimitadorIntentos(intentos_libres=2, espera_base=5, espera_maxima=12, reloj=lambda: ahora[0])

    limitador.registrar_fallo("x")
    assert limitador.segundos_restantes("x") == 0
    limitador.registrar_fallo("x")
    assert limitador.segundos_restantes("x") == 5
    limitador.registrar_fallo("x")
    assert limitador.segundos_restantes("x") == 10
    limitador.registrar_fallo("x")
    assert limitador.segundos_restantes("x") == 12
    assert limitador.segundos_restantes("otra") == 0

    limitador.registrar_exito("x")
    limitador.verificar("x")


# Almacén de credenciales -------------------------------------------------------


def test_sin_almacen_del_sistema_no_falla() -> None:
    almacen = AlmacenTokens("proyecto", backend=KeyringRoto())
    assert almacen.guardar("rt") is False
    assert almacen.leer() is None
    almacen.borrar()
