from __future__ import annotations

import httpx
import pytest

from app.core.almacen_tokens import AlmacenTokens
from app.core.auth_service import AuthService
from app.core.errores import (
    AccesoDenegado,
    CredencialesInvalidas,
    DatosInvalidos,
    DemasiadosIntentos,
    SinConexion,
    UsuarioInactivo,
)
from app.core.limitador_intentos import LimitadorIntentos
from app.core.roles import Rol
from tests.falsos import (
    ID_TRABAJADOR,
    ClienteFalso,
    KeyringMemoria,
    cliente_con_usuarios,
)


class Reloj:
    def __init__(self) -> None:
        self.ahora = 0.0

    def __call__(self) -> float:
        return self.ahora


@pytest.fixture
def cliente() -> ClienteFalso:
    return cliente_con_usuarios()


@pytest.fixture
def keyring_memoria() -> KeyringMemoria:
    return KeyringMemoria()


@pytest.fixture
def reloj() -> Reloj:
    return Reloj()


@pytest.fixture
def auth(cliente: ClienteFalso, keyring_memoria: KeyringMemoria, reloj: Reloj) -> AuthService:
    almacen = AlmacenTokens("proyecto", backend=keyring_memoria)
    return AuthService(cliente, almacen, "inv.local", LimitadorIntentos(reloj=reloj))


# Inicio de sesión --------------------------------------------------------------


def test_login_con_codigo_usa_el_dominio_interno(auth: AuthService) -> None:
    sesion = auth.iniciar_sesion("  OP01 ", "clave2026")

    assert sesion.perfil.id == ID_TRABAJADOR
    assert sesion.perfil.rol is Rol.TRABAJADOR
    assert auth.sesion is sesion


def test_login_sin_recordar_no_guarda_token(auth: AuthService, keyring_memoria: KeyringMemoria) -> None:
    auth.iniciar_sesion("op01", "clave2026", recordar=False)
    assert keyring_memoria.tokens == []


def test_login_recordado_guarda_y_rota_el_refresh_token(
    auth: AuthService, cliente: ClienteFalso, keyring_memoria: KeyringMemoria
) -> None:
    auth.iniciar_sesion("op01", "clave2026", recordar=True)
    assert keyring_memoria.tokens == [cliente.auth.sesion.refresh_token]

    cliente.auth.renovar_en_segundo_plano()

    assert keyring_memoria.tokens == [cliente.auth.sesion.refresh_token]


def test_desbloquear_con_sesion_recordada_guarda_el_token_nuevo(
    auth: AuthService, cliente: ClienteFalso, keyring_memoria: KeyringMemoria
) -> None:
    auth.iniciar_sesion("op01", "clave2026", recordar=True)
    assert auth.verificar_password("clave2026")
    assert keyring_memoria.tokens == [cliente.auth.sesion.refresh_token]


def test_un_login_rechazado_no_guarda_el_token_de_esa_cuenta(
    auth: AuthService, keyring_memoria: KeyringMemoria
) -> None:
    auth.iniciar_sesion("op01", "clave2026", recordar=True)
    token_op01 = keyring_memoria.tokens

    with pytest.raises(AccesoDenegado):
        auth.iniciar_sesion("visita@example.com", "visita2026", recordar=True)

    assert keyring_memoria.tokens == token_op01


def test_rol_sin_acceso_es_rechazado_y_se_cierra_la_sesion_de_auth(
    auth: AuthService, cliente: ClienteFalso
) -> None:
    with pytest.raises(AccesoDenegado):
        auth.iniciar_sesion("visita@example.com", "visita2026")

    assert auth.sesion is None
    assert cliente.auth.sesion is None
    assert cliente.auth.cierres == [{"scope": "local"}]


def test_perfil_desactivado_es_rechazado(auth: AuthService, cliente: ClienteFalso) -> None:
    with pytest.raises(UsuarioInactivo):
        auth.iniciar_sesion("op02", "clave2026")
    assert cliente.auth.sesion is None


def test_usuario_bloqueado_en_auth(auth: AuthService, cliente: ClienteFalso) -> None:
    cliente.auth.baneados.add(ID_TRABAJADOR)
    with pytest.raises(UsuarioInactivo):
        auth.iniciar_sesion("op01", "clave2026")


def test_espera_creciente_tras_fallos(auth: AuthService, cliente: ClienteFalso, reloj: Reloj) -> None:
    for _ in range(3):
        with pytest.raises(CredencialesInvalidas):
            auth.iniciar_sesion("op01", "incorrecta1")

    # El cuarto intento ni siquiera llega al servidor, aunque la clave sea correcta.
    with pytest.raises(DemasiadosIntentos) as error:
        auth.iniciar_sesion("op01", "clave2026")
    assert error.value.segundos == 5

    reloj.ahora += 5
    assert auth.iniciar_sesion("op01", "clave2026").perfil.id == ID_TRABAJADOR


def test_sin_red_no_cuenta_como_fallo(auth: AuthService, cliente: ClienteFalso) -> None:
    cliente.auth.sin_red = True
    for _ in range(5):
        with pytest.raises(SinConexion):
            auth.iniciar_sesion("op01", "clave2026")

    cliente.auth.sin_red = False
    assert auth.iniciar_sesion("op01", "clave2026")


