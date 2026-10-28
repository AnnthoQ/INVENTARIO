"""Registro en archivo rotativo. Nunca se registran contraseñas ni tokens."""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def directorio_logs() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Logs"
    else:
        base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return base / "Inventario" / "logs"


def configurar_logging(nivel: int = logging.INFO) -> Path | None:
    formato = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    raiz = logging.getLogger()
    raiz.setLevel(nivel)

    consola = logging.StreamHandler()
    consola.setFormatter(formato)
    raiz.addHandler(consola)

    # httpx registra cada URL en INFO; basta con sus advertencias.
    logging.getLogger("httpx").setLevel(logging.WARNING)

    directorio = directorio_logs()
    try:
        directorio.mkdir(parents=True, exist_ok=True)
        archivo = RotatingFileHandler(
            directorio / "inventario.log", maxBytes=1_000_000, backupCount=5, encoding="utf-8"
        )
    except OSError as exc:
        raiz.warning("No se pudo crear el archivo de log en %s: %s", directorio, exc)
        return None
    archivo.setFormatter(formato)
    raiz.addHandler(archivo)
    return directorio / "inventario.log"
