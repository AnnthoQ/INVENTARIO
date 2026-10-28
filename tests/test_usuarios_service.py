from __future__ import annotations

import pytest
from supabase_functions.errors import FunctionsHttpError

from app.core.errores import DatosInvalidos, PermisoDenegado
from app.core.roles import Rol
from app.services.usuarios_service import FUNCION_ADMIN_USUARIOS, UsuariosService
from tests.falsos import ID_TRABAJADOR, ClienteFalso, cliente_con_usuarios


@pytest.fixture
def cliente() -> ClienteFalso:
    return cliente_con_usuarios()


@pytest.fixture
def servicio(cliente: ClienteFalso) -> UsuariosService:
    return UsuariosService(cliente, "inv.local")


def test_listar(servicio: UsuariosService) -> None:
    perfiles = servicio.listar()
    assert {p.rol for p in perfiles} == {Rol.ADMIN, Rol.TRABAJADOR, Rol.USUARIO}


def test_crear_con_codigo(servicio: UsuariosService, cliente: ClienteFalso) -> None:
    usuario_id = servicio.crear("OP05", " Ana Pérez ", "clave2026", Rol.TRABAJADOR)

    nombre, opciones = cliente.functions.invocaciones[0]
    assert nombre == FUNCION_ADMIN_USUARIOS
    assert opciones["responseType"] == "json"
    assert opciones["body"] == {
        "accion": "crear",
        "email": "op05@inv.local",
        "password": "clave2026",
        "nombre": "Ana Pérez",
        "rol": "trabajador",
    }
    assert usuario_id


def test_crear_valida_antes_de_llamar_al_servidor(servicio: UsuariosService, cliente: ClienteFalso) -> None:
    with pytest.raises(DatosInvalidos):
        servicio.crear("op05", "Ana", "corta", Rol.TRABAJADOR)
    with pytest.raises(DatosInvalidos):
        servicio.crear("op05", "  ", "clave2026", Rol.TRABAJADOR)
    with pytest.raises(DatosInvalidos):
        servicio.crear("op05", "Ana", "clave2026", Rol.HOST)
    assert cliente.functions.invocaciones == []


def test_cambiar_rol_y_estado(servicio: UsuariosService, cliente: ClienteFalso) -> None:
    servicio.cambiar_rol(ID_TRABAJADOR, Rol.ADMIN)
    servicio.cambiar_estado(ID_TRABAJADOR, False)
    servicio.restablecer_password(ID_TRABAJADOR, "nueva2026x")

    cuerpos = [opciones["body"] for _, opciones in cliente.functions.invocaciones]
    assert cuerpos == [
        {"accion": "cambiar_rol", "usuario_id": ID_TRABAJADOR, "rol": "admin"},
        {"accion": "cambiar_estado", "usuario_id": ID_TRABAJADOR, "activo": False},
        {"accion": "restablecer_password", "usuario_id": ID_TRABAJADOR, "password": "nueva2026x"},
    ]


def test_errores_de_la_funcion(servicio: UsuariosService, cliente: ClienteFalso) -> None:
    cliente.functions.error = FunctionsHttpError("Debe quedar al menos un administrador activo", 409)
    with pytest.raises(DatosInvalidos, match="al menos un administrador"):
        servicio.cambiar_estado(ID_TRABAJADOR, False)

    cliente.functions.error = FunctionsHttpError("Solo un administrador activo puede gestionar usuarios", 403)
    with pytest.raises(PermisoDenegado):
        servicio.cambiar_rol(ID_TRABAJADOR, Rol.ADMIN)
