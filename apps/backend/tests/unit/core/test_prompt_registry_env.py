"""
Contrato de `CHAT_CHANNEL_MAX_TOKENS` en PromptRegistry.

El límite del canal `chat` es configurable por entorno (los modelos de
razonamiento necesitan más presupuesto de respuesta); estos tests fijan que
la variable se respeta, que un valor inválido cae al default sin lanzar y
que los demás canales no se ven afectados.
"""

import pytest

from src.core.prompt_registry import ModelParams, PromptEntry, PromptRegistry


@pytest.fixture
def registry():
    """Registry mínimo en memoria, sin YAML ni max_tokens por modelo."""
    reg = PromptRegistry()
    reg.models["default"] = PromptEntry(
        system_base="Eres {CopilotOS} de {Saptiva}.",
        params=ModelParams(),
    )
    return reg


@pytest.mark.unit
class TestChatChannelMaxTokensEnv:
    def test_default_sin_variable(self, registry, monkeypatch):
        monkeypatch.delenv("CHAT_CHANNEL_MAX_TOKENS", raising=False)

        _, params = registry.resolve("default", channel="chat")

        assert params["max_tokens"] == 1200

    def test_respeta_variable_de_entorno(self, registry, monkeypatch):
        monkeypatch.setenv("CHAT_CHANNEL_MAX_TOKENS", "4000")

        _, params = registry.resolve("default", channel="chat")

        assert params["max_tokens"] == 4000

    def test_valor_invalido_cae_al_default(self, registry, monkeypatch):
        monkeypatch.setenv("CHAT_CHANNEL_MAX_TOKENS", "cuatro-mil")

        _, params = registry.resolve("default", channel="chat")

        assert params["max_tokens"] == 1200

    def test_otros_canales_no_cambian(self, registry, monkeypatch):
        monkeypatch.setenv("CHAT_CHANNEL_MAX_TOKENS", "4000")

        _, params = registry.resolve("default", channel="report")

        assert params["max_tokens"] == 3500
