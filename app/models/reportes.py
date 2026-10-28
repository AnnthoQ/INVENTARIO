"""Filas de los reportes del panel de administración."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.core.formato import a_decimal, leer_fecha, leer_fecha_hora

COLUMNAS_CIERRE = (
    "id, fecha, turno, operador, libreria_total, color, a3, scan, espiral, impresion, "
    "yape_plin, total_manual, n_op, created_at"
)
COLUMNAS_MOVIMIENTO = (
    "id, fecha, producto_id, ubicacion, concepto, cantidad_cambio, saldo_resultante, productos(producto, pg)"
)

# Servicios que el cierre de caja registra aparte de las ventas de librería.
SERVICIOS = ("color", "a3", "scan", "espiral", "impresion")
UBICACIONES = {"ALMACEN": "Almacén", "VITRINA": "Vitrina"}

_CERO = Decimal(0)


@dataclass(frozen=True)
class CierreCaja:
    id: int
    fecha: date
    turno: str
    operador: str
    libreria: Decimal
    color: Decimal | None
    a3: Decimal | None
    scan: Decimal | None
    espiral: Decimal | None
    impresion: Decimal | None
    yape_plin: Decimal | None
    total_manual: Decimal | None
    n_op: str
    creado: datetime | None

    @classmethod
    def desde_fila(cls, fila: Mapping[str, Any]) -> CierreCaja:
        return cls(
            id=int(fila["id"]),
            fecha=leer_fecha(fila["fecha"]),  # type: ignore[arg-type]
            turno=fila.get("turno") or "",
            operador=(fila.get("operador") or "").strip(),
            libreria=a_decimal(fila.get("libreria_total")) or _CERO,
            color=a_decimal(fila.get("color")),
            a3=a_decimal(fila.get("a3")),
            scan=a_decimal(fila.get("scan")),
            espiral=a_decimal(fila.get("espiral")),
            impresion=a_decimal(fila.get("impresion")),
            yape_plin=a_decimal(fila.get("yape_plin")),
            total_manual=a_decimal(fila.get("total_manual")),
            n_op=(fila.get("n_op") or "").strip(),
            creado=leer_fecha_hora(fila.get("created_at")),
        )

    @property
    def servicios(self) -> Decimal:
        return sum((getattr(self, s) or _CERO for s in SERVICIOS), _CERO)

    @property
    def total_registrado(self) -> Decimal:
        """Librería más servicios, tal como los anotó el operador al cerrar."""
        return self.libreria + self.servicios


def turnos_repetidos(cierres: Sequence[CierreCaja]) -> frozenset[tuple[date, str]]:
    """Turnos con más de un cierre: puede ser un cierre repetido o una venta tardía."""
    cuenta = Counter((c.fecha, c.turno) for c in cierres)
    return frozenset(turno for turno, n in cuenta.items() if n > 1)


@dataclass(frozen=True)
class ResumenVentas:
    cierres: int
    dias: int
    libreria: Decimal
    servicios: Decimal
    total_registrado: Decimal
    yape_plin: Decimal
    total_manual: Decimal
    repetidos: frozenset[tuple[date, str]]

    @classmethod
    def de(cls, cierres: Sequence[CierreCaja]) -> ResumenVentas:
        return cls(
            cierres=len(cierres),
            dias=len({c.fecha for c in cierres}),
            libreria=sum((c.libreria for c in cierres), _CERO),
            servicios=sum((c.servicios for c in cierres), _CERO),
            total_registrado=sum((c.total_registrado for c in cierres), _CERO),
            yape_plin=sum((c.yape_plin or _CERO for c in cierres), _CERO),
            total_manual=sum((c.total_manual or _CERO for c in cierres), _CERO),
            repetidos=turnos_repetidos(cierres),
        )


@dataclass(frozen=True)
class ProductoVendido:
    producto_id: int
    nombre: str
    pagina: int | None
    cantidad: int
    importe: Decimal
    cierres: int

    @classmethod
    def desde_fila(cls, fila: Mapping[str, Any]) -> ProductoVendido:
        return cls(
            producto_id=int(fila["producto_id"]),
            nombre=(fila.get("producto") or "").strip(),
            pagina=fila.get("pg"),
            cantidad=int(fila.get("cantidad") or 0),
            importe=a_decimal(fila.get("importe")) or _CERO,
            cierres=int(fila.get("cierres") or 0),
        )


@dataclass(frozen=True)
class StockProducto:
    producto_id: int
    pagina: int | None
    nombre: str
    almacen: int
    vitrina: int
    total: int
    ultimo_movimiento: datetime | None
    almacen_registrado: int | None
    vitrina_registrado: int | None
    revisar: bool

    @classmethod
    def desde_fila(cls, fila: Mapping[str, Any]) -> StockProducto:
        return cls(
            producto_id=int(fila["producto_id"]),
            pagina=fila.get("pg"),
            nombre=(fila.get("producto") or "").strip(),
            almacen=int(fila.get("almacen") or 0),
            vitrina=int(fila.get("vitrina") or 0),
            total=int(fila.get("total") or 0),
            ultimo_movimiento=leer_fecha_hora(fila.get("ultimo_movimiento")),
            almacen_registrado=fila.get("almacen_registrado"),
            vitrina_registrado=fila.get("vitrina_registrado"),
            revisar=bool(fila.get("revisar")),
        )

    @property
    def aviso(self) -> str | None:
        """Motivo para revisar el producto, o None si sus saldos son coherentes."""
        avisos = []
        if self.revisar:
            avisos.append(
                f"El último saldo registrado es almacén {self.almacen_registrado or 0} y "
                f"vitrina {self.vitrina_registrado or 0}, distinto de la suma de sus movimientos"
            )
        if self.almacen < 0 or self.vitrina < 0:
            avisos.append("Tiene stock negativo")
        return ". ".join(avisos) or None


@dataclass(frozen=True)
class Movimiento:
    id: int
    fecha: datetime
    producto_id: int
    producto: str
    pagina: int | None
    ubicacion: str
    concepto: str
    cantidad: int
    saldo: int | None

    @classmethod
    def desde_fila(cls, fila: Mapping[str, Any]) -> Movimiento:
        producto = fila.get("productos") or {}
        return cls(
            id=int(fila["id"]),
            fecha=leer_fecha_hora(fila["fecha"]),  # type: ignore[arg-type]
            producto_id=int(fila["producto_id"]),
            producto=(producto.get("producto") or "").strip(),
            pagina=producto.get("pg"),
            ubicacion=fila.get("ubicacion") or "",
            concepto=fila.get("concepto") or "",
            cantidad=int(fila.get("cantidad_cambio") or 0),
            saldo=fila.get("saldo_resultante"),
        )

    @property
    def ubicacion_texto(self) -> str:
        return UBICACIONES.get(self.ubicacion, self.ubicacion.capitalize())

    @property
    def concepto_texto(self) -> str:
        return self.concepto.capitalize()
