"""Cambio de contraseña del usuario actual."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.auth_service import AuthService
from app.core.errores import ErrorApp
from app.core.tareas import ejecutar
from app.core.validaciones import LONGITUD_MINIMA_PASSWORD, validar_password


class CambiarPasswordDialog(QDialog):
    def __init__(self, auth: AuthService, padre: QWidget | None = None) -> None:
        super().__init__(padre)
        self._auth = auth
        self.setWindowTitle("Cambiar contraseña")
        self.setMinimumWidth(380)

        self.campo_actual = QLineEdit()
        self.campo_nueva = QLineEdit()
        self.campo_confirmacion = QLineEdit()
        for campo in (self.campo_actual, self.campo_nueva, self.campo_confirmacion):
            campo.setEchoMode(QLineEdit.EchoMode.Password)

        formulario = QFormLayout()
        formulario.addRow("Contraseña actual", self.campo_actual)
        formulario.addRow("Nueva contraseña", self.campo_nueva)
        formulario.addRow("Repite la nueva", self.campo_confirmacion)

        ayuda = QLabel(f"Mínimo {LONGITUD_MINIMA_PASSWORD} caracteres, con letras y números.")
        ayuda.setObjectName("subtitulo")
        self.mensaje = QLabel("")
        self.mensaje.setObjectName("mensajeError")
        self.mensaje.setWordWrap(True)

        self.botones = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.botones.accepted.connect(self._guardar)
        self.botones.rejected.connect(self.reject)

        diseno = QVBoxLayout(self)
        diseno.addLayout(formulario)
        diseno.addWidget(ayuda)
        diseno.addWidget(self.mensaje)
        diseno.addWidget(self.botones)

    def _guardar(self) -> None:
        nueva = self.campo_nueva.text()
        if nueva != self.campo_confirmacion.text():
            self.mensaje.setText("Las contraseñas nuevas no coinciden.")
            return
        try:
            validar_password(nueva)
        except ErrorApp as error:
            self.mensaje.setText(error.mensaje)
            return
        self.botones.setEnabled(False)
        ejecutar(
            self._auth.cambiar_password,
            self.campo_actual.text(),
            nueva,
            al_terminar=lambda _: self.accept(),
            al_fallar=self._al_fallar,
        )

    def _al_fallar(self, error: ErrorApp) -> None:
        self.botones.setEnabled(True)
        self.mensaje.setText(error.mensaje)
