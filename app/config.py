"""Configuración de la aplicación a partir de variables de entorno o un archivo .env."""

from __future__ import annotations

import base64
import binascii
import json
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from app.core.errores import ConfiguracionInvalida

_HOSTS_LOCALES = {"localhost", "127.0.0.1", "::1"}


def _rol_de_jwt(clave: str) -> str | None:
    """Devuelve el claim «role» si la clave es un JWT (claves heredadas anon / service_role)."""
    partes = clave.split(".")
    if len(partes) != 3:
        return None
    carga = partes[1] + "=" * (-len(partes[1]) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(carga)).get("role")
    except (binascii.Error, ValueError, AttributeError):
        return None


def validar_clave_publica(clave: str) -> None:
    """Rechaza claves con privilegios de servidor: un ejecutable distribuido se puede inspeccionar."""
    if clave.startswith("sb_secret_") or _rol_de_jwt(clave) == "service_role":
        raise ConfiguracionInvalida(
            "SUPABASE_KEY es una clave secreta (service_role). Usa la clave publishable o anon."
        )


def _entero(entorno: Mapping[str, str], nombre: str, defecto: int, minimo: int) -> int:
    valor = entorno.get(nombre, "").strip()
    if not valor:
        return defecto
    try:
        numero = int(valor)
    except ValueError:
        raise ConfiguracionInvalida(f"{nombre} debe ser un número entero") from None
    if numero < minimo:
        raise ConfiguracionInvalida(f"{nombre} debe ser al menos {minimo}")
    return numero


def _booleano(entorno: Mapping[str, str], nombre: str, defecto: bool) -> bool:
    valor = entorno.get(nombre, "").strip().lower()
    if not valor:
        return defecto
    return valor in {"1", "true", "si", "sí", "yes"}


def cargar_dotenv() -> None:
    """Carga .env desde el directorio actual o, en el ejecutable empaquetado, junto al .exe."""
    from dotenv import find_dotenv, load_dotenv

    if getattr(sys, "frozen", False):
        load_dotenv(Path(sys.executable).with_name(".env"))
    load_dotenv(find_dotenv(usecwd=True))


@dataclass(frozen=True)
class Config:
    supabase_url: str
    supabase_key: str
    # Los usuarios con código (p. ej. «op01») tienen en Auth el correo «op01@inv.local».
    dominio_codigos: str = "inv.local"
    minutos_inactividad: int = 15
    segundos_verificacion_sesion: int = 120
    permitir_recordar_sesion: bool = True

    @property
    def id_proyecto(self) -> str:
        return urlparse(self.supabase_url).hostname or self.supabase_url

    @classmethod
    def desde_entorno(cls, entorno: Mapping[str, str] | None = None) -> Config:
        entorno = os.environ if entorno is None else entorno

        url = entorno.get("SUPABASE_URL", "").strip().rstrip("/")
        clave = entorno.get("SUPABASE_KEY", "").strip()
        if not url or not clave:
            raise ConfiguracionInvalida(
                "Faltan SUPABASE_URL o SUPABASE_KEY. Copia .env.example como .env y complétalo."
            )

        partes = urlparse(url)
        es_local = partes.hostname in _HOSTS_LOCALES
        if partes.scheme != "https" and not (partes.scheme == "http" and es_local):
            raise ConfiguracionInvalida("SUPABASE_URL debe usar https://")

        validar_clave_publica(clave)

        dominio = entorno.get("INVENTARIO_DOMINIO_CODIGOS", "").strip().lstrip("@") or "inv.local"

        return cls(
            supabase_url=url,
            supabase_key=clave,
            dominio_codigos=dominio,
            minutos_inactividad=_entero(entorno, "INVENTARIO_MINUTOS_INACTIVIDAD", 15, 1),
            segundos_verificacion_sesion=_entero(entorno, "INVENTARIO_SEGUNDOS_VERIFICACION_SESION", 120, 30),
            permitir_recordar_sesion=_booleano(entorno, "INVENTARIO_RECORDAR_SESION", True),
        )
