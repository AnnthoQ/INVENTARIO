"""Servicios de la capa 3 contra el cliente falso de Supabase."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from postgrest.exceptions import APIError

from app.core.errores import DatosInvalidos, PermisoDenegado, SinConexion
from app.models.auditoria import FiltroAuditoria
from app.services import consultas
from app.services.auditoria_service import AuditoriaService
from app.services.productos_service import ProductosService, validar_producto
from app.services.reportes_service import ReportesService
from tests.falsos import ClienteFalso, cliente_con_datos


@pytest.fixture
def cliente() -> ClienteFalso:
    return cliente_con_datos()


# Productos ---------------------------------------------------------------------


def test_validar_producto_normaliza_el_nombre_y_el_precio() -> None:
    assert validar_producto(3, "  Folder   azul ", Decimal("5.5")) == {
        "pg": 3,
        "producto": "Folder azul",
        "precio": 5.5,
    }


@pytest.mark.parametrize(
    ("pagina", "nombre", "precio"),
    [
        (3, "   ", Decimal(1)),
        (0, "Regla", Decimal(1)),
        (None, "Regla", Decimal(1)),
        (3, "Regla", None),
        (3, "Regla", Decimal("-0.5")),
        (3, "x" * 121, Decimal(1)),
    ],
)
def test_validar_producto_rechaza_datos_invalidos(
    pagina: int | None, nombre: str, precio: Decimal | None
) -> None:
    with pytest.raises(DatosInvalidos):
        validar_producto(pagina, nombre, precio)


def test_crear_producto(cliente: ClienteFalso) -> None:
    producto = ProductosService(cliente).crear(4, "Regla 30 cm", Decimal("2.50"))

    assert (producto.nombre, producto.precio, producto.pagina) == ("Regla 30 cm", Decimal("2.5"), 4)
    consulta = cliente.tabla("productos").ultima
    assert consulta.operacion == "insert"
    assert consulta.datos == {"pg": 4, "producto": "Regla 30 cm", "precio": 2.5}


def test_actualizar_producto(cliente: ClienteFalso) -> None:
    producto = ProductosService(cliente).actualizar(1, 1, "Fille", Decimal("1.20"))
    assert producto.precio == Decimal("1.2")
    assert cliente.tabla("productos").ultima.filtros == [("eq", "id", 1)]


def test_actualizar_bloqueado_por_rls_avisa_al_usuario(cliente: ClienteFalso) -> None:
    cliente.tabla("productos").solo_lectura = True
    with pytest.raises(PermisoDenegado):
        ProductosService(cliente).actualizar(1, 1, "Fille", Decimal("1.20"))


def test_eliminar_producto_con_ventas_explica_por_que_no_se_puede(cliente: ClienteFalso) -> None:
    servicio = ProductosService(cliente)
    fille = servicio.listar()[0]
    cliente.tabla("productos").error = APIError(
        {"code": "23503", "message": "violates foreign key constraint"}
    )

    with pytest.raises(DatosInvalidos, match="«Fille».*movimientos o ventas"):
        servicio.eliminar(fille)


def test_eliminar_producto(cliente: ClienteFalso) -> None:
    servicio = ProductosService(cliente)
    servicio.eliminar(servicio.listar()[2])
    assert [p.nombre for p in servicio.listar()] == ["Fille", "Lápiz"]


def test_listar_lee_todas_las_paginas(cliente: ClienteFalso, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(consultas, "TAMANO_PAGINA", 2)
    assert len(ProductosService(cliente).listar()) == 3
    assert [c.rango for c in cliente.tabla("productos").consultas] == [(0, 1), (2, 3)]


def test_los_errores_de_red_se_traducen(cliente: ClienteFalso) -> None:
    import httpx

    cliente.tabla("productos").error = httpx.ConnectError("sin red")
    with pytest.raises(SinConexion):
        ProductosService(cliente).listar()


# Reportes ----------------------------------------------------------------------


def test_ventas_de_caja_del_periodo(cliente: ClienteFalso) -> None:
    cierres = ReportesService(cliente).ventas_caja(date(2026, 10, 1), date(2026, 10, 31))
    assert [c.id for c in cierres] == [7, 10, 11]
    assert ("gte", "fecha", "2026-10-01") in cliente.tabla("caja_cierres").ultima.filtros


def test_el_rango_invertido_no_llega_al_servidor(cliente: ClienteFalso) -> None:
    with pytest.raises(DatosInvalidos):
        ReportesService(cliente).ventas_caja(date(2026, 10, 31), date(2026, 10, 1))
    assert cliente.tabla("caja_cierres").consultas == []


def test_mas_vendidos_llama_a_la_funcion_de_la_base(cliente: ClienteFalso) -> None:
    vendidos = ReportesService(cliente).mas_vendidos(date(2026, 10, 1), date(2026, 10, 31))
    assert cliente.llamadas_rpc == [
        ("reporte_mas_vendidos", {"p_desde": "2026-10-01", "p_hasta": "2026-10-31"})
    ]
    assert [(v.nombre, v.cantidad, v.importe) for v in vendidos] == [
        ("Fille", 21, Decimal(21)),
        ("Lápiz", 8, Decimal(4)),
    ]


def test_movimientos_usa_los_dias_completos_de_lima(cliente: ClienteFalso) -> None:
    tabla = cliente.tabla("movimientos_inventario")
    tabla.filas[:] = [
        {"id": i, "fecha": fecha, "producto_id": 1, "cantidad_cambio": 1, "productos": {"producto": "Fille"}}
        for i, fecha in enumerate(
            [
                "2026-03-23T04:59:59+00:00",  # 22/03 23:59:59 en Lima
                "2026-03-23T05:00:00+00:00",  # 23/03 00:00 en Lima
                "2026-03-24T04:59:59+00:00",  # 23/03 23:59:59 en Lima
                "2026-03-24T05:00:00+00:00",  # 24/03 00:00 en Lima
            ]
        )
    ]
    movimientos = ReportesService(cliente).movimientos(date(2026, 3, 23), date(2026, 3, 23))
    assert [m.id for m in movimientos] == [1, 2]


def test_movimientos_de_un_producto(cliente: ClienteFalso) -> None:
    movimientos = ReportesService(cliente).movimientos(date(2026, 3, 1), date(2026, 3, 31), producto_id=2)
    assert [m.id for m in movimientos] == [4]
    assert ("eq", "producto_id", 2) in cliente.tabla("movimientos_inventario").ultima.filtros


def test_stock_actual(cliente: ClienteFalso) -> None:
    stock = ReportesService(cliente).stock_actual()
    assert [s.nombre for s in stock if s.aviso] == ["Lápiz"]


# Auditoría ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("filtro", "esperado"),
    [
        (FiltroAuditoria.TODAS, None),
        (FiltroAuditoria.USUARIOS, ("eq", "entidad", "usuario")),
        (FiltroAuditoria.PRODUCTOS, ("eq", "entidad", "producto")),
        (FiltroAuditoria.PRECIOS, ("eq", "accion", "producto.cambiar_precio")),
    ],
)
def test_filtros_de_auditoria(
    cliente: ClienteFalso, filtro: FiltroAuditoria, esperado: tuple[str, str, str] | None
) -> None:
    entradas = AuditoriaService(cliente).listar(date(2026, 10, 1), date(2026, 10, 31), filtro)
    filtros = cliente.tabla("auditoria").ultima.filtros
    igualdades = [f for f in filtros if f[0] == "eq"]
    assert igualdades == ([esperado] if esperado else [])
    assert all(e.fecha.year == 2026 for e in entradas)


def test_auditoria_del_periodo(cliente: ClienteFalso) -> None:
    entradas = AuditoriaService(cliente).listar(date(2026, 10, 29), date(2026, 10, 29))
    assert [e.accion for e in entradas] == ["producto.cambiar_precio"]
