"""Ventana principal: cabecera de sesión y navegación filtrada por los permisos del rol."""

from __future__ import annotations

import html
from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.core.roles import Permiso
from app.models.perfil import SesionUsuario
from app.services.contenedor import Servicios
from app.views.auditoria_pagina import AuditoriaPagina
from app.views.catalogo_pagina import CatalogoPagina
from app.views.reportes_pagina import ReportesPagina
from app.views.usuarios_pagina import UsuariosPagina


@dataclass(frozen=True)
class Modulo:
    clave: str
    titulo: str
    permiso: Permiso | None
    capa: int  # capa del plan en la que se implementa


MODULOS: tuple[Modulo, ...] = (
    Modulo("inicio", "Inicio", None, 2),
    Modulo("consulta", "Consulta de productos", Permiso.VER_PRODUCTOS, 4),
    Modulo("movimientos", "Entradas y salidas", Permiso.REGISTRAR_MOVIMIENTOS, 4),
    Modulo("catalogo", "Productos y precios", Permiso.GESTIONAR_PRODUCTOS, 3),
    Modulo("reportes", "Reportes", Permiso.VER_REPORTES, 3),
    Modulo("usuarios", "Usuarios", Permiso.GESTIONAR_USUARIOS, 3),
    Modulo("auditoria", "Auditoría", Permiso.VER_AUDITORIA, 3),
)


def modulos_visibles(sesion: SesionUsuario) -> list[Modulo]:
    return [m for m in MODULOS if m.permiso is None or sesion.puede(m.permiso)]


def crear_pagina_capa3(clave: str, sesion: SesionUsuario, servicios: Servicios) -> QWidget | None:
    """Páginas del panel de administración; None si el módulo aún no está implementado."""
    if clave == "usuarios":
        return UsuariosPagina(servicios.usuarios, sesion)
    if clave == "catalogo":
        return CatalogoPagina(servicios.productos)
    if clave == "reportes":
        return ReportesPagina(servicios.reportes, servicios.productos)
    if clave == "auditoria":
        return AuditoriaPagina(servicios.auditoria)
    return None


class VentanaPrincipal(QMainWindow):
    cierre_solicitado = Signal()
    bloqueo_solicitado = Signal()
    cambio_password_solicitado = Signal()
    cerrada = Signal()

    def __init__(self, sesion: SesionUsuario, servicios: Servicios | None = None) -> None:
        super().__init__()
        self.setWindowTitle("Inventario")
        self.resize(1200, 760)
        self._paginas: dict[str, QWidget] = {}

        self.navegacion = QListWidget()
        self.navegacion.setObjectName("navegacion")
        self.paginas = QStackedWidget()
        for modulo in modulos_visibles(sesion):
            item = QListWidgetItem(modulo.titulo)
            item.setData(Qt.ItemDataRole.UserRole, modulo.clave)
            self.navegacion.addItem(item)
            pagina = self._crear_pagina(modulo, sesion, servicios)
            self._paginas[modulo.clave] = pagina
            self.paginas.addWidget(pagina)
        self.navegacion.currentRowChanged.connect(self._mostrar_pagina)
        self.navegacion.setCurrentRow(0)

        cuerpo = QHBoxLayout()
        cuerpo.setContentsMargins(0, 0, 0, 0)
        cuerpo.addWidget(self.navegacion)
        cuerpo.addWidget(self.paginas, stretch=1)

        central = QWidget()
        diseno = QVBoxLayout(central)
        diseno.setContentsMargins(0, 0, 0, 0)
        diseno.addWidget(self._cabecera(sesion))
        diseno.addLayout(cuerpo, stretch=1)
        self.setCentralWidget(central)

    @property
    def claves_modulos(self) -> list[str]:
        return list(self._paginas)

    def pagina(self, clave: str) -> QWidget:
        return self._paginas[clave]

    def ir_a(self, clave: str) -> None:
        self.navegacion.setCurrentRow(list(self._paginas).index(clave))

    def _mostrar_pagina(self, fila: int) -> None:
        self.paginas.setCurrentIndex(fila)
        # Las páginas con datos los consultan la primera vez que se muestran.
        al_mostrar = getattr(self.paginas.widget(fila), "al_mostrar", None)
        if al_mostrar is not None:
            al_mostrar()

    def _crear_pagina(self, modulo: Modulo, sesion: SesionUsuario, servicios: Servicios | None) -> QWidget:
        if modulo.clave == "inicio":
            return self._pagina_inicio(sesion)
        pagina = crear_pagina_capa3(modulo.clave, sesion, servicios) if servicios else None
        return pagina or self._pagina_pendiente(modulo)

    def closeEvent(self, evento: QCloseEvent) -> None:
        self.cerrada.emit()
        super().closeEvent(evento)

    def _cabecera(self, sesion: SesionUsuario) -> QFrame:
        perfil = sesion.perfil
        cabecera = QFrame()
        cabecera.setObjectName("cabecera")
        usuario = QLabel(f"<b>{html.escape(perfil.nombre_visible)}</b> · {perfil.rol.etiqueta}")
        usuario.setTextFormat(Qt.TextFormat.RichText)

        boton_password = QPushButton("Cambiar contraseña")
        boton_password.clicked.connect(self.cambio_password_solicitado)
        boton_bloquear = QPushButton("Bloquear")
        boton_bloquear.clicked.connect(self.bloqueo_solicitado)
        boton_salir = QPushButton("Cerrar sesión")
        boton_salir.clicked.connect(self.cierre_solicitado)

        diseno = QHBoxLayout(cabecera)
        diseno.addWidget(usuario)
        diseno.addStretch()
        diseno.addWidget(boton_password)
        diseno.addWidget(boton_bloquear)
        diseno.addWidget(boton_salir)
        return cabecera

    @staticmethod
    def _pagina_inicio(sesion: SesionUsuario) -> QWidget:
        perfil = sesion.perfil
        titulo = QLabel(f"Hola, {perfil.nombre_visible}")
        titulo.setObjectName("titulo")
        detalle = QLabel(f"Ingresaste como {perfil.rol.etiqueta.lower()} ({perfil.email}).")
        detalle.setObjectName("subtitulo")

        pagina = QWidget()
        diseno = QVBoxLayout(pagina)
        diseno.setContentsMargins(24, 24, 24, 24)
        diseno.addWidget(titulo)
        diseno.addWidget(detalle)
        diseno.addStretch()
        return pagina

    @staticmethod
    def _pagina_pendiente(modulo: Modulo) -> QWidget:
        titulo = QLabel(modulo.titulo)
        titulo.setObjectName("titulo")
        detalle = QLabel(f"Este módulo se implementa en la capa {modulo.capa}.")
        detalle.setObjectName("subtitulo")

        pagina = QWidget()
        diseno = QVBoxLayout(pagina)
        diseno.setContentsMargins(24, 24, 24, 24)
        diseno.addWidget(titulo)
        diseno.addWidget(detalle)
        diseno.addStretch()
        return pagina
