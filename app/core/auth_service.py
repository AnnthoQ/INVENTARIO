"""Inicio y cierre de sesión, restauración de sesión y verificación de acceso por rol.

Los métodos hacen llamadas de red: la interfaz los ejecuta fuera del hilo
principal (app/core/tareas.py).
"""

from __future__ import annotations

import logging
import threading

from supabase import Client

from app.core.almacen_tokens import AlmacenTokens
from app.core.errores import (
    AccesoDenegado,
    CredencialesInvalidas,
    ErrorApp,
    SesionExpirada,
    SinConexion,
    UsuarioInactivo,
    traducir_error,
)
from app.core.limitador_intentos import LimitadorIntentos
from app.core.validaciones import identificador_a_email, validar_password
from app.models.perfil import COLUMNAS_PERFIL, Perfil, SesionUsuario

log = logging.getLogger(__name__)


class AuthService:
    def __init__(
        self,
        cliente: Client,
        almacen: AlmacenTokens,
        dominio_codigos: str,
        limitador: LimitadorIntentos | None = None,
    ) -> None:
        self._cliente = cliente
        self._almacen = almacen
        self._dominio_codigos = dominio_codigos
        self._limitador = limitador or LimitadorIntentos()
        self._sesion: SesionUsuario | None = None
        self._recordar = False
        self._candado = threading.Lock()
        # Supabase rota el refresh token en cada renovación: hay que guardar el nuevo.
        cliente.auth.on_auth_state_change(self._al_cambiar_auth)

    @property
    def sesion(self) -> SesionUsuario | None:
        return self._sesion

    # Inicio de sesión ---------------------------------------------------------

    def iniciar_sesion(self, identificador: str, password: str, recordar: bool = False) -> SesionUsuario:
        email = identificador_a_email(identificador, self._dominio_codigos)
        if not password:
            raise CredencialesInvalidas("Ingresa tu contraseña.")
        self._limitador.verificar(email)
        # Hasta validar el perfil no se guarda ningún token de esta cuenta.
        with self._candado:
            self._recordar = False

        try:
            respuesta = self._cliente.auth.sign_in_with_password({"email": email, "password": password})
        except Exception as exc:  # noqa: BLE001 - se traduce a un ErrorApp
            error = traducir_error(exc)
            if isinstance(error, CredencialesInvalidas):
                self._limitador.registrar_fallo(email)
            raise error from exc

        self._limitador.registrar_exito(email)
        sesion = self._abrir_sesion(respuesta.user.id)

        with self._candado:
            self._recordar = recordar
        if recordar and respuesta.session:
            self._almacen.guardar(respuesta.session.refresh_token)
        else:
            self._almacen.borrar()
        log.info("Sesión iniciada: %s (%s)", sesion.perfil.email, sesion.perfil.rol)
        return sesion

    def restaurar_sesion(self) -> SesionUsuario | None:
        """Retoma la sesión recordada en este equipo, si existe y sigue siendo válida."""
        token = self._almacen.leer()
        if not token:
            return None
        try:
            respuesta = self._cliente.auth.refresh_session(token)
            if respuesta.user is None:
                raise SesionExpirada()
            sesion = self._abrir_sesion(respuesta.user.id)
        except Exception as exc:  # noqa: BLE001
            error = traducir_error(exc)
            # Sin red el token puede seguir sirviendo más tarde; en otro caso se descarta.
            if not isinstance(error, SinConexion):
                self._almacen.borrar()
            log.info("No se pudo restaurar la sesión: %s", error.mensaje)
            return None

        with self._candado:
            self._recordar = True
        sesion_auth = self._cliente.auth.get_session()
        if sesion_auth:
            self._almacen.guardar(sesion_auth.refresh_token)
        log.info("Sesión restaurada: %s", sesion.perfil.email)
        return sesion

    def _abrir_sesion(self, user_id: str) -> SesionUsuario:
        """Carga el perfil y comprueba que el rol tenga acceso; si no, cierra la sesión de Auth."""
        try:
            perfil = self._cargar_perfil(user_id)
            if not perfil.activo:
                raise UsuarioInactivo()
            if not perfil.tiene_acceso:
                raise AccesoDenegado()
        except Exception:
            self._cerrar_sesion_auth()
            raise
        self._sesion = SesionUsuario(perfil)
        return self._sesion

    def _cargar_perfil(self, user_id: str) -> Perfil:
        try:
            respuesta = (
                self._cliente.table("profiles").select(COLUMNAS_PERFIL).eq("id", user_id).limit(1).execute()
            )
        except Exception as exc:  # noqa: BLE001
            raise traducir_error(exc) from exc
        if not respuesta.data:
            raise AccesoDenegado("Tu cuenta no tiene un perfil asignado. Contacta a un administrador.")
        return Perfil.desde_fila(respuesta.data[0])

    # Sesión activa ------------------------------------------------------------

    def verificar_password(self, password: str) -> bool:
        """Confirma la contraseña del usuario actual (desbloqueo por inactividad)."""
        sesion = self._exigir_sesion()
        email = sesion.perfil.email
        self._limitador.verificar(email)
        try:
            self._cliente.auth.sign_in_with_password({"email": email, "password": password})
        except Exception as exc:  # noqa: BLE001
            error = traducir_error(exc)
            if isinstance(error, CredencialesInvalidas):
                self._limitador.registrar_fallo(email)
                return False
            raise error from exc
        self._limitador.registrar_exito(email)
        return True

    def cambiar_password(self, actual: str, nueva: str) -> None:
        validar_password(nueva)
        if not self.verificar_password(actual):
            raise CredencialesInvalidas("La contraseña actual no es correcta.")
        try:
            self._cliente.auth.update_user({"password": nueva})
        except Exception as exc:  # noqa: BLE001
            raise traducir_error(exc) from exc
        log.info("Contraseña cambiada: %s", self._exigir_sesion().perfil.email)

    def verificar_sesion_vigente(self) -> bool:
        """Comprueba en el servidor que la cuenta siga activa y con un rol con acceso.

        Devuelve False si el administrador la desactivó o la sesión expiró.
        Lanza SinConexion si no se pudo comprobar.
        """
        sesion = self._exigir_sesion()
        try:
            perfil = self._cargar_perfil(sesion.perfil.id)
        except SinConexion:
            raise
        except ErrorApp:
            return False
        if not perfil.tiene_acceso:
            return False
        if perfil != sesion.perfil:
            self._sesion = SesionUsuario(perfil, sesion.inicio)
        return True

    def cerrar_sesion(self) -> None:
        email = self._sesion.perfil.email if self._sesion else None
        self._cerrar_sesion_auth()
        self._almacen.borrar()
        with self._candado:
            self._recordar = False
        if email:
            log.info("Sesión cerrada: %s", email)

    # Internos -----------------------------------------------------------------

    def _exigir_sesion(self) -> SesionUsuario:
        if self._sesion is None:
            raise SesionExpirada()
        return self._sesion

    def _cerrar_sesion_auth(self) -> None:
        self._sesion = None
        try:
            # «local»: cierra solo este equipo, no las sesiones del usuario en otros.
            self._cliente.auth.sign_out({"scope": "local"})
        except Exception as exc:  # noqa: BLE001 - sin red igual se limpia la sesión local
            log.warning("No se pudo cerrar la sesión en el servidor: %s", exc)

    def _al_cambiar_auth(self, evento: str, sesion_auth: object | None) -> None:
        with self._candado:
            recordar = self._recordar
        # SIGNED_IN también llega al desbloquear la pantalla, que abre una sesión nueva.
        if evento in {"SIGNED_IN", "TOKEN_REFRESHED"} and recordar and sesion_auth is not None:
            self._almacen.guardar(sesion_auth.refresh_token)  # type: ignore[attr-defined]
