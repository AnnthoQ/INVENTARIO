"""Validaciones compartidas por la interfaz y los servicios."""

from __future__ import annotations

import re

from app.core.errores import DatosInvalidos

# Misma política que la Edge Function admin-usuarios (manejador.ts).
LONGITUD_MINIMA_PASSWORD = 8
LONGITUD_MAXIMA_PASSWORD = 72  # límite de bcrypt

_PATRON_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_PATRON_CODIGO = re.compile(r"^[a-z0-9][a-z0-9._-]{1,62}$")


def identificador_a_email(identificador: str, dominio_codigos: str) -> str:
    """Convierte «op01» en «op01@inv.local»; los correos completos se devuelven normalizados."""
    valor = identificador.strip().lower()
    if not valor:
        raise DatosInvalidos("Ingresa tu usuario o correo.")
    if "@" in valor:
        if not _PATRON_EMAIL.match(valor):
            raise DatosInvalidos("El correo no es válido.")
        return valor
    if not _PATRON_CODIGO.match(valor):
        raise DatosInvalidos(
            "El código de usuario solo puede tener letras, números, puntos, guiones y guiones bajos."
        )
    return f"{valor}@{dominio_codigos}"


def validar_password(password: str) -> None:
    if not (LONGITUD_MINIMA_PASSWORD <= len(password) <= LONGITUD_MAXIMA_PASSWORD):
        raise DatosInvalidos(
            f"La contraseña debe tener entre {LONGITUD_MINIMA_PASSWORD} y "
            f"{LONGITUD_MAXIMA_PASSWORD} caracteres."
        )
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise DatosInvalidos("La contraseña debe incluir letras y números.")
