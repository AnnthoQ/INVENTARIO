"""Pruebas de la interfaz con Qt sin pantalla (QT_QPA_PLATFORM=offscreen)."""

from __future__ import annotations

import os
import threading

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt

from app.config import Config
from app.controllers.inactividad import MonitorInactividad
from app.controllers.sesion_controller import ControladorSesion
from app.core.almacen_tokens import AlmacenTokens
from app.core.auth_service import AuthService
from app.core.errores import CredencialesInvalidas
from app.core.roles import Rol
from app.core.tareas import ejecutar
from app.models.perfil import Perfil, SesionUsuario
from app.views.bloqueo_dialog import BloqueoDialog
from app.views.login_dialog import LoginDialog
from app.views.ventana_principal import VentanaPrincipal
from tests.falsos import ID_TRABAJADOR, ClienteFalso, KeyringMemoria, cliente_con_usuarios


def sesion_de(rol: Rol) -> SesionUsuario:
    return SesionUsuario(Perfil(id="x", email="ana@example.com", nombre="Ana", rol=rol, activo=True))


@pytest.fixture
def cliente() -> ClienteFalso:
    return cliente_con_usuarios()


@pytest.fixture
def auth(cliente: ClienteFalso) -> AuthService:
    return AuthService(cliente, AlmacenTokens("proyecto", backend=KeyringMemoria()), "inv.local")


def test_los_callbacks_de_las_tareas_corren_en_el_hilo_principal(qtbot) -> None:
    hilos: dict[str, int] = {}

    def trabajo() -> int:
        hilos["trabajo"] = threading.get_ident()
        return 42

    resultado: list[int] = []

    def al_terminar(valor: int) -> None:
        hilos["callback"] = threading.get_ident()
        resultado.append(valor)

    ejecutar(trabajo, al_terminar=al_terminar)
    qtbot.waitUntil(lambda: resultado == [42])
    assert hilos["callback"] == threading.get_ident()
    assert hilos["trabajo"] != threading.get_ident()


def test_las_tareas_entregan_errores_traducidos(qtbot) -> None:
    errores: list[object] = []

    def falla() -> None:
        raise CredencialesInvalidas()

    ejecutar(falla, al_fallar=errores.append)
    qtbot.waitUntil(lambda: len(errores) == 1)
    assert isinstance(errores[0], CredencialesInvalidas)


def test_login_correcto_emite_la_sesion(qtbot, auth: AuthService) -> None:
    dialogo = LoginDialog(auth, permitir_recordar=True)
    qtbot.addWidget(dialogo)
    dialogo.campo_usuario.setText("op01")
    dialogo.campo_password.setText("clave2026")

    with qtbot.waitSignal(dialogo.sesion_iniciada, timeout=3000) as senal:
        qtbot.mouseClick(dialogo.boton_ingresar, Qt.MouseButton.LeftButton)

    assert senal.args[0].perfil.id == ID_TRABAJADOR
    assert dialogo.campo_password.text() == ""


def test_login_incorrecto_muestra_el_error(qtbot, auth: AuthService) -> None:
    dialogo = LoginDialog(auth, permitir_recordar=False)
    qtbot.addWidget(dialogo)
    dialogo.campo_usuario.setText("op01")
    dialogo.campo_password.setText("incorrecta")

    qtbot.mouseClick(dialogo.boton_ingresar, Qt.MouseButton.LeftButton)

    qtbot.waitUntil(lambda: dialogo.boton_ingresar.isEnabled())
    assert dialogo.mensaje.text() == CredencialesInvalidas.mensaje_por_defecto
    assert dialogo.casilla_recordar.isHidden()


def test_ventana_del_trabajador_solo_muestra_sus_modulos(qtbot) -> None:
    ventana = VentanaPrincipal(sesion_de(Rol.TRABAJADOR))
    qtbot.addWidget(ventana)
    assert ventana.claves_modulos == ["inicio", "consulta", "movimientos"]


def test_ventana_del_admin_muestra_todo(qtbot) -> None:
    ventana = VentanaPrincipal(sesion_de(Rol.ADMIN))
    qtbot.addWidget(ventana)
    assert {"usuarios", "auditoria", "catalogo", "reportes"} <= set(ventana.claves_modulos)


def test_bloqueo_cierra_sesion_tras_tres_fallos(qtbot, auth: AuthService) -> None:
    auth.iniciar_sesion("op01", "clave2026")
    dialogo = BloqueoDialog(auth)
    qtbot.addWidget(dialogo)

    with qtbot.waitSignal(dialogo.cierre_solicitado, timeout=5000):
        for _ in range(3):
            qtbot.waitUntil(lambda: dialogo.boton_desbloquear.isEnabled())
            dialogo.campo_password.setText("incorrecta")
            dialogo.boton_desbloquear.click()


def test_bloqueo_no_se_salta_con_escape(qtbot, auth: AuthService) -> None:
    auth.iniciar_sesion("op01", "clave2026")
    dialogo = BloqueoDialog(auth)
    qtbot.addWidget(dialogo)
    dialogo.show()
    qtbot.keyClick(dialogo, Qt.Key.Key_Escape)
    assert dialogo.isVisible()


def test_monitor_de_inactividad(qtbot) -> None:
    monitor = MonitorInactividad(minutos=0.001)  # 60 ms
    with qtbot.waitSignal(monitor.inactivo, timeout=2000):
        monitor.iniciar()


def test_flujo_completo_de_sesion(qtbot, qapp, auth: AuthService, cliente: ClienteFalso) -> None:
    config = Config(supabase_url="https://x.supabase.co", supabase_key="k", segundos_verificacion_sesion=30)
    controlador = ControladorSesion(qapp, auth, config)

    # Sin sesión recordada aparece el login.
    controlador.iniciar()
    qtbot.waitUntil(lambda: controlador.login is not None and controlador.login.isVisible())

    controlador.login.campo_usuario.setText("op01")
    controlador.login.campo_password.setText("clave2026")
    controlador.login.boton_ingresar.click()
    qtbot.waitUntil(lambda: controlador.ventana is not None and controlador.ventana.isVisible())
    assert controlador.monitor.activo

    # El administrador desactiva la cuenta: la verificación periódica la expulsa.
    cliente.perfil(ID_TRABAJADOR)["activo"] = False
    controlador._verificar_vigencia()
    qtbot.waitUntil(lambda: controlador.login is not None and controlador.login.isVisible())
    assert controlador.ventana is None
    assert "desactivada" in controlador.login.mensaje.text()
    assert auth.sesion is None
    assert not controlador.monitor.activo
    controlador.login.close()
