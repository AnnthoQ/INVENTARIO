"""Páginas del panel de administración (capa 3) con Qt sin pantalla."""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from postgrest.exceptions import APIError
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialogButtonBox

from app.core.roles import Rol
from app.models.auditoria import FiltroAuditoria
from app.models.perfil import Perfil, SesionUsuario
from app.services.contenedor import Servicios
from app.views.auditoria_pagina import AuditoriaPagina
from app.views.catalogo_pagina import CatalogoPagina
from app.views.componentes import PanelTabla
from app.views.reportes_pagina import ReportesPagina
from app.views.usuarios_pagina import UsuariosPagina
from app.views.ventana_principal import VentanaPrincipal
from tests.falsos import ID_ADMIN, ID_INACTIVO, ID_SIN_ACCESO, ID_TRABAJADOR, ClienteFalso, cliente_con_datos

OCTUBRE = (date(2026, 10, 1), date(2026, 10, 31))
MARZO = (date(2026, 3, 1), date(2026, 3, 31))


def sesion(rol: Rol, user_id: str = ID_ADMIN) -> SesionUsuario:
    return SesionUsuario(Perfil(id=user_id, email="admin@example.com", nombre="Admin", rol=rol, activo=True))


def guardar(dialogo: Any) -> None:
    dialogo.botones.button(QDialogButtonBox.StandardButton.Save).click()


def seleccionar(panel: PanelTabla, condicion: Callable[[Any], bool]) -> None:
    for fila in range(panel.proxy.rowCount()):
        if condicion(panel.proxy.fila(panel.proxy.index(fila, 0))):
            panel.tabla.selectRow(fila)
            return
    raise AssertionError("no hay ninguna fila que cumpla la condición")


def textos_columna(panel: PanelTabla, columna: int) -> list[str]:
    return [panel.proxy.index(f, columna).data() for f in range(panel.proxy.rowCount())]


@pytest.fixture
def cliente() -> ClienteFalso:
    return cliente_con_datos()


@pytest.fixture
def servicios(cliente: ClienteFalso) -> Servicios:
    return Servicios.crear(cliente, "inv.local")


def cargar(qtbot, panel: PanelTabla) -> None:  # noqa: ANN001
    panel.al_mostrar()
    qtbot.waitUntil(lambda: panel.cargada and panel.boton_exportar.isEnabled())


# Ventana principal -------------------------------------------------------------


def test_el_admin_ve_las_paginas_de_la_capa_3(qtbot, servicios: Servicios) -> None:
    ventana = VentanaPrincipal(sesion(Rol.ADMIN), servicios)
    qtbot.addWidget(ventana)
    assert isinstance(ventana.pagina("catalogo"), CatalogoPagina)
    assert isinstance(ventana.pagina("reportes"), ReportesPagina)
    assert isinstance(ventana.pagina("usuarios"), UsuariosPagina)
    assert isinstance(ventana.pagina("auditoria"), AuditoriaPagina)


def test_el_trabajador_no_recibe_paginas_de_administracion(qtbot, servicios: Servicios) -> None:
    ventana = VentanaPrincipal(sesion(Rol.TRABAJADOR, ID_TRABAJADOR), servicios)
    qtbot.addWidget(ventana)
    assert ventana.claves_modulos == ["inicio", "consulta", "movimientos"]


def test_las_paginas_cargan_al_abrirse(qtbot, servicios: Servicios, cliente: ClienteFalso) -> None:
    ventana = VentanaPrincipal(sesion(Rol.ADMIN), servicios)
    qtbot.addWidget(ventana)
    assert cliente.tabla("productos").consultas == []

    ventana.ir_a("catalogo")
    pagina = ventana.pagina("catalogo")
    qtbot.waitUntil(lambda: pagina.modelo.rowCount() == 3)


# Catálogo ----------------------------------------------------------------------


def test_catalogo_busca_sin_tildes_y_exporta_lo_visible(qtbot, servicios: Servicios, tmp_path: Path) -> None:
    pagina = CatalogoPagina(servicios.productos)
    qtbot.addWidget(pagina)
    cargar(qtbot, pagina)
    assert pagina.resumen.text() == "3 productos"

    pagina.campo_busqueda.setText("LAPIZ")
    assert pagina.proxy.rowCount() == 1
    assert pagina.resumen.text() == "Mostrando 1 de 3 productos"

    pagina.elegir_ruta = lambda *_: tmp_path / "productos.csv"
    pagina.boton_exportar.click()
    contenido = (tmp_path / "productos.csv").read_text(encoding="utf-8-sig")
    assert contenido.splitlines() == ["Página,Producto,Precio", "2,Lápiz,0.50"]
    assert "Se exportaron 1 filas" in pagina.aviso.text()


