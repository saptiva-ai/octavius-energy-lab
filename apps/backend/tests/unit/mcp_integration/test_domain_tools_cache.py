"""TTL del caché de tools del plugin de dominio (DomainToolProvider).

Regresión 2026-07-21: el caché por proceso NO tenía TTL — un tool nuevo del
plugin (predecir_demanda) no aparecía en la lista ofrecida al LLM hasta
reiniciar el backend, y el modelo FABRICÓ el resultado del tool ausente.
"""
from __future__ import annotations

import pytest

from src.mcp_integration.clients import domain_tools
from src.mcp_integration.clients.domain_tools import (
    DomainToolProvider,
    invalidate_tools_cache,
)
from src.mcp_integration.clients.remote_mcp_client import McpToolSpec, RemoteMcpError

pytestmark = pytest.mark.unit


class _StubClient:
    def __init__(self, specs_por_llamada):
        self._specs = list(specs_por_llamada)
        self.llamadas = 0

    async def list_tools(self):
        self.llamadas += 1
        resultado = self._specs.pop(0)
        if isinstance(resultado, Exception):
            raise resultado
        return resultado


def _spec(name: str) -> McpToolSpec:
    return McpToolSpec(name=name, description=f"tool {name}", input_schema={})


@pytest.fixture(autouse=True)
def _cache_limpio():
    invalidate_tools_cache()
    yield
    invalidate_tools_cache()


async def test_cache_hit_dentro_del_ttl():
    client = _StubClient([[_spec("a")]])
    provider = DomainToolProvider(client=client)
    assert [s.name for s in await provider.discover()] == ["a"]
    assert [s.name for s in await provider.discover()] == ["a"]
    assert client.llamadas == 1  # segunda llamada sale del caché


async def test_ttl_vencido_redescubre_y_refresca_markdown(monkeypatch):
    client = _StubClient([[_spec("a")], [_spec("a"), _spec("predecir_demanda")]])
    provider = DomainToolProvider(client=client)
    md_inicial = await provider.tools_markdown()
    assert "predecir_demanda" not in (md_inicial or "")

    # Vencer el TTL sin dormir.
    monkeypatch.setattr(domain_tools, "_TOOLS_CACHE_TTL_SEGUNDOS", 0.0)
    schemas = await provider.tool_schemas()
    assert client.llamadas == 2
    assert any(
        s["function"]["name"] == "predecir_demanda" for s in schemas
    )
    # El markdown derivado se regenera con los specs nuevos (prompt y schemas
    # nunca desincronizados). TTL de vuelta a vigente: el markdown sale del
    # caché recién refrescado, sin un tercer list_tools.
    monkeypatch.setattr(domain_tools, "_TOOLS_CACHE_TTL_SEGUNDOS", 300.0)
    assert "predecir_demanda" in (await provider.tools_markdown() or "")
    assert client.llamadas == 2


async def test_falla_transitoria_conserva_cache_viejo(monkeypatch):
    client = _StubClient([[_spec("a")], RemoteMcpError("plugin caído")])
    provider = DomainToolProvider(client=client)
    await provider.discover()
    monkeypatch.setattr(domain_tools, "_TOOLS_CACHE_TTL_SEGUNDOS", 0.0)
    # TTL vencido + plugin caído → mejor tools stale que sin tools.
    assert [s.name for s in await provider.discover()] == ["a"]
    assert client.llamadas == 2


async def test_falla_sin_cache_previo_devuelve_vacio():
    client = _StubClient([RemoteMcpError("plugin caído")])
    provider = DomainToolProvider(client=client)
    assert await provider.discover() == []


async def test_invalidate_fuerza_redescubrimiento():
    client = _StubClient([[_spec("a")], [_spec("b")]])
    provider = DomainToolProvider(client=client)
    await provider.discover()
    invalidate_tools_cache()
    assert [s.name for s in await provider.discover()] == ["b"]
    assert client.llamadas == 2
