"""Campos extra en el cuerpo de cada petición al proveedor (`SAPTIVA_EXTRA_BODY`).

Para fijar el proveedor de un modelo en las evaluaciones: OpenRouter repartía
gemma-4-26b entre varios proveedores con cuantizaciones distintas y, con
temperatura 0, el decide mandaba argumentos distintos según quién contestara
(sellada del examen v2, 2026-10-12). Vacío por defecto: producción no cambia.
"""

import pytest

from src.services import saptiva_client
from src.services.saptiva_client import _con_extra_body

pytestmark = pytest.mark.unit

_FIJO = '{"provider": {"order": ["Novita"], "allow_fallbacks": false}}'


def test_sin_variable_el_cuerpo_no_cambia(monkeypatch):
    monkeypatch.delenv("SAPTIVA_EXTRA_BODY", raising=False)
    datos = {"model": "m", "messages": []}
    assert _con_extra_body(datos) == datos


def test_la_variable_agrega_sus_campos(monkeypatch):
    monkeypatch.setenv("SAPTIVA_EXTRA_BODY", _FIJO)
    salida = _con_extra_body({"model": "m", "messages": []})
    assert salida["provider"] == {"order": ["Novita"], "allow_fallbacks": False}
    assert salida["model"] == "m"


def test_los_campos_de_la_peticion_ganan(monkeypatch):
    monkeypatch.setenv("SAPTIVA_EXTRA_BODY", '{"model": "otro", "provider": {}}')
    assert _con_extra_body({"model": "m"})["model"] == "m"


@pytest.mark.parametrize("crudo", ["no es json", "[1, 2]", "  "])
def test_valor_invalido_se_ignora(monkeypatch, crudo):
    monkeypatch.setenv("SAPTIVA_EXTRA_BODY", crudo)
    assert _con_extra_body({"model": "m"}) == {"model": "m"}


def test_sin_cuerpo_sigue_sin_cuerpo(monkeypatch):
    monkeypatch.setenv("SAPTIVA_EXTRA_BODY", _FIJO)
    assert _con_extra_body(None) is None


async def test_make_request_manda_el_cuerpo_con_los_campos_extra(monkeypatch):
    monkeypatch.setenv("SAPTIVA_EXTRA_BODY", _FIJO)
    enviados = []

    class _Respuesta:
        status_code = 200
        headers: dict = {}

        def raise_for_status(self):
            return None

    class _Cliente:
        async def request(self, method, url, json=None):
            enviados.append(json)
            return _Respuesta()

    cliente = saptiva_client.SaptivaClient.__new__(saptiva_client.SaptivaClient)
    cliente.base_url = "http://proveedor"
    cliente.max_retries = 0
    cliente.allow_mock_fallback = False
    cliente.force_mock = False
    cliente.client = _Cliente()
    await cliente._make_request("POST", "/v1/chat/completions", {"model": "m"})
    assert enviados[0]["provider"]["order"] == ["Novita"]