def test_catalogo_ordena_por_el_valor_y_no_por_el_texto(qtbot, servicios: Servicios) -> None:
    pagina = CatalogoPagina(servicios.productos)
    qtbot.addWidget(pagina)
    cargar(qtbot, pagina)

    pagina.tabla.sortByColumn(2, Qt.SortOrder.DescendingOrder)
    assert textos_columna(pagina, 2) == ["S/ 5.50", "S/ 1.00", "S/ 0.50"]


def test_crear_producto_desde_el_dialogo(qtbot, servicios: Servicios, cliente: ClienteFalso) -> None:
    pagina = CatalogoPagina(servicios.productos)
    qtbot.addWidget(pagina)
    cargar(qtbot, pagina)
    assert not pagina.boton_editar.isEnabled()

    pagina.boton_nuevo.click()
    dialogo = pagina.dialogo
    assert dialogo is not None
    dialogo.campo_nombre.setText("  lápiz ")
    guardar(dialogo)
    assert dialogo.mensaje.text() == "Ya existe un producto con ese nombre."

    dialogo.campo_nombre.setText("Regla 30 cm")
    dialogo.campo_pagina.setValue(4)
    dialogo.campo_precio.setValue(2.5)
    guardar(dialogo)
    qtbot.waitUntil(lambda: "Se creó «Regla 30 cm»" in pagina.aviso.text())

    assert {"id": 4, "pg": 4, "producto": "Regla 30 cm", "precio": 2.5} in cliente.tabla("productos").filas
    assert pagina.modelo.rowCount() == 4


def test_editar_precio(qtbot, servicios: Servicios, cliente: ClienteFalso) -> None:
    pagina = CatalogoPagina(servicios.productos)
    qtbot.addWidget(pagina)
    cargar(qtbot, pagina)
    seleccionar(pagina, lambda p: p.nombre == "Fille")
    assert pagina.boton_editar.isEnabled()

    pagina.boton_editar.click()
    dialogo = pagina.dialogo
    assert dialogo.campo_nombre.text() == "Fille"
    dialogo.campo_precio.setValue(1.2)
    guardar(dialogo)
    qtbot.waitUntil(lambda: "Se guardó «Fille»" in pagina.aviso.text())
    assert cliente.tabla("productos").filas[0]["precio"] == 1.2


def test_eliminar_pide_confirmacion_y_explica_el_error(
    qtbot, servicios: Servicios, cliente: ClienteFalso
) -> None:
    pagina = CatalogoPagina(servicios.productos)
    qtbot.addWidget(pagina)
    cargar(qtbot, pagina)
    seleccionar(pagina, lambda p: p.nombre == "Fille")

    pagina.confirmar = lambda *_: False
    pagina.boton_eliminar.click()
    assert all(c.operacion == "select" for c in cliente.tabla("productos").consultas)

    pagina.confirmar = lambda *_: True
    cliente.tabla("productos").error = APIError(
        {"code": "23503", "message": "violates foreign key constraint"}
    )
    pagina.boton_eliminar.click()
    qtbot.waitUntil(lambda: "No se puede eliminar «Fille»" in pagina.aviso.text())
    assert pagina.boton_nuevo.isEnabled()


# Usuarios ----------------------------------------------------------------------


def test_usuarios_protege_la_propia_cuenta_y_las_de_otras_apps(qtbot, servicios: Servicios) -> None:
    pagina = UsuariosPagina(servicios.usuarios, sesion(Rol.ADMIN))
    qtbot.addWidget(pagina)
    cargar(qtbot, pagina)
    assert pagina.modelo.rowCount() == 3  # la cuenta sin acceso está oculta
    assert "Activas: 1 administrador(es) y 1 trabajador(es)" in pagina.resumen.text()

    seleccionar(pagina, lambda p: p.id == ID_ADMIN)
    assert not pagina.boton_rol.isEnabled()
    assert not pagina.boton_estado.isEnabled()
    assert not pagina.boton_password.isEnabled()

    seleccionar(pagina, lambda p: p.id == ID_TRABAJADOR)
    assert pagina.boton_estado.isEnabled() and pagina.boton_estado.text() == "Desactivar"
    seleccionar(pagina, lambda p: p.id == ID_INACTIVO)
    assert pagina.boton_estado.text() == "Activar"

    pagina.casilla_sin_acceso.setChecked(True)
    seleccionar(pagina, lambda p: p.id == ID_SIN_ACCESO)
    assert pagina.boton_rol.text() == "Dar acceso"
    assert not pagina.boton_estado.isEnabled()
    assert not pagina.boton_password.isEnabled()


