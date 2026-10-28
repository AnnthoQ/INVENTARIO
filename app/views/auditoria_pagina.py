"""Página de auditoría: quién cambió usuarios, productos y precios, y cuándo."""

from __future__ import annotations

from datetime import timedelta

from PySide6.QtWidgets import QComboBox, QPushButton, QWidget

from app.core import formato
from app.models.auditoria import EntradaAuditoria, FiltroAuditoria
from app.services.auditoria_service import AuditoriaService
from app.views.componentes import Columna, PanelTabla, RangoFechas

COLUMNAS = (
    Columna("Fecha", lambda e: e.fecha),
    Columna("Usuario", lambda e: e.actor),
    Columna("Acción", lambda e: e.titulo),
    Columna("Detalle", lambda e: e.descripcion),
)


class AuditoriaPagina(PanelTabla):
    def __init__(self, servicio: AuditoriaService, padre: QWidget | None = None) -> None:
        super().__init__(
            COLUMNAS,
            "auditoria.csv",
            "Auditoría",
            "Registro de los cambios en usuarios, productos y precios: quién los hizo y cuándo. "
            "Nadie puede editarlo ni borrarlo desde la aplicación.",
            padre,
        )
        self._servicio = servicio
        hoy = formato.hoy()
        self.rango = RangoFechas(hoy - timedelta(days=30), hoy)
        self.combo_filtro = QComboBox()
        for filtro in FiltroAuditoria:
            self.combo_filtro.addItem(filtro.etiqueta, filtro.value)
        self.boton_consultar = QPushButton("Consultar")
        self.boton_consultar.clicked.connect(self.cargar)
        self.agregar_control(self.rango)
        self.agregar_control(self.combo_filtro)
        self.agregar_control(self.boton_consultar)
        self.completar_barra()

    @property
    def filtro(self) -> FiltroAuditoria:
        return FiltroAuditoria(self.combo_filtro.currentData())

    def cargar(self) -> None:
        self.en_segundo_plano(
            self._servicio.listar, self.rango.desde, self.rango.hasta, self.filtro, al_terminar=self._mostrar
        )

    def _mostrar(self, entradas: list[EntradaAuditoria]) -> None:
        self.mostrar_filas(entradas)
        self.resumen.setText(
            f"{len(entradas)} registro(s), del más reciente al más antiguo."
            if entradas
            else "No hay registros en este período."
        )
