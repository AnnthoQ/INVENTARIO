"""Piezas comunes de las páginas: tabla con búsqueda y orden, rango de fechas,
mensajes y exportación a CSV."""

from __future__ import annotations

import csv
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import shiboken6
from PySide6.QtCore import (
    QAbstractTableModel,
    QDate,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QSortFilterProxyModel,
    Qt,
)
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from app.core import formato
from app.core.errores import ErrorApp
from app.core.tareas import ejecutar

_Indice = QModelIndex | QPersistentModelIndex
_COLOR_AVISO = QColor(255, 236, 179)  # ámbar claro: filas que conviene revisar


def texto_por_defecto(valor: Any) -> str:
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return "Sí" if valor else ""
    if isinstance(valor, int):
        return formato.entero(valor)
    if isinstance(valor, Decimal):
        return f"{valor:,.2f}"
    if isinstance(valor, datetime):
        return formato.fecha_hora(valor)
    if isinstance(valor, date):
        return formato.fecha(valor)
    return str(valor)


def valor_csv(valor: Any) -> str:
    """Valores sin formato de moneda ni separador de miles, para que Excel los lea como números."""
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return "Sí" if valor else "No"
    if isinstance(valor, Decimal):
        return f"{valor:.2f}"
    if isinstance(valor, datetime):
        return formato.fecha_hora(valor)
    if isinstance(valor, date):
        return formato.fecha(valor)
    return str(valor)


def clave_orden(valor: Any) -> tuple[int, Any]:
    # Los vacíos van al final y los textos se comparan sin tildes ni mayúsculas.
    if valor is None:
        return (1, "")
    if isinstance(valor, str):
        return (0, formato.normalizar(valor))
    return (0, valor)


@dataclass(frozen=True)
class Columna:
    titulo: str
    valor: Callable[[Any], Any]
    texto: Callable[[Any], str] = texto_por_defecto
    numerica: bool = False

    def mostrar(self, fila: Any) -> str:
        return self.texto(self.valor(fila))


