"""Errores de la aplicación y traducción de las excepciones de Supabase a mensajes para el usuario."""

from __future__ import annotations

import logging

import httpx
from postgrest.exceptions import APIError
from supabase_auth.errors import AuthApiError, AuthError, AuthRetryableError
from supabase_functions.errors import FunctionsHttpError, FunctionsRelayError

log = logging.getLogger(__name__)


class ErrorApp(Exception):
    """Error con un mensaje apto para mostrarse en la interfaz."""

    mensaje_por_defecto = "Ocurrió un error inesperado."

    def __init__(self, mensaje: str | None = None) -> None:
        self.mensaje = mensaje or self.mensaje_por_defecto
        super().__init__(self.mensaje)


class ConfiguracionInvalida(ErrorApp):
    mensaje_por_defecto = "La configuración de la aplicación no es válida."


class SinConexion(ErrorApp):
    mensaje_por_defecto = "No hay conexión con el servidor. Revisa tu conexión a internet."


class CredencialesInvalidas(ErrorApp):
    mensaje_por_defecto = "Usuario o contraseña incorrectos."


class DemasiadosIntentos(ErrorApp):
    def __init__(self, segundos: int | None = None) -> None:
        self.segundos = segundos
        if segundos:
            mensaje = f"Demasiados intentos fallidos. Espera {segundos} s antes de volver a intentar."
        else:
            mensaje = "Demasiados intentos. Espera unos minutos antes de volver a intentar."
        super().__init__(mensaje)


class AccesoDenegado(ErrorApp):
    mensaje_por_defecto = "Tu cuenta no tiene acceso al sistema de inventario."


class UsuarioInactivo(ErrorApp):
    mensaje_por_defecto = "Tu cuenta está desactivada. Contacta a un administrador."


class SesionExpirada(ErrorApp):
    mensaje_por_defecto = "Tu sesión expiró. Vuelve a iniciar sesión."


class PermisoDenegado(ErrorApp):
    mensaje_por_defecto = "No tienes permiso para realizar esta acción."


class DatosInvalidos(ErrorApp):
    mensaje_por_defecto = "Los datos ingresados no son válidos."


class ErrorServidor(ErrorApp):
    mensaje_por_defecto = "El servidor no pudo completar la operación. Inténtalo de nuevo."


# Códigos de PostgREST para JWT ausente, inválido o expirado.
_CODIGOS_JWT = {"PGRST301", "PGRST302", "PGRST303"}


def _traducir_auth(exc: AuthError) -> ErrorApp:
    codigo = getattr(exc, "code", None)
    if isinstance(exc, AuthRetryableError):
        return SinConexion()
    if codigo == "invalid_credentials":
        return CredencialesInvalidas()
    if codigo == "user_banned":
        return UsuarioInactivo()
    if codigo == "email_not_confirmed":
        return AccesoDenegado("Tu cuenta aún no está confirmada. Contacta a un administrador.")
    if codigo == "over_request_rate_limit":
        return DemasiadosIntentos()
    if codigo == "same_password":
        return DatosInvalidos("La nueva contraseña debe ser distinta de la actual.")
    if codigo == "weak_password":
        return DatosInvalidos("La contraseña no cumple la política de seguridad.")
    if codigo in {"session_not_found", "refresh_token_not_found", "refresh_token_already_used"}:
        return SesionExpirada()
    if isinstance(exc, AuthApiError) and exc.status == 401:
        return SesionExpirada()
    log.warning("Error de autenticación no mapeado: %s (%s)", exc.message, codigo)
    return ErrorServidor()


def _traducir_postgrest(exc: APIError) -> ErrorApp:
    if exc.code in _CODIGOS_JWT:
        return SesionExpirada()
    if exc.code == "42501":
        # Los triggers de seguridad usan 42501 con un mensaje propio en español.
        mensaje = exc.message if exc.message and "permission denied" not in exc.message else None
        return PermisoDenegado(mensaje)
    if exc.code == "P0001":
        return DatosInvalidos(exc.message)
    log.error("Error de PostgREST: %r", exc)
    return ErrorServidor()


def _traducir_funcion(exc: FunctionsHttpError) -> ErrorApp:
    if exc.status == 401:
        return SesionExpirada()
    if exc.status == 403:
        return PermisoDenegado(exc.message)
    if exc.status in {400, 404, 409, 422}:
        return DatosInvalidos(exc.message)
    log.error("Error en Edge Function (%s): %s", exc.status, exc.message)
    return ErrorServidor()


def traducir_error(exc: BaseException) -> ErrorApp:
    """Convierte cualquier excepción en un ErrorApp con un mensaje comprensible."""
    if isinstance(exc, ErrorApp):
        return exc
    if isinstance(exc, AuthError):
        return _traducir_auth(exc)
    if isinstance(exc, APIError):
        return _traducir_postgrest(exc)
    if isinstance(exc, FunctionsHttpError):
        return _traducir_funcion(exc)
    if isinstance(exc, FunctionsRelayError):
        log.error("Error de relay en Edge Function: %s", exc.message)
        return ErrorServidor()
    if isinstance(exc, (httpx.TransportError, ConnectionError, TimeoutError)):
        return SinConexion()
    log.exception("Error no controlado", exc_info=exc)
    return ErrorApp()
