"""Pantalla de bloqueo tras un periodo de inactividad."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from app.core.auth_service import AuthService
from app.core.errores import DemasiadosIntentos, ErrorApp
from app.core.tareas import ejecutar

INTENTOS_MAXIMOS = 3


class BloqueoDialog(QDialog):
    desbloqueado = Signal()
    cierre_solicitado = Signal()

    def __init__(self, auth: AuthService, padre: QWidget | None = None) -> None:
        super().__init__(padre)
        self._auth = auth
        self._fallos = 0
        self.setWindowTitle("Sesión bloqueada")
        self.setModal(True)
        self.setMinimumWidth(360)

        sesion = auth.sesion
        nombre = sesion.perfil.nombre_visible if sesion else ""
        titulo = QLabel("Sesión bloqueada")
        titulo.setObjectName("titulo")
        detalle = QLabel(f"Se bloqueó por inactividad. {nombre}, ingresa tu contraseña para continuar.")
        detalle.setWordWrap(True)

        self.campo_password = QLineEdit()
        self.campo_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.campo_password.setPlaceholderText("Contraseña")

        self.mensaje = QLabel("")
        self.mensaje.setObjectName("mensajeError")
        self.mensaje.setWordWrap(True)

        self.boton_desbloquear = QPushButton("Desbloquear")
        self.boton_desbloquear.setDefault(True)
        self.boton_desbloquear.clicked.connect(self._desbloquear)
        self.boton_salir = QPushButton("Cerrar sesión")
        self.boton_salir.clicked.connect(self._salir)

        botones = QHBoxLayout()
        botones.addWidget(self.boton_salir)
        botones.addStretch()
        botones.addWidget(self.boton_desbloquear)

        diseno = QVBoxLayout(self)
        diseno.addWidget(titulo)
        diseno.addWidget(detalle)
        diseno.addWidget(self.campo_password)
        diseno.addWidget(self.mensaje)
        diseno.addLayout(botones)

    # Ni Esc ni el botón de cerrar de la ventana saltan el bloqueo.
    def reject(self) -> None:
        pass

    def closeEvent(self, evento: QCloseEvent) -> None:
        evento.ignore()

    def _desbloquear(self) -> None:
        if not self.campo_password.text():
            return
        self._ocupado(True)
        ejecutar(
            self._auth.verificar_password,
            self.campo_password.text(),
            al_terminar=self._al_verificar,
            al_fallar=self._al_fallar,
        )

    def _al_verificar(self, correcta: bool) -> None:
        self._ocupado(False)
        self.campo_password.clear()
        if correcta:
            self.desbloqueado.emit()
            self.done(QDialog.DialogCode.Accepted)
            return
        self._fallos += 1
        if self._fallos >= INTENTOS_MAXIMOS:
            self._salir()
            return
        restantes = INTENTOS_MAXIMOS - self._fallos
        self.mensaje.setText(f"Contraseña incorrecta. Te quedan {restantes} intento(s).")

    def _al_fallar(self, error: ErrorApp) -> None:
        self._ocupado(False)
        if isinstance(error, DemasiadosIntentos):
            self._salir()
            return
        self.mensaje.setText(error.mensaje)

    def _salir(self) -> None:
        self.cierre_solicitado.emit()
        self.done(QDialog.DialogCode.Rejected)

    def _ocupado(self, ocupado: bool) -> None:
        for widget in (self.campo_password, self.boton_desbloquear, self.boton_salir):
            widget.setEnabled(not ocupado)
