"""Detecta inactividad del usuario en toda la aplicación."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QTimer, Signal

_EVENTOS_DE_ACTIVIDAD = {
    QEvent.Type.MouseButtonPress,
    QEvent.Type.MouseMove,
    QEvent.Type.KeyPress,
    QEvent.Type.Wheel,
    QEvent.Type.TouchBegin,
}


class MonitorInactividad(QObject):
    inactivo = Signal()

    def __init__(self, minutos: float, padre: QObject | None = None) -> None:
        super().__init__(padre)
        self._temporizador = QTimer(self)
        self._temporizador.setSingleShot(True)
        self._temporizador.setInterval(int(minutos * 60_000))
        self._temporizador.timeout.connect(self.inactivo)

    def iniciar(self) -> None:
        self._temporizador.start()

    def detener(self) -> None:
        self._temporizador.stop()

    @property
    def activo(self) -> bool:
        return self._temporizador.isActive()

    def eventFilter(self, objeto: QObject, evento: QEvent) -> bool:
        # Solo se reinicia si está contando: mientras la pantalla de bloqueo
        # está abierta el monitor permanece detenido.
        if evento.type() in _EVENTOS_DE_ACTIVIDAD and self._temporizador.isActive():
            self._temporizador.start()
        return False
