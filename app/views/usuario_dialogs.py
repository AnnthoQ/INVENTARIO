"""Diálogos de la página de usuarios: alta, cambio de rol y restablecimiento de contraseña."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QLabel, QLineEdit, QWidget

from app.core.roles import ROLES_ASIGNABLES, Rol
from app.core.validaciones import LONGITUD_MINIMA_PASSWORD
from app.models.perfil import Perfil
from app.services.usuarios_service import UsuariosService
from app.views.componentes import DialogoFormulario

_AYUDA_PASSWORD = (
    f"La contraseña debe tener al menos {LONGITUD_MINIMA_PASSWORD} caracteres, con letras y números."
)
_AYUDA_ROLES = (
    "Administrador: acceso total, incluidos usuarios, precios, reportes y auditoría. "
    "Trabajador: consulta productos y registra movimientos."
)


def _campo_password() -> QLineEdit:
    campo = QLineEdit()
    campo.setEchoMode(QLineEdit.EchoMode.Password)
    return campo


def _combo_roles(actual: Rol | None = None) -> QComboBox:
    combo = QComboBox()
    for rol in ROLES_ASIGNABLES:
        # Qt guarda el texto del enum; se vuelve a convertir con Rol(...).
        combo.addItem(rol.etiqueta, rol.value)
    if actual in ROLES_ASIGNABLES:
        combo.setCurrentIndex(ROLES_ASIGNABLES.index(actual))
    return combo


class NuevoUsuarioDialog(DialogoFormulario):
    def __init__(self, servicio: UsuariosService, padre: QWidget | None = None) -> None:
        super().__init__("Nuevo usuario", padre)
        self._servicio = servicio
        self.campo_usuario = QLineEdit()
        self.campo_usuario.setPlaceholderText("código (p. ej. op05) o correo")
        self.campo_nombre = QLineEdit()
        self.campo_nombre.setPlaceholderText("Nombre y apellido")
        self.campo_nombre.setMaxLength(120)
        self.combo_rol = _combo_roles()
        self.campo_password = _campo_password()
        self.campo_confirmacion = _campo_password()

        self.formulario.addRow("Usuario o correo", self.campo_usuario)
        self.formulario.addRow("Nombre", self.campo_nombre)
        self.formulario.addRow("Rol", self.combo_rol)
        self.formulario.addRow("Contraseña", self.campo_password)
        self.formulario.addRow("Repite la contraseña", self.campo_confirmacion)
        self.agregar_ayuda(
            "Con un código, la persona inicia sesión escribiendo ese código. " + _AYUDA_PASSWORD
        )
        self.terminar_diseno()

    def guardar(self) -> None:
        if self.campo_password.text() != self.campo_confirmacion.text():
            self.mensaje.setText("Las contraseñas no coinciden.")
            return
        self.enviar(
            self._servicio.crear,
            self.campo_usuario.text(),
            self.campo_nombre.text(),
            self.campo_password.text(),
            Rol(self.combo_rol.currentData()),
        )


class CambiarRolDialog(DialogoFormulario):
    def __init__(self, servicio: UsuariosService, perfil: Perfil, padre: QWidget | None = None) -> None:
        super().__init__("Cambiar rol", padre)
        self._servicio = servicio
        self._perfil = perfil
        self.combo_rol = _combo_roles(perfil.rol)
        self.formulario.addRow("Cuenta", QLabel(f"{perfil.nombre_visible} ({perfil.email})"))
        self.formulario.addRow("Rol", self.combo_rol)
        self.agregar_ayuda(_AYUDA_ROLES)
        self.terminar_diseno()

    def guardar(self) -> None:
        rol = Rol(self.combo_rol.currentData())
        if rol is self._perfil.rol:
            self.reject()
            return
        self.enviar(self._servicio.cambiar_rol, self._perfil.id, rol)


class RestablecerPasswordDialog(DialogoFormulario):
    def __init__(self, servicio: UsuariosService, perfil: Perfil, padre: QWidget | None = None) -> None:
        super().__init__("Restablecer contraseña", padre)
        self._servicio = servicio
        self._perfil = perfil
        self.campo_password = _campo_password()
        self.campo_confirmacion = _campo_password()
        self.formulario.addRow("Cuenta", QLabel(f"{perfil.nombre_visible} ({perfil.email})"))
        self.formulario.addRow("Nueva contraseña", self.campo_password)
        self.formulario.addRow("Repite la contraseña", self.campo_confirmacion)
        self.agregar_ayuda(
            _AYUDA_PASSWORD + " La persona puede cambiarla después desde «Cambiar contraseña»."
        )
        self.terminar_diseno()

    def guardar(self) -> None:
        if self.campo_password.text() != self.campo_confirmacion.text():
            self.mensaje.setText("Las contraseñas no coinciden.")
            return
        self.enviar(self._servicio.restablecer_password, self._perfil.id, self.campo_password.text())