def test_identificador_invalido(auth: AuthService) -> None:
    with pytest.raises(DatosInvalidos):
        auth.iniciar_sesion("op 01", "clave2026")


# Restauración ------------------------------------------------------------------


def test_restaurar_sin_token(auth: AuthService) -> None:
    assert auth.restaurar_sesion() is None


def test_restaurar_con_token_valido(
    auth: AuthService, cliente: ClienteFalso, keyring_memoria: KeyringMemoria
) -> None:
    auth.iniciar_sesion("op01", "clave2026", recordar=True)
    token_anterior = keyring_memoria.tokens[0]

    sesion = auth.restaurar_sesion()

    assert sesion is not None and sesion.perfil.id == ID_TRABAJADOR
    assert keyring_memoria.tokens == [cliente.auth.sesion.refresh_token]
    assert keyring_memoria.tokens[0] != token_anterior


def test_restaurar_con_token_revocado_lo_descarta(auth: AuthService, keyring_memoria: KeyringMemoria) -> None:
    keyring_memoria.set_password("inventario:proyecto", "refresh_token", "rt-viejo")

    assert auth.restaurar_sesion() is None
    assert keyring_memoria.tokens == []


def test_restaurar_cuenta_desactivada_descarta_el_token(
    auth: AuthService, cliente: ClienteFalso, keyring_memoria: KeyringMemoria
) -> None:
    auth.iniciar_sesion("op01", "clave2026", recordar=True)
    cliente.perfil(ID_TRABAJADOR)["activo"] = False

    assert auth.restaurar_sesion() is None
    assert keyring_memoria.tokens == []


def test_restaurar_sin_red_conserva_el_token(
    auth: AuthService, cliente: ClienteFalso, keyring_memoria: KeyringMemoria
) -> None:
    auth.iniciar_sesion("op01", "clave2026", recordar=True)
    cliente.auth.sin_red = True

    assert auth.restaurar_sesion() is None
    assert len(keyring_memoria.tokens) == 1


# Sesión activa -----------------------------------------------------------------


def test_verificar_sesion_vigente(auth: AuthService, cliente: ClienteFalso) -> None:
    auth.iniciar_sesion("op01", "clave2026")
    assert auth.verificar_sesion_vigente() is True

    cliente.perfil(ID_TRABAJADOR)["activo"] = False
    assert auth.verificar_sesion_vigente() is False


def test_verificar_sesion_detecta_cambio_de_rol(auth: AuthService, cliente: ClienteFalso) -> None:
    auth.iniciar_sesion("op01", "clave2026")
    cliente.perfil(ID_TRABAJADOR)["role"] = "admin"

    assert auth.verificar_sesion_vigente() is True
    assert auth.sesion.perfil.rol is Rol.ADMIN


def test_verificar_sesion_con_jwt_expirado(auth: AuthService, cliente: ClienteFalso) -> None:
    auth.iniciar_sesion("op01", "clave2026")
    cliente.expirar_jwt()
    assert auth.verificar_sesion_vigente() is False


def test_verificar_sesion_sin_red_no_expulsa(auth: AuthService, cliente: ClienteFalso) -> None:
    auth.iniciar_sesion("op01", "clave2026")
    cliente.perfiles.error = httpx.ConnectError("sin red")
    with pytest.raises(SinConexion):
        auth.verificar_sesion_vigente()


def test_verificar_password(auth: AuthService) -> None:
    auth.iniciar_sesion("op01", "clave2026")
    assert auth.verificar_password("clave2026") is True
    assert auth.verificar_password("otra") is False


def test_cambiar_password(auth: AuthService, cliente: ClienteFalso) -> None:
    auth.iniciar_sesion("op01", "clave2026")

    with pytest.raises(DatosInvalidos):
        auth.cambiar_password("clave2026", "corta")
    with pytest.raises(CredencialesInvalidas):
        auth.cambiar_password("incorrecta", "NuevaClave2027")
    assert cliente.auth.actualizaciones == []

    auth.cambiar_password("clave2026", "NuevaClave2027")
    assert cliente.auth.actualizaciones == [{"password": "NuevaClave2027"}]


def test_cerrar_sesion(auth: AuthService, cliente: ClienteFalso, keyring_memoria: KeyringMemoria) -> None:
    auth.iniciar_sesion("op01", "clave2026", recordar=True)

    auth.cerrar_sesion()

    assert auth.sesion is None
    assert keyring_memoria.tokens == []
    assert cliente.auth.cierres[-1] == {"scope": "local"}
    # Tras cerrar, una renovación posterior ya no se guarda.
    auth.iniciar_sesion("op01", "clave2026")
    cliente.auth.renovar_en_segundo_plano()
    assert keyring_memoria.tokens == []


def test_cuenta_sin_perfil(auth: AuthService, cliente: ClienteFalso) -> None:
    cliente.auth.usuarios["huerfano@inv.local"] = ("00000000-0000-0000-0000-0000000000f1", "clave2026")
    with pytest.raises(AccesoDenegado, match="perfil"):
        auth.iniciar_sesion("huerfano", "clave2026")
