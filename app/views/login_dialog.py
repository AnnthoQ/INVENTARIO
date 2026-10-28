"""Ventana de inicio de sesión."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from app.core.auth_service import AuthService
from app.core.errores import ErrorApp
from app.core.tareas import ejecutar
from app.models.perfil import SesionUsuario


class LoginDialog(QDialog):
    sesion_iniciada = Signal(object)  # SesionUsuario

    def __init__(self, auth: AuthService, permitir_recordar: bool, aviso: str | None = None) -> None:
        super().__init__()
        self._auth = auth
        self.setWindowTitle("Inventario · Iniciar sesión")
        self.setMinimumWidth(380)

        titulo = QLabel("Iniciar sesión")
        titulo.setObjectName("titulo")
        subtitulo = QLabel("Usa tu código de usuario o tu correo.")
        subtitulo.setObjectName("subtitulo")

        self.campo_usuario = QLineEdit()
        self.campo_usuario.setPlaceholderText("p. ej. op01 o nombre@empresa.com")
        self.campo_password = QLineEdit()
        self.campo_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.casilla_recordar = QCheckBox("Recordar sesión en este equipo")
        self.casilla_recordar.setVisible(permitir_recordar)

        formulario = QFormLayout()
        formulario.addRow("Usuario o correo", self.campo_usuario)
        formulario.addRow("Contraseña", self.campo_password)

        self.mensaje = QLabel(aviso or "")
        self.mensaje.setObjectName("mensajeError")
        self.mensaje.setWordWrap(True)

        self.boton_ingresar = QPushButton("Ingresar")
        self.boton_ingresar.setDefault(True)
        self.boton_ingresar.clicked.connect(self._ingresar)

        diseno = QVBoxLayout(self)
        diseno.addWidget(titulo)
        diseno.addWidget(subtitulo)
        diseno.addSpacing(8)
        diseno.addLayout(formulario)
        diseno.addWidget(self.casilla_recordar)
        diseno.addWidget(self.mensaje)
        diseno.addWidget(self.boton_ingresar, alignment=Qt.AlignmentFlag.AlignRight)

        self.campo_usuario.setFocus()

    def _ingresar(self) -> None:
        usuario = self.campo_usuario.text()
        if not usuario.strip() or not self.campo_password.text():
            self.mensaje.setText("Ingresa tu usuario y contraseña.")
            return
        self._ocupado(True)
        self.mensaje.setText("")
        ejecutar(
            self._auth.iniciar_sesion,
            usuario,
            self.campo_password.text(),
            self.casilla_recordar.isChecked(),
            al_terminar=self._al_iniciar,
            al_fallar=self._al_fallar,
        )

    def _al_iniciar(self, sesion: SesionUsuario) -> None:
        self.campo_password.clear()
        self.sesion_iniciada.emit(sesion)
        self.accept()

    def _al_fallar(self, error: ErrorApp) -> None:
        self._ocupado(False)
        self.mensaje.setText(error.mensaje)
        self.campo_password.clear()
        self.campo_password.setFocus()

    def _ocupado(self, ocupado: bool) -> None:
        for widget in (self.campo_usuario, self.campo_password, self.casilla_recordar, self.boton_ingresar):
            widget.setEnabled(not ocupado)
        self.boton_ingresar.setText("Ingresando…" if ocupado else "Ingresar")
