from __future__ import annotations

import base64
import json

import pytest

from app.config import Config
from app.core.errores import ConfiguracionInvalida

URL = "https://proyecto.supabase.co"


def jwt_con_rol(rol: str) -> str:
    def b64(datos: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(datos).encode()).decode().rstrip("=")

    return f"{b64({'alg': 'HS256'})}.{b64({'role': rol, 'iss': 'supabase'})}.firma"


def test_configuracion_minima_con_valores_por_defecto() -> None:
    config = Config.desde_entorno({"SUPABASE_URL": URL + "/", "SUPABASE_KEY": "sb_publishable_abc"})

    assert config.supabase_url == URL
    assert config.dominio_codigos == "inv.local"
    assert config.minutos_inactividad == 15
    assert config.permitir_recordar_sesion is True
    assert config.id_proyecto == "proyecto.supabase.co"


@pytest.mark.parametrize("entorno", [{}, {"SUPABASE_URL": URL}, {"SUPABASE_KEY": "sb_publishable_abc"}])
def test_faltan_variables(entorno: dict) -> None:
    with pytest.raises(ConfiguracionInvalida, match=".env.example"):
        Config.desde_entorno(entorno)


@pytest.mark.parametrize("clave", ["sb_secret_abc", jwt_con_rol("service_role")])
def test_rechaza_claves_secretas(clave: str) -> None:
    with pytest.raises(ConfiguracionInvalida, match="service_role"):
        Config.desde_entorno({"SUPABASE_URL": URL, "SUPABASE_KEY": clave})


def test_acepta_la_clave_anon_heredada() -> None:
    config = Config.desde_entorno({"SUPABASE_URL": URL, "SUPABASE_KEY": jwt_con_rol("anon")})
    assert config.supabase_key.count(".") == 2


def test_exige_https_salvo_en_local() -> None:
    with pytest.raises(ConfiguracionInvalida, match="https"):
        Config.desde_entorno({"SUPABASE_URL": "http://proyecto.supabase.co", "SUPABASE_KEY": "k"})
    assert Config.desde_entorno({"SUPABASE_URL": "http://127.0.0.1:54321", "SUPABASE_KEY": "k"})


def test_opciones_personalizadas() -> None:
    config = Config.desde_entorno(
        {
            "SUPABASE_URL": URL,
            "SUPABASE_KEY": "k",
            "INVENTARIO_DOMINIO_CODIGOS": "@tienda.local",
            "INVENTARIO_MINUTOS_INACTIVIDAD": "5",
            "INVENTARIO_RECORDAR_SESION": "false",
        }
    )
    assert config.dominio_codigos == "tienda.local"
    assert config.minutos_inactividad == 5
    assert config.permitir_recordar_sesion is False


@pytest.mark.parametrize(
    ("variable", "valor"),
    [("INVENTARIO_MINUTOS_INACTIVIDAD", "cinco"), ("INVENTARIO_SEGUNDOS_VERIFICACION_SESION", "10")],
)
def test_numeros_invalidos(variable: str, valor: str) -> None:
    with pytest.raises(ConfiguracionInvalida, match=variable):
        Config.desde_entorno({"SUPABASE_URL": URL, "SUPABASE_KEY": "k", variable: valor})
