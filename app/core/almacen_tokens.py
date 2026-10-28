"""Guarda el refresh token en el almacén de credenciales del sistema operativo.

Windows: Administrador de credenciales · macOS: Llavero · Linux: Secret Service.
Si no hay almacén disponible, la opción «recordar sesión» simplemente no persiste.
"""

from __future__ import annotations

import logging

import keyring
from keyring.errors import KeyringError, PasswordDeleteError

log = logging.getLogger(__name__)

_CUENTA = "refresh_token"


class AlmacenTokens:
    def __init__(self, id_proyecto: str, backend: keyring.backend.KeyringBackend | None = None) -> None:
        # Un servicio por proyecto evita mezclar sesiones de entornos distintos.
        self._servicio = f"inventario:{id_proyecto}"
        self._keyring = backend or keyring.get_keyring()

    def guardar(self, token: str) -> bool:
        try:
            self._keyring.set_password(self._servicio, _CUENTA, token)
            return True
        except KeyringError as exc:
            log.warning("No se pudo guardar la sesión en el almacén de credenciales: %s", exc)
            return False

    def leer(self) -> str | None:
        try:
            return self._keyring.get_password(self._servicio, _CUENTA)
        except KeyringError as exc:
            log.warning("No se pudo leer el almacén de credenciales: %s", exc)
            return None

    def borrar(self) -> None:
        try:
            self._keyring.delete_password(self._servicio, _CUENTA)
        except PasswordDeleteError:
            pass
        except KeyringError as exc:
            log.warning("No se pudo borrar la sesión del almacén de credenciales: %s", exc)