class ModeloTabla(QAbstractTableModel):
    def __init__(self, columnas: Sequence[Columna], padre: QObject | None = None) -> None:
        super().__init__(padre)
        self.columnas = list(columnas)
        # Devuelve un texto (tooltip) para resaltar la fila, o None.
        self.aviso: Callable[[Any], str | None] | None = None
        self._filas: list[Any] = []
        self._busqueda: list[str] = []

    def establecer_filas(self, filas: Sequence[Any]) -> None:
        self.beginResetModel()
        self._filas = list(filas)
        self._busqueda = [
            formato.normalizar(" ".join(c.mostrar(fila) for c in self.columnas)) for fila in self._filas
        ]
        self.endResetModel()

    def fila(self, indice: int) -> Any:
        return self._filas[indice]

    def texto_busqueda(self, indice: int) -> str:
        return self._busqueda[indice]

    def clave(self, indice: _Indice) -> tuple[int, Any]:
        return clave_orden(self.columnas[indice.column()].valor(self._filas[indice.row()]))

    def rowCount(self, padre: _Indice = QModelIndex()) -> int:  # noqa: B008
        return 0 if padre.isValid() else len(self._filas)

    def columnCount(self, padre: _Indice = QModelIndex()) -> int:  # noqa: B008
        return 0 if padre.isValid() else len(self.columnas)

    def headerData(
        self, seccion: int, orientacion: Qt.Orientation, rol: int = Qt.ItemDataRole.DisplayRole
    ) -> Any:
        if orientacion == Qt.Orientation.Horizontal and rol == Qt.ItemDataRole.DisplayRole:
            return self.columnas[seccion].titulo
        return None

    def data(self, indice: _Indice, rol: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not indice.isValid():
            return None
        fila = self._filas[indice.row()]
        columna = self.columnas[indice.column()]
        if rol == Qt.ItemDataRole.DisplayRole:
            return columna.mostrar(fila)
        if rol == Qt.ItemDataRole.TextAlignmentRole:
            horizontal = Qt.AlignmentFlag.AlignRight if columna.numerica else Qt.AlignmentFlag.AlignLeft
            return horizontal | Qt.AlignmentFlag.AlignVCenter
        if rol in (Qt.ItemDataRole.ToolTipRole, Qt.ItemDataRole.BackgroundRole) and self.aviso is not None:
            aviso = self.aviso(fila)
            if aviso:
                return aviso if rol == Qt.ItemDataRole.ToolTipRole else QBrush(_COLOR_AVISO)
        return None


class ProxyTabla(QSortFilterProxyModel):
    """Búsqueda por palabras sin distinguir tildes y orden por el valor real de cada columna."""

    def __init__(self, modelo: ModeloTabla, padre: QObject | None = None) -> None:
        super().__init__(padre)
        self._palabras: list[str] = []
        self.setSourceModel(modelo)

    @property
    def modelo(self) -> ModeloTabla:
        return self.sourceModel()  # type: ignore[return-value]

    def buscar(self, texto: str) -> None:
        palabras = formato.normalizar(texto).split()
        if palabras == self._palabras:
            return
        # Qt 6.9 introdujo begin/endFilterChange; antes se usaba invalidateRowsFilter.
        if hasattr(self, "beginFilterChange"):
            self.beginFilterChange()
            self._palabras = palabras
            self.endFilterChange(QSortFilterProxyModel.Direction.Rows)
        else:
            self._palabras = palabras
            self.invalidateRowsFilter()

    def filterAcceptsRow(self, fila: int, _padre: _Indice) -> bool:
        if not self._palabras:
            return True
        texto = self.modelo.texto_busqueda(fila)
        return all(palabra in texto for palabra in self._palabras)

    def lessThan(self, izquierda: _Indice, derecha: _Indice) -> bool:
        return self.modelo.clave(izquierda) < self.modelo.clave(derecha)

    def fila(self, indice: QModelIndex) -> Any:
        return self.modelo.fila(self.mapToSource(indice).row())

    def filas_visibles(self) -> list[Any]:
        return [self.fila(self.index(i, 0)) for i in range(self.rowCount())]


def crear_tabla(proxy: ProxyTabla) -> QTableView:
    tabla = QTableView()
    tabla.setModel(proxy)
    tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    tabla.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    tabla.setAlternatingRowColors(True)
    tabla.verticalHeader().setVisible(False)
    tabla.horizontalHeader().setStretchLastSection(True)
    # Sin columna de orden inicial: se respeta el orden en que llegan las filas.
    tabla.horizontalHeader().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
    tabla.setSortingEnabled(True)
    return tabla


class Aviso(QLabel):
    """Mensaje bajo la tabla: error, éxito o información."""

    def __init__(self) -> None:
        super().__init__("")
        self.setWordWrap(True)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

    def _mostrar(self, estilo: str, texto: str) -> None:
        self.setObjectName(estilo)
        self.style().unpolish(self)
        self.style().polish(self)
        self.setText(texto)

    def error(self, texto: str) -> None:
        self._mostrar("mensajeError", texto)

    def exito(self, texto: str) -> None:
        self._mostrar("mensajeExito", texto)

    def info(self, texto: str) -> None:
        self._mostrar("subtitulo", texto)

    def limpiar(self) -> None:
        self.setText("")


class RangoFechas(QWidget):
    def __init__(self, desde: date, hasta: date, padre: QWidget | None = None) -> None:
        super().__init__(padre)
        self.campo_desde = self._campo(desde)
        self.campo_hasta = self._campo(hasta)
        diseno = QHBoxLayout(self)
        diseno.setContentsMargins(0, 0, 0, 0)
        diseno.addWidget(QLabel("Desde"))
        diseno.addWidget(self.campo_desde)
        diseno.addWidget(QLabel("hasta"))
        diseno.addWidget(self.campo_hasta)

    @staticmethod
    def _campo(dia: date) -> QDateEdit:
        campo = QDateEdit(QDate(dia.year, dia.month, dia.day))
        campo.setCalendarPopup(True)
        campo.setDisplayFormat("dd/MM/yyyy")
        return campo

    @property
    def desde(self) -> date:
        return self.campo_desde.date().toPython()  # type: ignore[return-value]

    @property
    def hasta(self) -> date:
        return self.campo_hasta.date().toPython()  # type: ignore[return-value]

    def establecer(self, desde: date, hasta: date) -> None:
        self.campo_desde.setDate(QDate(desde.year, desde.month, desde.day))
        self.campo_hasta.setDate(QDate(hasta.year, hasta.month, hasta.day))


def escribir_csv(ruta: Path, columnas: Sequence[Columna], filas: Sequence[Any]) -> None:
    # utf-8-sig: Excel reconoce las tildes. Coma como separador y punto decimal,
    # como en la configuración regional de Perú.
    with ruta.open("w", newline="", encoding="utf-8-sig") as archivo:
        escritor = csv.writer(archivo)
        escritor.writerow([c.titulo for c in columnas])
        for fila in filas:
            escritor.writerow([valor_csv(c.valor(fila)) for c in columnas])


def elegir_ruta_csv(padre: QWidget, nombre_sugerido: str) -> Path | None:
    ruta, _ = QFileDialog.getSaveFileName(
        padre, "Exportar a CSV", str(Path.home() / nombre_sugerido), "CSV para Excel (*.csv)"
    )
    if not ruta:
        return None
    ruta_csv = Path(ruta)
    return ruta_csv if ruta_csv.suffix.lower() == ".csv" else ruta_csv.with_suffix(".csv")


def confirmar(padre: QWidget, titulo: str, texto: str) -> bool:
    respuesta = QMessageBox.question(
        padre,
        titulo,
        texto,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return respuesta == QMessageBox.StandardButton.Yes


def encabezado(titulo: str, descripcion: str) -> tuple[QLabel, QLabel]:
    etiqueta_titulo = QLabel(titulo)
    etiqueta_titulo.setObjectName("titulo")
    etiqueta_descripcion = QLabel(descripcion)
    etiqueta_descripcion.setObjectName("subtitulo")
    etiqueta_descripcion.setWordWrap(True)
    return etiqueta_titulo, etiqueta_descripcion


class PanelTabla(QWidget):
    """Barra de controles, resumen, tabla con búsqueda, mensajes y exportación a CSV.

    Las subclases agregan sus controles a «barra» y llaman a completar_barra().
    Las páginas cargan sus datos la primera vez que se muestran (al_mostrar).
    """

    def __init__(
        self,
        columnas: Sequence[Columna],
        nombre_csv: str,
        titulo: str | None = None,
        descripcion: str = "",
        padre: QWidget | None = None,
    ) -> None:
        super().__init__(padre)
        self.modelo = ModeloTabla(columnas, self)
        self.proxy = ProxyTabla(self.modelo, self)
        self.tabla = crear_tabla(self.proxy)
        self.aviso = Aviso()
        self.resumen = QLabel("")
        self.resumen.setObjectName("subtitulo")
        self.resumen.setWordWrap(True)
        self.campo_busqueda = QLineEdit()
        self.campo_busqueda.setPlaceholderText("Buscar…")
        self.campo_busqueda.setClearButtonEnabled(True)
        self.campo_busqueda.setMinimumWidth(160)
        self.campo_busqueda.setMaximumWidth(280)
        self.campo_busqueda.textChanged.connect(self.proxy.buscar)
        self.boton_exportar = QPushButton("Exportar CSV")
        self.boton_exportar.clicked.connect(self.exportar)
        # Se reemplazan en las pruebas para no abrir diálogos del sistema.
        self.elegir_ruta: Callable[[QWidget, str], Path | None] = elegir_ruta_csv
        self.confirmar: Callable[[QWidget, str, str], bool] = confirmar

        self.cargada = False
        self._nombre_csv = nombre_csv
        self._controles: list[QWidget] = [self.boton_exportar]
        self.tabla.selectionModel().selectionChanged.connect(lambda *_: self.al_cambiar_seleccion())

        self.barra = QHBoxLayout()
        diseno = QVBoxLayout(self)
        if titulo:
            # Página completa de la ventana principal.
            diseno.setContentsMargins(24, 24, 24, 24)
            for etiqueta in encabezado(titulo, descripcion):
                diseno.addWidget(etiqueta)
            diseno.addSpacing(8)
        else:
            # Pestaña dentro de otra página.
            diseno.setContentsMargins(8, 8, 8, 8)
        # Bajo la barra: el resumen y, a su derecha, opciones de vista (casillas).
        self.fila_resumen = QHBoxLayout()
        self.fila_resumen.addWidget(self.resumen, stretch=1)
        diseno.addLayout(self.barra)
        diseno.addLayout(self.fila_resumen)
        diseno.addWidget(self.tabla, stretch=1)
        diseno.addWidget(self.aviso)

    def agregar_control(self, widget: QWidget) -> None:
        self.barra.addWidget(widget)
        self._controles.append(widget)

    def completar_barra(self, buscar: bool = True) -> None:
        self.barra.addStretch()
        if buscar:
            self.barra.addWidget(self.campo_busqueda)
        self.barra.addWidget(self.boton_exportar)

    def seleccion(self) -> Any | None:
        indices = self.tabla.selectionModel().selectedRows()
        return self.proxy.fila(indices[0]) if indices else None

    def mostrar_filas(self, filas: Sequence[Any]) -> None:
        self.modelo.establecer_filas(filas)
        self.tabla.resizeColumnsToContents()
        self.cargada = True
        # Al reemplazar las filas la selección se pierde sin emitir selectionChanged.
        self.al_cambiar_seleccion()

    def al_mostrar(self) -> None:
        if not self.cargada:
            self.cargar()

    def cargar(self) -> None:
        """Las subclases consultan el servicio y llaman a mostrar_filas."""

    def en_segundo_plano(
        self, funcion: Callable[..., Any], *args: Any, al_terminar: Callable[[Any], None]
    ) -> None:
        """Ejecuta una llamada de red con los controles bloqueados y muestra su error, si lo hay."""
        self._ocupado(True)
        self.aviso.info("Cargando…")

        def terminar(resultado: Any) -> None:
            # La página pudo cerrarse (cierre de sesión) mientras esperaba la respuesta.
            if not shiboken6.isValid(self):
                return
            self._ocupado(False)
            self.aviso.limpiar()
            al_terminar(resultado)

        def fallar(error: ErrorApp) -> None:
            if not shiboken6.isValid(self):
                return
            self._ocupado(False)
            self.aviso.error(error.mensaje)

        ejecutar(funcion, *args, al_terminar=terminar, al_fallar=fallar)

    def _ocupado(self, ocupado: bool) -> None:
        for widget in self._controles:
            widget.setEnabled(not ocupado)
        if not ocupado:
            self.al_cambiar_seleccion()

    def al_cambiar_seleccion(self) -> None:
        """Las subclases habilitan o deshabilitan sus botones según la fila elegida."""

    def exportar(self) -> None:
        ruta = self.elegir_ruta(self, self._nombre_csv)
        if ruta is None:
            return
        filas = self.proxy.filas_visibles()
        try:
            escribir_csv(ruta, self.modelo.columnas, filas)
        except OSError as exc:
            self.aviso.error(f"No se pudo guardar el archivo: {exc.strerror or exc}")
            return
        self.aviso.exito(f"Se exportaron {len(filas)} filas a {ruta}.")


class DialogoFormulario(QDialog):
    """Formulario con Guardar/Cancelar que envía los datos en segundo plano.

    Las subclases llenan «formulario», llaman a terminar_diseno() e implementan
    guardar(), que valida y llama a enviar(). Si el servidor acepta, el diálogo
    se cierra con accept() y deja la respuesta en «resultado».
    """

    def __init__(self, titulo: str, padre: QWidget | None = None) -> None:
        super().__init__(padre)
        self.setWindowTitle(titulo)
        self.setMinimumWidth(420)
        self.resultado: Any = None
        self.formulario = QFormLayout()
        self.mensaje = QLabel("")
        self.mensaje.setObjectName("mensajeError")
        self.mensaje.setWordWrap(True)
        self.botones = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.botones.accepted.connect(self.guardar)
        self.botones.rejected.connect(self.reject)
        self.diseno = QVBoxLayout(self)
        self.diseno.addLayout(self.formulario)

    def agregar_ayuda(self, texto: str) -> None:
        ayuda = QLabel(texto)
        ayuda.setObjectName("subtitulo")
        ayuda.setWordWrap(True)
        self.diseno.addWidget(ayuda)

    def terminar_diseno(self) -> None:
        self.diseno.addWidget(self.mensaje)
        self.diseno.addWidget(self.botones)

    def guardar(self) -> None:
        raise NotImplementedError

    def enviar(self, funcion: Callable[..., Any], *args: Any) -> None:
        self.botones.setEnabled(False)
        self.mensaje.setText("")
        ejecutar(funcion, *args, al_terminar=self._al_terminar, al_fallar=self._al_fallar)

    def _al_terminar(self, resultado: Any) -> None:
        if shiboken6.isValid(self):
            self.resultado = resultado
            self.accept()

    def _al_fallar(self, error: ErrorApp) -> None:
        if shiboken6.isValid(self):
            self.botones.setEnabled(True)
            self.mensaje.setText(error.mensaje)
