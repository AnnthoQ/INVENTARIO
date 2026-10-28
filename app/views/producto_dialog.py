"""Alta y edición de un producto del catálogo."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from PySide6.QtWidgets import QDoubleSpinBox, QLineEdit, QSpinBox, QWidget

from app.models.producto import Producto, nombre_repetido
from app.services.productos_service import (
    LONGITUD_MAXIMA_NOMBRE,
    PAGINA_MAXIMA,
    PRECIO_MAXIMO,
    ProductosService,
)
from app.views.componentes import DialogoFormulario


class ProductoDialog(DialogoFormulario):
    def __init__(
        self,
        servicio: ProductosService,
        productos: Sequence[Producto],
        producto: Producto | None = None,
        padre: QWidget | None = None,
    ) -> None:
        super().__init__("Editar producto" if producto else "Nuevo producto", padre)
        self._servicio = servicio
        self._productos = productos
        self._producto = producto

        self.campo_pagina = QSpinBox()
        self.campo_pagina.setRange(1, PAGINA_MAXIMA)
        self.campo_nombre = QLineEdit()
        self.campo_nombre.setMaxLength(LONGITUD_MAXIMA_NOMBRE)
        self.campo_precio = QDoubleSpinBox()
        self.campo_precio.setDecimals(2)
        self.campo_precio.setRange(0, float(PRECIO_MAXIMO))
        self.campo_precio.setSingleStep(0.1)
        self.campo_precio.setPrefix("S/ ")
        if producto is not None:
            self.campo_pagina.setValue(producto.pagina or 1)
            self.campo_nombre.setText(producto.nombre)
            self.campo_precio.setValue(float(producto.precio or 0))

        self.formulario.addRow("Página del catálogo", self.campo_pagina)
        self.formulario.addRow("Nombre", self.campo_nombre)
        self.formulario.addRow("Precio", self.campo_precio)
        self.terminar_diseno()
        self.campo_nombre.setFocus()

    def guardar(self) -> None:
        nombre = self.campo_nombre.text()
        excepto = self._producto.id if self._producto else None
        if nombre_repetido(nombre, self._productos, excepto):
            self.mensaje.setText("Ya existe un producto con ese nombre.")
            return
        pagina = self.campo_pagina.value()
        precio = Decimal(f"{self.campo_precio.value():.2f}")
        if self._producto is None:
            self.enviar(self._servicio.crear, pagina, nombre, precio)
        else:
            self.enviar(self._servicio.actualizar, self._producto.id, pagina, nombre, precio)