def test_crear_usuario(qtbot, servicios: Servicios, cliente: ClienteFalso) -> None:
    pagina = UsuariosPagina(servicios.usuarios, sesion(Rol.ADMIN))
    qtbot.addWidget(pagina)
    cargar(qtbot, pagina)

    pagina.boton_nuevo.click()
    dialogo = pagina.dialogo
    dialogo.campo_usuario.setText("op05")
    dialogo.campo_nombre.setText("Ana Pérez")
    dialogo.combo_rol.setCurrentIndex(1)  # Administrador
    dialogo.campo_password.setText("clave2026")
    dialogo.campo_confirmacion.setText("otra2026")
    guardar(dialogo)
    assert dialogo.mensaje.text() == "Las contraseñas no coinciden."

    dialogo.campo_confirmacion.setText("clave2026")
    guardar(dialogo)
    qtbot.waitUntil(lambda: pagina.aviso.text() == "Se creó el usuario.")
    _, opciones = cliente.functions.invocaciones[-1]
    assert opciones["body"] == {
        "accion": "crear",
        "email": "op05@inv.local",
        "password": "clave2026",
        "nombre": "Ana Pérez",
        "rol": "admin",
    }


def test_desactivar_pide_confirmacion(qtbot, servicios: Servicios, cliente: ClienteFalso) -> None:
    pagina = UsuariosPagina(servicios.usuarios, sesion(Rol.ADMIN))
    qtbot.addWidget(pagina)
    cargar(qtbot, pagina)
    seleccionar(pagina, lambda p: p.id == ID_TRABAJADOR)

    pagina.confirmar = lambda *_: False
    pagina.boton_estado.click()
    assert cliente.functions.invocaciones == []

    pagina.confirmar = lambda *_: True
    pagina.boton_estado.click()
    qtbot.waitUntil(lambda: "Se desactivó la cuenta" in pagina.aviso.text())
    _, opciones = cliente.functions.invocaciones[-1]
    assert opciones["body"] == {"accion": "cambiar_estado", "usuario_id": ID_TRABAJADOR, "activo": False}


def test_cambiar_rol(qtbot, servicios: Servicios, cliente: ClienteFalso) -> None:
    pagina = UsuariosPagina(servicios.usuarios, sesion(Rol.ADMIN))
    qtbot.addWidget(pagina)
    cargar(qtbot, pagina)
    seleccionar(pagina, lambda p: p.id == ID_TRABAJADOR)

    pagina.boton_rol.click()
    dialogo = pagina.dialogo
    assert dialogo.combo_rol.currentText() == "Trabajador"
    dialogo.combo_rol.setCurrentIndex(1)
    guardar(dialogo)
    qtbot.waitUntil(lambda: "Se actualizó el rol" in pagina.aviso.text())
    _, opciones = cliente.functions.invocaciones[-1]
    assert opciones["body"] == {"accion": "cambiar_rol", "usuario_id": ID_TRABAJADOR, "rol": "admin"}


# Reportes ----------------------------------------------------------------------


def test_ventas_de_caja_resalta_los_turnos_con_varios_cierres(qtbot, servicios: Servicios) -> None:
    pagina = ReportesPagina(servicios.reportes, servicios.productos)
    qtbot.addWidget(pagina)
    panel = pagina.ventas
    panel.rango.establecer(*OCTUBRE)
    cargar(qtbot, panel)

    assert panel.modelo.rowCount() == 3
    assert "3 cierres en 2 días" in panel.resumen.text()
    assert "Librería S/ 140.80" in panel.resumen.text()
    assert "1 turno(s) tienen más de un cierre" in panel.resumen.text()
    avisos = [panel.modelo.index(f, 0).data(Qt.ItemDataRole.ToolTipRole) for f in range(3)]
    assert avisos[0] is None
    assert avisos[1] == avisos[2] is not None


