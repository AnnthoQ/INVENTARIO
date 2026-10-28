"""Ejecución de llamadas de red fuera del hilo de la interfaz.

    ejecutar(auth.iniciar_sesion, usuario, clave, al_terminar=..., al_fallar=...)

Los callbacks siempre se ejecutan en el hilo principal de Qt y reciben el
resultado o el error ya traducido a ErrorApp.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from app.core.errores import ErrorApp, traducir_error


class _Senales(QObject):
    terminado = Signal(object)
    fallido = Signal(object)


class Tarea(QRunnable):
    def __init__(self, funcion: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self._funcion = funcion
        self._args = args
        self._kwargs = kwargs
        # Se crea en el hilo principal: las señales llegan a él por cola de eventos.
        self.senales = _Senales()

    def run(self) -> None:
        try:
            resultado = self._funcion(*self._args, **self._kwargs)
        except Exception as exc:  # noqa: BLE001
            self.senales.fallido.emit(traducir_error(exc))
        else:
            self.senales.terminado.emit(resultado)


# Las tareas en curso se retienen aquí para que Python no destruya sus señales
# antes de que lleguen al hilo principal.
_en_curso: set[Tarea] = set()


def ejecutar(
    funcion: Callable[..., Any],
    *args: Any,
    al_terminar: Callable[[Any], None] | None = None,
    al_fallar: Callable[[ErrorApp], None] | None = None,
    pool: QThreadPool | None = None,
    **kwargs: Any,
) -> Tarea:
    tarea = Tarea(funcion, *args, **kwargs)
    tarea.setAutoDelete(False)
    _en_curso.add(tarea)

    def _liberar(_: object) -> None:
        _en_curso.discard(tarea)

    if al_terminar:
        tarea.senales.terminado.connect(al_terminar)
    if al_fallar:
        tarea.senales.fallido.connect(al_fallar)
    tarea.senales.terminado.connect(_liberar)
    tarea.senales.fallido.connect(_liberar)

    (pool or QThreadPool.globalInstance()).start(tarea)
    return tarea
