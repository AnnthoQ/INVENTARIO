"""Espera creciente tras inicios de sesión fallidos.

Complementa el límite de Supabase Auth (por IP) con uno por cuenta en este equipo.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable

from app.core.errores import DemasiadosIntentos


class LimitadorIntentos:
    def __init__(
        self,
        intentos_libres: int = 3,
        espera_base: float = 5.0,
        espera_maxima: float = 300.0,
        reloj: Callable[[], float] = time.monotonic,
    ) -> None:
        self._intentos_libres = intentos_libres
        self._espera_base = espera_base
        self._espera_maxima = espera_maxima
        self._reloj = reloj
        self._fallos: dict[str, int] = {}
        self._bloqueado_hasta: dict[str, float] = {}

    def segundos_restantes(self, clave: str) -> int:
        restante = self._bloqueado_hasta.get(clave, 0.0) - self._reloj()
        return math.ceil(restante) if restante > 0 else 0

    def verificar(self, clave: str) -> None:
        restante = self.segundos_restantes(clave)
        if restante:
            raise DemasiadosIntentos(restante)

    def registrar_fallo(self, clave: str) -> None:
        fallos = self._fallos.get(clave, 0) + 1
        self._fallos[clave] = fallos
        exceso = fallos - self._intentos_libres
        if exceso >= 0:
            espera = min(self._espera_base * 2**exceso, self._espera_maxima)
            self._bloqueado_hasta[clave] = self._reloj() + espera

    def registrar_exito(self, clave: str) -> None:
        self._fallos.pop(clave, None)
        self._bloqueado_hasta.pop(clave, None)
