"""Formato de importes y fechas, y modelos de la capa 3 (sin red ni interfaz)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.core import formato
from app.models.auditoria import EntradaAuditoria
from app.models.producto import Producto, nombre_repetido
from app.models.reportes import CierreCaja, Movimiento, ResumenVentas, StockProducto, turnos_repetidos
from tests.falsos import AUDITORIA, CIERRES, MOVIMIENTOS, STOCK

# Formato -----------------------------------------------------------------------


def test_moneda_y_enteros() -> None:
    assert formato.moneda(Decimal("1234.5")) == "S/ 1,234.50"
    assert formato.moneda(None) == ""
    assert formato.entero(3767) == "3,767"


def test_las_horas_se_muestran_en_lima() -> None:
    assert formato.fecha_hora(datetime(2026, 10, 24, 20, 34, tzinfo=UTC)) == "24/10/2026 15:34"
    assert formato.fecha(date(2026, 3, 1)) == "01/03/2026"


def test_el_rango_incluye_todo_el_ultimo_dia_en_lima() -> None:
    assert formato.rango_del_dia(date(2026, 3, 1), date(2026, 3, 31)) == (
        "2026-03-01T00:00:00-05:00",
        "2026-04-01T00:00:00-05:00",
    )


def test_normalizar_quita_tildes_mayusculas_y_espacios() -> None:
    assert formato.normalizar("  Lápiz   AZUL ") == "lapiz azul"


def test_a_decimal_no_pierde_centimos() -> None:
    assert formato.a_decimal(2.2) == Decimal("2.2")
    assert formato.a_decimal(None) is None
    assert formato.a_decimal("x") is None


# Productos ---------------------------------------------------------------------


def test_nombre_repetido_ignora_mayusculas_tildes_y_el_propio_producto() -> None:
    productos = [Producto(1, 1, "Lápiz", Decimal(1)), Producto(2, 1, "Borrador", Decimal(1))]
    assert nombre_repetido(" LAPIZ ", productos)
    assert not nombre_repetido("lapiz", productos, excepto_id=1)
    assert not nombre_repetido("Regla", productos)


# Reportes ----------------------------------------------------------------------


def test_cierre_suma_libreria_y_servicios() -> None:
    cierre = CierreCaja.desde_fila(CIERRES[1])
    assert cierre.servicios == Decimal("38.2")
    assert cierre.total_registrado == Decimal("66.2")
    assert cierre.impresion is None


def test_resumen_de_ventas_marca_turnos_con_varios_cierres() -> None:
    cierres = [CierreCaja.desde_fila(fila) for fila in CIERRES[1:]]
    resumen = ResumenVentas.de(cierres)
    assert (resumen.cierres, resumen.dias) == (3, 2)
    assert resumen.libreria == Decimal("140.8")
    assert resumen.servicios == Decimal("98.2")
    assert resumen.yape_plin == Decimal("242.6")
    assert resumen.repetidos == {(date(2026, 10, 24), "Mañana")}
    assert turnos_repetidos(cierres[:1]) == frozenset()


def test_stock_avisa_saldos_distintos_y_negativos() -> None:
    fille, lapiz, folder = (StockProducto.desde_fila(fila) for fila in STOCK)
    assert fille.aviso is None
    assert folder.aviso is None
    assert "vitrina 9" in lapiz.aviso  # type: ignore[operator]
    assert "stock negativo" in lapiz.aviso  # type: ignore[operator]


def test_movimiento_trae_el_producto_relacionado() -> None:
    movimiento = Movimiento.desde_fila(MOVIMIENTOS[0])
    assert (movimiento.producto, movimiento.pagina) == ("Fille", 1)
    assert (movimiento.ubicacion_texto, movimiento.concepto_texto) == ("Almacén", "Ingreso")


# Auditoría ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("accion", "detalle", "esperado"),
    [
        (
            "usuario.crear",
            {"email": "op05@inv.local", "nombre": "Ana", "rol": "trabajador"},
            "op05@inv.local · Ana · Trabajador",
        ),
        ("usuario.desactivar", {"email": "op05@inv.local"}, "op05@inv.local"),
        (
            "producto.crear",
            {"producto": "Regla", "valores": {"pg": 4, "producto": "Regla", "precio": 2.5}},
            "«Regla» · pág. 4 · S/ 2.50",
        ),
        (
            "producto.editar",
            {
                "producto": "B",
                "cambios": {"producto": {"antes": "A", "despues": "B"}, "pg": {"antes": 1, "despues": 2}},
            },
            "«B»: nombre «A» → «B»; página 1 → 2",
        ),
    ],
)
def test_descripciones_de_auditoria(accion: str, detalle: dict, esperado: str) -> None:
    entidad = accion.split(".")[0]
    fila = {
        "id": 1,
        "fecha": "2026-10-29T15:00:00+00:00",
        "accion": accion,
        "entidad": entidad,
        "detalle": detalle,
    }
    assert EntradaAuditoria.desde_fila(fila).descripcion == esperado


def test_auditoria_de_precios_y_cambios_hechos_desde_sql() -> None:
    desde_sql, precio = (EntradaAuditoria.desde_fila(fila) for fila in AUDITORIA)
    assert desde_sql.actor == "Sistema"
    assert desde_sql.titulo == "Cambio de rol"
    assert (
        desde_sql.descripcion == "admin@example.com: Sin acceso → Administrador · SQL al desplegar la capa 2"
    )
    assert precio.titulo == "Cambio de precio"
    assert precio.descripcion == "«Fille»: precio S/ 1.00 → S/ 1.20"
