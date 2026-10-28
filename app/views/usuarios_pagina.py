"""Página de usuarios: altas, roles, activación y contraseñas.

Las escrituras pasan por la Edge Function «admin-usuarios», que vuelve a
comprobar que quien las pide es un administrador activo.
"""

from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QDialog, QPushButton, QWidget

from app.core.roles import ROLES_CON_ACCESO, Rol
from app.models.perfil import Perfil, SesionUsuario
from app.services.usuarios_service import UsuariosService
from app.views.componentes import Columna, PanelTabla
from app.views.usuario_dialogs import CambiarRolDialog, NuevoUsuarioDialog, RestablecerPasswordDialog

COLUMNAS = (
    Columna("Nombre", lambda p: p.nombre_visible),
    Columna("Usuario o correo", lambda p: p.email),
    Columna("Rol", lambda p: p.rol.etiqueta),
    Columna("Estado", lambda p: "Activa" if p.activo else "Desactivada"),
)


class UsuariosPagina(PanelTabla):
    def __init__(
        self, servicio: UsuariosService, sesion: SesionUsuario, padre: QWidget | None = None
    ) -> None:
        super().__init__(
            COLUMNAS,
            "usuarios.csv",
            "Usuarios",
            "Crea cuentas y cambia su rol o su estado. Desactivar una cuenta le quita el acceso "
            "de inmediato. Cada cambio queda en la auditoría.",
            padre,
        )
        self._servicio = servicio
        self._sesion = sesion
        self._perfiles: list[Perfil] = []
        self.dialogo: QDialog | None = None

        self.boton_nuevo = QPushButton("Nuevo usuario")
        self.boton_rol = QPushButton("Cambiar rol")
        self.boton_estado = QPushButton("Desactivar")
        self.boton_password = QPushButton("Restablecer contraseña")
        self.boton_actualizar = QPushButton("Actualizar")
        self.casilla_sin_acceso = QCheckBox("Mostrar cuentas sin acceso")
        for boton, accion in (
            (self.boton_nuevo, self._nuevo),
            (self.boton_rol, self._cambiar_rol),
            (self.boton_estado, self._cambiar_estado),
            (self.boton_password, self._restablecer_password),
            (self.boton_actualizar, self.cargar),
        ):
            boton.clicked.connect(accion)
            self.agregar_control(boton)
        # Solo filtra lo ya cargado: puede quedar activa mientras se consulta.
        self.fila_resumen.addWidget(self.casilla_sin_acceso)
        self.casilla_sin_acceso.toggled.connect(self._filtrar)
        self.completar_barra()
        self.al_cambiar_seleccion()

    def cargar(self) -> None:
        self.en_segundo_plano(self._servicio.listar, al_terminar=self._al_cargar)

    def _al_cargar(self, perfiles: list[Perfil]) -> None:
        self._perfiles = perfiles
        self._filtrar()

    def _filtrar(self) -> None:
        # Las cuentas sin acceso suelen ser de otras aplicaciones del proyecto.
        if self.casilla_sin_acceso.isChecked():
            visibles = self._perfiles
        else:
            visibles = [p for p in self._perfiles if p.rol in ROLES_CON_ACCESO]
        self.mostrar_filas(visibles)

        activos = [p for p in self._perfiles if p.activo and p.rol in ROLES_CON_ACCESO]
        admins = sum(1 for p in activos if p.rol is Rol.ADMIN)
        desactivadas = sum(1 for p in self._perfiles if not p.activo and p.rol in ROLES_CON_ACCESO)
        sin_acceso = sum(1 for p in self._perfiles if p.rol not in ROLES_CON_ACCESO)
        self.resumen.setText(
            f"Activas: {admins} administrador(es) y {len(activos) - admins} trabajador(es) · "
            f"Desactivadas: {desactivadas} · Sin acceso al inventario: {sin_acceso}"
        )

    def al_cambiar_seleccion(self) -> None:
        perfil = self.seleccion()
        propia = perfil is not None and perfil.id == self._sesion.perfil.id
        # Los cambios sobre la propia cuenta los rechaza también la Edge Function.
        otra = None if propia else perfil
        con_acceso = otra is not None and otra.rol in ROLES_CON_ACCESO
        desactivada = otra is not None and not otra.activo

        self.boton_rol.setEnabled(otra is not None)
        self.boton_rol.setText("Dar acceso" if otra is not None and not con_acceso else "Cambiar rol")
        self.boton_estado.setEnabled(con_acceso)
        self.boton_estado.setText("Activar" if con_acceso and desactivada else "Desactivar")
        self.boton_password.setEnabled(con_acceso)
        aviso_propia = "Tu propia cuenta se gestiona con «Cambiar contraseña», arriba." if propia else ""
        for boton in (self.boton_rol, self.boton_estado, self.boton_password):
            boton.setToolTip(aviso_propia)

    # Acciones -----------------------------------------------------------------

    def _nuevo(self) -> None:
        self._abrir(NuevoUsuarioDialog(self._servicio, self), "Se creó el usuario.")

    def _cambiar_rol(self) -> None:
        perfil = self.seleccion()
        if perfil is not None:
            self._abrir(
                CambiarRolDialog(self._servicio, perfil, self),
                f"Se actualizó el rol de {perfil.nombre_visible}.",
            )

    def _restablecer_password(self) -> None:
        perfil = self.seleccion()
        if perfil is not None:
            self._abrir(
                RestablecerPasswordDialog(self._servicio, perfil, self),
                f"Se restableció la contraseña de {perfil.nombre_visible}.",
            )

    def _cambiar_estado(self) -> None:
        perfil = self.seleccion()
        if perfil is None:
            return
        activar = not perfil.activo
        if not activar and not self.confirmar(
            self,
            "Desactivar cuenta",
            f"¿Desactivar la cuenta de {perfil.nombre_visible}? Perderá el acceso de inmediato "
            "y su sesión se cerrará.",
        ):
            return
        estado = "activó" if activar else "desactivó"
        self.en_segundo_plano(
            self._servicio.cambiar_estado,
            perfil.id,
            activar,
            al_terminar=lambda _: self._recargar(f"Se {estado} la cuenta de {perfil.nombre_visible}."),
        )

    def _abrir(self, dialogo: QDialog, mensaje: str) -> None:
        self.dialogo = dialogo
        dialogo.accepted.connect(lambda: self._recargar(mensaje))
        dialogo.open()

    def _recargar(self, mensaje: str) -> None:
        def mostrar(perfiles: list[Perfil]) -> None:
            self._al_cargar(perfiles)
            self.aviso.exito(mensaje)

        self.en_segundo_plano(self._servicio.listar, al_terminar=mostrar)
