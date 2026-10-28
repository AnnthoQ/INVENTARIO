"""Página «Productos y precios»: catálogo editable solo por administradores."""

from __future__ import annotations

from PySide6.QtWidgets import QPushButton, QWidget

from app.core.formato import moneda
from app.models.producto import Producto
from app.services.productos_service import ProductosService
from app.views.componentes import Columna, PanelTabla
from app.views.producto_dialog import ProductoDialog

COLUMNAS = (
    Columna("Página", lambda p: p.pagina, numerica=True),
    Columna("Producto", lambda p: p.nombre),
    Columna("Precio", lambda p: p.precio, texto=moneda, numerica=True),
)


class CatalogoPagina(PanelTabla):
    def __init__(self, servicio: ProductosService, padre: QWidget | None = None) -> None:
        super().__init__(
            COLUMNAS,
            "productos.csv",
            "Productos y precios",
            "Solo los administradores crean, editan y eliminan productos; los trabajadores solo los "
            "consultan. Cada cambio, y en especial cada cambio de precio, queda en la auditoría.",
            padre,
        )
        self._servicio = servicio
        self._productos: list[Producto] = []
        self.dialogo: ProductoDialog | None = None

        self.boton_nuevo = QPushButton("Nuevo producto")
        self.boton_editar = QPushButton("Editar")
        self.boton_eliminar = QPushButton("Eliminar")
        self.boton_actualizar = QPushButton("Actualizar")
        for boton, accion in (
            (self.boton_nuevo, self._nuevo),
            (self.boton_editar, self._editar),
            (self.boton_eliminar, self._eliminar),
            (self.boton_actualizar, self.cargar),
        ):
            boton.clicked.connect(accion)
            self.agregar_control(boton)
        self.completar_barra()
        self.tabla.doubleClicked.connect(lambda _: self._editar())
        self.campo_busqueda.textChanged.connect(self._actualizar_resumen)
        self.al_cambiar_seleccion()

    def cargar(self) -> None:
        self.en_segundo_plano(self._servicio.listar, al_terminar=self._al_cargar)

    def _al_cargar(self, productos: list[Producto]) -> None:
        self._productos = productos
        self.mostrar_filas(productos)
        self._actualizar_resumen()

    def _actualizar_resumen(self) -> None:
        total = len(self._productos)
        visibles = self.proxy.rowCount()
        texto = f"{total} productos" if visibles == total else f"Mostrando {visibles} de {total} productos"
        self.resumen.setText(texto)

    def al_cambiar_seleccion(self) -> None:
        hay_seleccion = self.seleccion() is not None
        self.boton_editar.setEnabled(hay_seleccion)
        self.boton_eliminar.setEnabled(hay_seleccion)

    # Acciones -----------------------------------------------------------------

    def _nuevo(self) -> None:
        self._abrir(ProductoDialog(self._servicio, self._productos, None, self), "creó")

    def _editar(self) -> None:
        producto = self.seleccion()
        if producto is not None:
            self._abrir(ProductoDialog(self._servicio, self._productos, producto, self), "guardó")

    def _abrir(self, dialogo: ProductoDialog, verbo: str) -> None:
        self.dialogo = dialogo
        dialogo.accepted.connect(lambda: self._recargar(f"Se {verbo} «{dialogo.resultado.nombre}»."))
        dialogo.open()

    def _eliminar(self) -> None:
        producto = self.seleccion()
        if producto is None or not self.confirmar(
            self,
            "Eliminar producto",
            f"¿Eliminar «{producto.nombre}» del catálogo? Esta acción no se puede deshacer.",
        ):
            return
        self.en_segundo_plano(
            self._servicio.eliminar,
            producto,
            al_terminar=lambda _: self._recargar(f"Se eliminó «{producto.nombre}»."),
        )

    def _recargar(self, mensaje: str) -> None:
        def mostrar(productos: list[Producto]) -> None:
            self._al_cargar(productos)
            self.aviso.exito(mensaje)

        self.en_segundo_plano(self._servicio.listar, al_terminar=mostrar)
