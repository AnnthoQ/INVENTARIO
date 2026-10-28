"""Flujo de sesión: restaurar → login → ventana principal → bloqueo → cierre."""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from app.config import Config
from app.controllers.inactividad import MonitorInactividad
from app.core.auth_service import AuthService
from app.core.errores import ErrorApp, SinConexion
from app.core.tareas import ejecutar
from app.models.perfil import SesionUsuario
from app.services.contenedor import Servicios
from app.views.bloqueo_dialog import BloqueoDialog
from app.views.cambiar_password_dialog import CambiarPasswordDialog
from app.views.login_dialog import LoginDialog
from app.views.ventana_principal import VentanaPrincipal

log = logging.getLogger(__name__)


class ControladorSesion(QObject):
    def __init__(
        self, app: QApplication, auth: AuthService, config: Config, servicios: Servicios | None = None
    ) -> None:
        super().__init__()
        self._app = app
        self._auth = auth
        self._config = config
        self._servicios = servicios
        self.login: LoginDialog | None = None
        self.ventana: VentanaPrincipal | None = None
        self.bloqueo: BloqueoDialog | None = None
        self._cerrando = False
        # Las ventanas se reemplazan entre sí; la app termina solo al cerrar el
        # login o la ventana principal, no al ocultarlos durante el cambio.
        app.setQuitOnLastWindowClosed(False)

        self.monitor = MonitorInactividad(config.minutos_inactividad, self)
        self.monitor.inactivo.connect(self.bloquear)
        app.installEventFilter(self.monitor)

        # Detecta cuentas desactivadas o sesiones revocadas mientras la app está abierta.
        self.verificador = QTimer(self)
        self.verificador.setInterval(config.segundos_verificacion_sesion * 1000)
        self.verificador.timeout.connect(self._verificar_vigencia)

    def iniciar(self) -> None:
        ejecutar(
            self._auth.restaurar_sesion,
            al_terminar=self._al_restaurar,
            al_fallar=lambda error: self.mostrar_login(error.mensaje),
        )

    def _al_restaurar(self, sesion: SesionUsuario | None) -> None:
        if sesion:
            self.mostrar_principal(sesion)
        else:
            self.mostrar_login()

    # Pantallas ----------------------------------------------------------------

    def mostrar_login(self, aviso: str | None = None) -> None:
        self.login = LoginDialog(self._auth, self._config.permitir_recordar_sesion, aviso)
        self.login.sesion_iniciada.connect(self.mostrar_principal)
        self.login.rejected.connect(self._app.quit)
        self.login.show()

    def mostrar_principal(self, sesion: SesionUsuario) -> None:
        self.login = None
        self.ventana = VentanaPrincipal(sesion, self._servicios)
        self.ventana.cierre_solicitado.connect(self.cerrar_sesion)
        self.ventana.bloqueo_solicitado.connect(self.bloquear)
        self.ventana.cambio_password_solicitado.connect(self._cambiar_password)
        self.ventana.cerrada.connect(self._app.quit)
        self.ventana.show()
        self.monitor.iniciar()
        self.verificador.start()

    def bloquear(self) -> None:
        if self.ventana is None or self.bloqueo is not None:
            return
        self.monitor.detener()
        self.bloqueo = BloqueoDialog(self._auth, self.ventana)
        self.bloqueo.desbloqueado.connect(self._al_desbloquear)
        self.bloqueo.cierre_solicitado.connect(self.cerrar_sesion)
        self.bloqueo.open()

    def _al_desbloquear(self) -> None:
        if self.bloqueo is not None:
            self.bloqueo.deleteLater()
            self.bloqueo = None
        self.monitor.iniciar()

    def _cambiar_password(self) -> None:
        dialogo = CambiarPasswordDialog(self._auth, self.ventana)
        if dialogo.exec():
            QMessageBox.information(self.ventana, "Contraseña", "Tu contraseña se cambió correctamente.")

    # Cierre -------------------------------------------------------------------

    def cerrar_sesion(self, aviso: str | None = None) -> None:
        if self._cerrando:
            return
        self._cerrando = True
        self.monitor.detener()
        self.verificador.stop()
        if self.bloqueo is not None:
            self.bloqueo.done(0)
            self.bloqueo = None
        if self.ventana is not None:
            self.ventana.hide()
            self.ventana.deleteLater()
            self.ventana = None

        # El login se muestra cuando termina el cierre: si apareciera antes, un
        # inicio de sesión rápido podría ser revocado por el cierre aún en curso.
        def mostrar_login(_: object = None) -> None:
            self._cerrando = False
            self.mostrar_login(aviso)

        ejecutar(self._auth.cerrar_sesion, al_terminar=mostrar_login, al_fallar=mostrar_login)

    def _verificar_vigencia(self) -> None:
        if self._auth.sesion is None:
            return
        ejecutar(
            self._auth.verificar_sesion_vigente,
            al_terminar=self._al_verificar_vigencia,
            al_fallar=self._al_fallar_verificacion,
        )

    def _al_verificar_vigencia(self, vigente: bool) -> None:
        if not vigente and self.ventana is not None:
            log.info("La sesión dejó de ser válida en el servidor")
            self.cerrar_sesion("Tu sesión terminó: la cuenta fue desactivada o cambió de permisos.")

    @staticmethod
    def _al_fallar_verificacion(error: ErrorApp) -> None:
        # Sin red no se expulsa al usuario; se vuelve a comprobar en el siguiente ciclo.
        if not isinstance(error, SinConexion):
            log.warning("No se pudo verificar la sesión: %s", error.mensaje)