def test_mas_vendidos_advierte_si_hay_cierres_repetidos(
    qtbot, servicios: Servicios, cliente: ClienteFalso
) -> None:
    pagina = ReportesPagina(servicios.reportes, servicios.productos)
    qtbot.addWidget(pagina)
    panel = pagina.mas_vendidos
    panel.rango.establecer(*OCTUBRE)
    pagina.pestanas.setCurrentWidget(panel)
    qtbot.waitUntil(lambda: panel.modelo.rowCount() == 2)

    assert "2 productos · 29 unidades · S/ 25.00" in panel.resumen.text()
    assert "se cuentan dos veces" in panel.resumen.text()
    assert cliente.llamadas_rpc[-1][1] == {"p_desde": "2026-10-01", "p_hasta": "2026-10-31"}


def test_stock_resalta_lo_que_hay_que_revisar(qtbot, servicios: Servicios, tmp_path: Path) -> None:
    pagina = ReportesPagina(servicios.reportes, servicios.productos)
    qtbot.addWidget(pagina)
    panel = pagina.stock
    pagina.pestanas.setCurrentWidget(panel)
    qtbot.waitUntil(lambda: panel.modelo.rowCount() == 3)

    assert "Último movimiento registrado: 23/03/2026 13:43" in panel.resumen.text()
    assert "1 producto(s) resaltados" in panel.resumen.text()
    assert textos_columna(panel, 6) == ["", "Sí", ""]

    panel.elegir_ruta = lambda *_: tmp_path / "stock.csv"
    panel.boton_exportar.click()
    lineas = (tmp_path / "stock.csv").read_text(encoding="utf-8-sig").splitlines()
    assert lineas[0] == "Página,Producto,Almacén,Vitrina,Total,Último movimiento,Revisar"
    assert lineas[2] == "2,Lápiz,0,-8,-8,23/03/2026 13:43,Sí"


def test_movimientos_por_producto(qtbot, servicios: Servicios, cliente: ClienteFalso) -> None:
    pagina = ReportesPagina(servicios.reportes, servicios.productos)
    qtbot.addWidget(pagina)
    panel = pagina.movimientos
    panel.rango.establecer(*MARZO)
    pagina.pestanas.setCurrentWidget(panel)
    qtbot.waitUntil(lambda: panel.modelo.rowCount() == 4)
    assert panel.combo_producto.count() == 4  # «Todos» y los tres productos
    assert "Entradas: 150 · Salidas: 58" in panel.resumen.text()

    panel.combo_producto.setCurrentIndex(panel.combo_producto.findData(2))
    panel.boton_consultar.click()
    qtbot.waitUntil(lambda: panel.modelo.rowCount() == 1)
    assert ("eq", "producto_id", 2) in cliente.tabla("movimientos_inventario").ultima.filtros
    assert textos_columna(panel, 5) == ["-8"]


def test_un_error_del_servidor_se_muestra_en_la_pestana(
    qtbot, servicios: Servicios, cliente: ClienteFalso
) -> None:
    cliente.tabla("stock_actual").error = APIError(
        {"code": "PGRST205", "message": "Could not find the table"}
    )
    pagina = ReportesPagina(servicios.reportes, servicios.productos)
    qtbot.addWidget(pagina)
    pagina.pestanas.setCurrentWidget(pagina.stock)
    qtbot.waitUntil(lambda: "aún no tiene los cambios" in pagina.stock.aviso.text())
    assert pagina.stock.boton_actualizar.isEnabled()


# Auditoría ---------------------------------------------------------------------


def test_auditoria_describe_y_filtra(qtbot, servicios: Servicios, cliente: ClienteFalso) -> None:
    pagina = AuditoriaPagina(servicios.auditoria)
    qtbot.addWidget(pagina)
    pagina.rango.establecer(*OCTUBRE)
    cargar(qtbot, pagina)
    assert textos_columna(pagina, 1) == ["Sistema", "admin@example.com"]
    assert textos_columna(pagina, 3)[1] == "«Fille»: precio S/ 1.00 → S/ 1.20"

    pagina.combo_filtro.setCurrentIndex(pagina.combo_filtro.findData(FiltroAuditoria.PRECIOS.value))
    pagina.boton_consultar.click()
    qtbot.waitUntil(lambda: pagina.modelo.rowCount() == 1)
    assert ("eq", "accion", "producto.cambiar_precio") in cliente.tabla("auditoria").ultima.filtros
