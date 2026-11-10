"""Ámbito del perfil del usuario para las tools de dominio (T3 perfiles)."""

import pytest

from src.services.perfil_usuario import ambito_desde_usuario, tools_con_ambito


@pytest.mark.unit
def test_ambito_desde_usuario_mapea_los_tres_perfiles():
    gerente = {
        "username": "gerente.centro",
        "ambito": {"rol": "gerente_tienda", "tienda_id": "652", "tienda_nombre": "Centro"},
    }
    assert ambito_desde_usuario(gerente) == {
        "rol": "gerente_tienda",
        "tienda_id": "652",
        "tienda_nombre": "Centro",
        "usuario": "gerente.centro",
    }
    jefe = {
        "username": "jefe",
        "ambito": {"rol": "jefe_departamento", "tienda_id": 652, "categorias": ["bebidas"]},
    }
    assert ambito_desde_usuario(jefe)["tienda_id"] == "652"  # normaliza a texto
    assert ambito_desde_usuario(jefe)["categorias"] == ["bebidas"]
    compras = {"username": "compras", "ambito": {"rol": "compras"}}
    assert ambito_desde_usuario(compras) == {"rol": "compras", "usuario": "compras"}


@pytest.mark.unit
def test_sin_perfil_o_rol_desconocido_no_restringe():
    assert ambito_desde_usuario(None) is None
    assert ambito_desde_usuario({"username": "demo"}) is None  # usuarios previos
    assert ambito_desde_usuario({"username": "x", "ambito": {"rol": "admin"}}) is None


@pytest.mark.unit
def test_tools_con_ambito_lee_el_schema_openai():
    schemas = [
        {
            "type": "function",
            "function": {
                "name": "retail_analytics",
                "parameters": {"properties": {"metric_or_query": {}, "ambito": {}}},
            },
        },
        {
            "type": "function",
            "function": {"name": "get_presets", "parameters": {"properties": {}}},
        },
    ]
    assert tools_con_ambito(schemas) == {"retail_analytics"}
    assert tools_con_ambito([]) == set()
