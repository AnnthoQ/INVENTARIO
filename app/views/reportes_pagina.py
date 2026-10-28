"""Página de reportes: ventas de caja, más vendidos, stock actual y movimientos (kárdex)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from PySide6.QtWidgets import QComboBox, QPushButton, QTabWidget, QVBoxLayout, QWidget

from app.core import formato
from app.core.formato import moneda
from app.models.producto import Producto
from app.models.reportes import (
    CierreCaja,
    Movimiento,
    ProductoVendido,
    ResumenVentas,
    StockProducto,
    turnos_repetidos,
)
from app.services.productos_service import ProductosService
from app.services.reportes_service import ReportesService
from app.views.componentes import Columna, PanelTabla, RangoFechas, encabezado

_MONEDA = {"texto": moneda, "numerica": True}

COLUMNAS_VENTAS = (
    Columna("Fecha", lambda c: c.fecha),
    Columna("Turno", lambda c: c.turno),
    Columna("Operador", lambda c: c.operador),
    Columna("Librería", lambda c: c.libreria, **_MONEDA),
    Columna("Color", lambda c: c.color, **_MONEDA),
    Columna("A3", lambda c: c.a3, **_MONEDA),
    Columna("Scan", lambda c: c.scan, **_MONEDA),
    Columna("Espiral", lambda c: c.espiral, **_MONEDA),
    Columna("Impresión", lambda c: c.impresion, **_MONEDA),
    Columna("Total registrado", lambda c: c.total_registrado, **_MONEDA),
    Columna("Yape/Plin", lambda c: c.yape_plin, **_MONEDA),
    Columna("Total manual", lambda c: c.total_manual, **_MONEDA),
    Columna("N.º op.", lambda c: c.n_op),
)

COLUMNAS_MAS_VENDIDOS = (
    Columna("Producto", lambda p: p.nombre),
    Columna("Página", lambda p: p.pagina, numerica=True),
    Columna("Cantidad", lambda p: p.cantidad, numerica=True),
    Columna("Importe", lambda p: p.importe, **_MONEDA),
    Columna("Cierres", lambda p: p.cierres, numerica=True),
)

COLUMNAS_STOCK = (
    Columna("Página", lambda s: s.pagina, numerica=True),
    Columna("Producto", lambda s: s.nombre),
    Columna("Almacén", lambda s: s.almacen, numerica=True),
    Columna("Vitrina", lambda s: s.vitrina, numerica=True),
    Columna("Total", lambda s: s.total, numerica=True),
    Columna("Último movimiento", lambda s: s.ultimo_movimiento),
    Columna("Revisar", lambda s: s.aviso is not None),
)

COLUMNAS_MOVIMIENTOS = (
    Columna("Fecha", lambda m: m.fecha),
    Columna("Producto", lambda m: m.producto),
    Columna("Página", lambda m: m.pagina, numerica=True),
    Columna("Ubicación", lambda m: m.ubicacion_texto),
    Columna("Concepto", lambda m: m.concepto_texto),
    Columna("Cantidad", lambda m: m.cantidad, texto=lambda v: f"{v:+,}", numerica=True),
    Columna("Saldo registrado", lambda m: m.saldo, numerica=True),
)

_AVISO_TURNO = "Este turno tiene más de un cierre: revisa si alguno está repetido."


def _inicio_del_mes(dia: date) -> date:
    return dia.replace(day=1)


class _PanelConFechas(PanelTabla):
    """Pestaña con rango de fechas y botón «Consultar»."""

    def __init__(self, columnas: tuple[Columna, ...], nombre_csv: str, desde: date, hasta: date) -> None:
        super().__init__(columnas, nombre_csv)
        self.rango = RangoFechas(desde, hasta)
        self.boton_consultar = QPushButton("Consultar")
        self.boton_consultar.clicked.connect(self.cargar)

    def completar_con_fechas(self) -> None:
        self.agregar_control(self.rango)
        self.agregar_control(self.boton_consultar)
        self.completar_barra()


class VentasCajaPanel(_PanelConFechas):
    def __init__(self, servicio: ReportesService) -> None:
        hoy = formato.hoy()
        super().__init__(COLUMNAS_VENTAS, "ventas_caja.csv", _inicio_del_mes(hoy), hoy)
        self._servicio = servicio
        self._repetidos: frozenset[tuple[date, str]] = frozenset()
        self.modelo.aviso = lambda c: _AVISO_TURNO if (c.fecha, c.turno) in self._repetidos else None
        self.completar_con_fechas()

    def cargar(self) -> None:
        self.en_segundo_plano(
            self._servicio.ventas_caja, self.rango.desde, self.rango.hasta, al_terminar=self._mostrar
        )

    def _mostrar(self, cierres: list[CierreCaja]) -> None:
        resumen = ResumenVentas.de(cierres)
        self._repetidos = resumen.repetidos
        self.mostrar_filas(cierres)
        if not cierres:
            self.resumen.setText("No hay cierres de caja en este período.")
            return
        texto = (
            f"{resumen.cierres} cierres en {resumen.dias} días · Librería {moneda(resumen.libreria)} · "
            f"Servicios {moneda(resumen.servicios)} · Total registrado {moneda(resumen.total_registrado)} · "
            f"Yape/Plin {moneda(resumen.yape_plin)} · Total manual {moneda(resumen.total_manual)}"
        )
        if resumen.repetidos:
            texto += (
                f"\n{len(resumen.repetidos)} turno(s) tienen más de un cierre (resaltados). "
                "Revisa si alguno está repetido: los totales suman todos los cierres."
            )
        self.resumen.setText(texto)


class MasVendidosPanel(_PanelConFechas):
    def __init__(self, servicio: ReportesService) -> None:
        hoy = formato.hoy()
        super().__init__(COLUMNAS_MAS_VENDIDOS, "mas_vendidos.csv", _inicio_del_mes(hoy), hoy)
        self._servicio = servicio
        self.completar_con_fechas()

    def cargar(self) -> None:
        self.en_segundo_plano(self._consultar, self.rango.desde, self.rango.hasta, al_terminar=self._mostrar)

    def _consultar(
        self, desde: date, hasta: date
    ) -> tuple[list[ProductoVendido], frozenset[tuple[date, str]]]:
        # Los turnos con varios cierres pueden contar dos veces los mismos productos.
        return self._servicio.mas_vendidos(desde, hasta), turnos_repetidos(
            self._servicio.ventas_caja(desde, hasta)
        )

    def _mostrar(self, resultado: tuple[list[ProductoVendido], frozenset[tuple[date, str]]]) -> None:
        productos, repetidos = resultado
        self.mostrar_filas(productos)
        if not productos:
            self.resumen.setText("No hay ventas registradas en los cierres de este período.")
            return
        unidades = sum(p.cantidad for p in productos)
        importe = sum((p.importe for p in productos), Decimal(0))
        texto = f"{len(productos)} productos · {formato.entero(unidades)} unidades · {moneda(importe)}"
        if repetidos:
            texto += (
                f"\nHay {len(repetidos)} turno(s) con más de un cierre en este período: si alguno está "
                "repetido, sus productos se cuentan dos veces (revisa la pestaña Ventas de caja)."
            )
        self.resumen.setText(texto)


class StockPanel(PanelTabla):
    def __init__(self, servicio: ReportesService) -> None:
        super().__init__(COLUMNAS_STOCK, "stock_actual.csv")
        self._servicio = servicio
        self.modelo.aviso = lambda s: s.aviso
        self.boton_actualizar = QPushButton("Actualizar")
        self.boton_actualizar.clicked.connect(self.cargar)
        self.agregar_control(self.boton_actualizar)
        self.completar_barra()

    def cargar(self) -> None:
        self.en_segundo_plano(self._servicio.stock_actual, al_terminar=self._mostrar)

    def _mostrar(self, stock: list[StockProducto]) -> None:
        self.mostrar_filas(stock)
        fechas = [s.ultimo_movimiento for s in stock if s.ultimo_movimiento]
        ultimo = formato.fecha_hora(max(fechas)) if fechas else "ninguno"
        texto = (
            f"{len(stock)} productos · {formato.entero(sum(s.total for s in stock))} unidades · "
            f"Último movimiento registrado: {ultimo}. El stock es la suma de los movimientos."
        )
        por_revisar = sum(1 for s in stock if s.aviso)
        if por_revisar:
            texto += (
                f"\n{por_revisar} producto(s) resaltados tienen un saldo registrado distinto de la suma "
                "de sus movimientos o stock negativo. Conviene confirmarlos con un conteo físico."
            )
        self.resumen.setText(texto)


class MovimientosPanel(_PanelConFechas):
    def __init__(self, servicio: ReportesService, productos: ProductosService) -> None:
        hoy = formato.hoy()
        super().__init__(COLUMNAS_MOVIMIENTOS, "movimientos.csv", hoy - timedelta(days=365), hoy)
        self._servicio = servicio
        self._productos = productos
        self._con_productos = False
        self.combo_producto = QComboBox()
        self.combo_producto.addItem("Todos los productos", None)
        self.agregar_control(self.combo_producto)
        self.completar_con_fechas()

    def cargar(self) -> None:
        if self._con_productos:
            self._consultar()
        else:
            self.en_segundo_plano(self._productos.listar, al_terminar=self._llenar_productos)

    def _llenar_productos(self, productos: list[Producto]) -> None:
        for producto in sorted(productos, key=lambda p: formato.normalizar(p.nombre)):
            self.combo_producto.addItem(f"{producto.nombre} (pág. {producto.pagina})", producto.id)
        self._con_productos = True
        self._consultar()

    def _consultar(self) -> None:
        self.en_segundo_plano(
            self._servicio.movimientos,
            self.rango.desde,
            self.rango.hasta,
            self.combo_producto.currentData(),
            al_terminar=self._mostrar,
        )

    def _mostrar(self, movimientos: list[Movimiento]) -> None:
        self.mostrar_filas(movimientos)
        if not movimientos:
            self.resumen.setText("No hay movimientos en este período.")
            return
        entradas = sum(m.cantidad for m in movimientos if m.cantidad > 0)
        salidas = -sum(m.cantidad for m in movimientos if m.cantidad < 0)
        self.resumen.setText(
            f"{len(movimientos)} movimientos · Entradas: {formato.entero(entradas)} · "
            f"Salidas: {formato.entero(salidas)} (los traslados aparecen como salida de un lugar y "
            "entrada en el otro)"
        )


class ReportesPagina(QWidget):
    def __init__(
        self, reportes: ReportesService, productos: ProductosService, padre: QWidget | None = None
    ) -> None:
        super().__init__(padre)
        self.ventas = VentasCajaPanel(reportes)
        self.mas_vendidos = MasVendidosPanel(reportes)
        self.stock = StockPanel(reportes)
        self.movimientos = MovimientosPanel(reportes, productos)

        self.pestanas = QTabWidget()
        self.pestanas.addTab(self.ventas, "Ventas de caja")
        self.pestanas.addTab(self.mas_vendidos, "Más vendidos")
        self.pestanas.addTab(self.stock, "Stock actual")
        self.pestanas.addTab(self.movimientos, "Movimientos (kárdex)")
        self.pestanas.currentChanged.connect(lambda _: self.al_mostrar())

        diseno = QVBoxLayout(self)
        diseno.setContentsMargins(24, 24, 24, 24)
        for etiqueta in encabezado(
            "Reportes",
            "Ventas según los cierres de caja y stock según los movimientos de inventario. "
            "Cada tabla se puede ordenar, filtrar y exportar a CSV para Excel.",
        ):
            diseno.addWidget(etiqueta)
        diseno.addWidget(self.pestanas, stretch=1)

    def al_mostrar(self) -> None:
        # Cada pestaña consulta sus datos la primera vez que se abre.
        panel = self.pestanas.currentWidget()
        if isinstance(panel, PanelTabla):
            panel.al_mostrar()
