"""Punto de entrada de la aplicación de escritorio."""

from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from app import __version__
from app.config import Config, cargar_dotenv
from app.controllers.sesion_controller import ControladorSesion
from app.core.almacen_tokens import AlmacenTokens
from app.core.auth_service import AuthService
from app.core.errores import ConfiguracionInvalida
from app.core.logging_config import configurar_logging
from app.core.supabase_client import crear_cliente
from app.views.estilo import HOJA_ESTILOS

log = logging.getLogger(__name__)


def main() -> int:
    archivo_log = configurar_logging()
    log.info("Inventario %s · log: %s", __version__, archivo_log)

    app = QApplication(sys.argv)
    app.setApplicationName("Inventario")
    app.setApplicationVersion(__version__)
    app.setStyleSheet(HOJA_ESTILOS)

    try:
        cargar_dotenv()
        config = Config.desde_entorno()
    except ConfiguracionInvalida as error:
        log.error("Configuración inválida: %s", error.mensaje)
        QMessageBox.critical(None, "Configuración", error.mensaje)
        return 1

    cliente = crear_cliente(config)
    auth = AuthService(cliente, AlmacenTokens(config.id_proyecto), config.dominio_codigos)
    controlador = ControladorSesion(app, auth, config)
    controlador.iniciar()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
