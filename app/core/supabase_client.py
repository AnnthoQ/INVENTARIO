"""Creación del cliente de Supabase."""

from __future__ import annotations

from supabase import Client, ClientOptions, create_client

from app.config import Config

_TIMEOUT_SEGUNDOS = 15


def crear_cliente(config: Config) -> Client:
    opciones = ClientOptions(
        auto_refresh_token=True,
        # La sesión vive en memoria; si el usuario pide recordarla, AuthService
        # guarda solo el refresh token en el almacén de credenciales del sistema.
        persist_session=False,
        postgrest_client_timeout=_TIMEOUT_SEGUNDOS,
        function_client_timeout=_TIMEOUT_SEGUNDOS,
    )
    return create_client(config.supabase_url, config.supabase_key, opciones)
