"""
Tests unitarios para el sistema de prompt registry.
Valida carga de YAML, sustitución de placeholders y parámetros por modelo.
"""

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from src.core.prompt_registry import (
    ModelParams,
    PromptEntry,
    PromptRegistry,
)


class TestModelParams:
    """Tests para ModelParams"""

    def test_default_values(self):
        """Validar valores por defecto"""
        params = ModelParams()
        assert params.temperature == 0.3
        assert params.top_p == 0.9
        assert params.presence_penalty == 0.0
        assert params.frequency_penalty == 0.2
        assert params.max_tokens is None

    def test_custom_values(self):
        """Validar asignación de valores personalizados"""
        params = ModelParams(
            temperature=0.5,
            top_p=0.95,
            frequency_penalty=0.3,
            max_tokens=2000
        )
        assert params.temperature == 0.5
        assert params.top_p == 0.95
        assert params.frequency_penalty == 0.3
        assert params.max_tokens == 2000

    def test_validation_temperature(self):
        """Validar que temperature esté en rango [0, 2]"""
        with pytest.raises(Exception):  # Pydantic validation error
            ModelParams(temperature=3.0)

        with pytest.raises(Exception):
            ModelParams(temperature=-0.1)

    def test_validation_top_p(self):
        """Validar que top_p esté en rango [0, 1]"""
        with pytest.raises(Exception):
            ModelParams(top_p=1.5)


class TestPromptEntry:
    """Tests para PromptEntry"""

    def test_basic_entry(self):
        """Validar creación básica de entry"""
        entry = PromptEntry(
            system_base="Eres {CopilotOS} de {Saptiva}",
            params=ModelParams()
        )
        assert "{CopilotOS}" in entry.system_base
        assert "{Saptiva}" in entry.system_base
        assert entry.addendum is None

    def test_entry_with_addendum(self):
        """Validar entry con addendum"""
        entry = PromptEntry(
            system_base="Base prompt",
            addendum="Optimiza para velocidad",
            params=ModelParams(temperature=0.2)
        )
        assert entry.addendum == "Optimiza para velocidad"
        assert entry.params.temperature == 0.2


class TestPromptRegistry:
    """Tests para PromptRegistry"""

    @pytest.fixture
    def sample_yaml(self):
        """Crear YAML de prueba temporal"""
        yaml_content = {
            "version": "v1",
            "copilot_name": "TestCopilot",
            "org_name": "TestOrg",
            "models": {
                "default": {
                    "system_base": "Eres {CopilotOS} de {Saptiva}. {TOOLS}",
                    "params": {
                        "temperature": 0.3,
                        "top_p": 0.9,
                        "frequency_penalty": 0.2
                    }
                },
                "Test Model": {
                    "system_base": "Test prompt for {CopilotOS}",
                    "addendum": "Optimiza para tests",
                    "params": {
                        "temperature": 0.1,
                        "max_tokens": 500
                    }
                }
            }
        }

        # Crear archivo temporal
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(yaml_content, f)
            temp_path = f.name

        yield temp_path

        # Cleanup
        os.unlink(temp_path)

    def test_load_registry(self, sample_yaml):
        """Test carga de registry desde YAML"""
        registry = PromptRegistry()
        registry.load(sample_yaml)

        assert registry.version == "v1"
        assert registry.copilot_name == "TestCopilot"
        assert registry.org_name == "TestOrg"
        assert "default" in registry.models
        assert "Test Model" in registry.models

    def test_load_nonexistent_file(self):
        """Test error al cargar archivo inexistente"""
        registry = PromptRegistry()
        with pytest.raises(FileNotFoundError):
            registry.load("/nonexistent/path.yaml")

    def test_resolve_default_model(self, sample_yaml):
        """Test resolución de modelo default"""
        registry = PromptRegistry()
        registry.load(sample_yaml)

        system_text, params = registry.resolve("default", channel="chat")

        # Verificar sustitución de placeholders
        assert "TestCopilot" in system_text
        assert "TestOrg" in system_text
        assert "{CopilotOS}" not in system_text
        assert "{Saptiva}" not in system_text

        # Verificar parámetros
        assert params["temperature"] == 0.3
        assert params["top_p"] == 0.9
        assert "max_tokens" in params

        # Verificar metadata
        assert "_metadata" in params
        assert params["_metadata"]["model"] == "default"
        assert params["_metadata"]["channel"] == "chat"
        assert "system_hash" in params["_metadata"]

    def test_resolve_with_tools(self, sample_yaml):
        """Test resolución con herramientas"""
        registry = PromptRegistry()
        registry.load(sample_yaml)

        tools_md = "* **search** — Search the web"
        system_text, params = registry.resolve(
            "default",
            tools_markdown=tools_md,
            channel="chat"
        )

        # Verificar que tools fue inyectado
        assert "search" in system_text
        assert "Search the web" in system_text
        assert "{TOOLS}" not in system_text

    def test_resolve_without_tools(self, sample_yaml):
        """Test resolución sin herramientas"""
        registry = PromptRegistry()
        registry.load(sample_yaml)

        system_text, params = registry.resolve("default", channel="chat")

        # Verificar que {TOOLS} fue removido/reemplazado
        assert "{TOOLS}" not in system_text

    def test_resolve_with_addendum(self, sample_yaml):
        """Test resolución con addendum"""
        registry = PromptRegistry()
        registry.load(sample_yaml)

        system_text, params = registry.resolve("Test Model", channel="chat")

        # Verificar que addendum fue agregado
        assert "Optimiza para tests" in system_text
        assert params["_metadata"]["has_addendum"] is True

    def test_resolve_nonexistent_model_fallback(self, sample_yaml):
        """Test fallback a default si modelo no existe"""
        registry = PromptRegistry()
        registry.load(sample_yaml)

        system_text, params = registry.resolve("NonExistent Model", channel="chat")

        # Debería usar default
        assert "TestCopilot" in system_text
        assert params["temperature"] == 0.3

    def test_channel_max_tokens(self, sample_yaml, monkeypatch):
        """Test que max_tokens varía por canal"""
        # El canal chat lee CHAT_CHANNEL_MAX_TOKENS; limpiar para no depender
        # de envs/.env del entorno donde corra la suite.
        monkeypatch.delenv("CHAT_CHANNEL_MAX_TOKENS", raising=False)
        registry = PromptRegistry()
        registry.load(sample_yaml)

        _, params_chat = registry.resolve("default", channel="chat")
        _, params_report = registry.resolve("default", channel="report")
        _, params_title = registry.resolve("default", channel="title")

        # Verificar límites por canal
        assert params_chat["max_tokens"] == 1200  # chat
        assert params_report["max_tokens"] == 3500  # report
        assert params_title["max_tokens"] == 64  # title

    def test_hash_system_prompt(self, sample_yaml):
        """Test hash de system prompt"""
        registry = PromptRegistry()
        registry.load(sample_yaml)

        system_text, params = registry.resolve("default", channel="chat")

        # Verificar hash
        hash_value = params["_metadata"]["system_hash"]
        assert isinstance(hash_value, str)
        assert len(hash_value) == 16  # Primeros 16 chars de SHA256

        # Hash debe ser determinístico
        system_text2, params2 = registry.resolve("default", channel="chat")
        assert params2["_metadata"]["system_hash"] == hash_value

    def test_get_available_models(self, sample_yaml):
        """Test obtener modelos disponibles"""
        registry = PromptRegistry()
        registry.load(sample_yaml)

        models = registry.get_available_models()

        assert "default" in models
        assert "Test Model" in models
        assert len(models) == 2

    def test_validate_registry(self, sample_yaml):
        """Test validación de registry"""
        registry = PromptRegistry()
        registry.load(sample_yaml)

        # Debe pasar validación
        assert registry.validate() is True

    def test_validate_missing_default(self):
        """Test validación falla si falta modelo default"""
        yaml_content = {
            "version": "v1",
            "copilot_name": "Test",
            "org_name": "Test",
            "models": {
                "SomeModel": {
                    "system_base": "Prompt",
                    "params": {}
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(yaml_content, f)
            temp_path = f.name

        try:
            registry = PromptRegistry()
            registry.load(temp_path)

            with pytest.raises(ValueError, match="default"):
                registry.validate()
        finally:
            os.unlink(temp_path)


class TestIntegration:
    """Tests de integración"""

    def test_full_workflow(self, tmp_path):
        """Test workflow completo: load → resolve → validate"""
        # Crear registry YAML
        yaml_file = tmp_path / "test_registry.yaml"
        yaml_content = {
            "version": "v1.0",
            "copilot_name": "IntegrationBot",
            "org_name": "IntegrationCorp",
            "models": {
                "default": {
                    "system_base": "You are {CopilotOS} from {Saptiva}. Tools: {TOOLS}",
                    "params": {"temperature": 0.5}
                },
                "FastModel": {
                    "system_base": "Fast {CopilotOS}. Available tools: {TOOLS}",
                    "addendum": "Be concise",
                    "params": {"temperature": 0.1, "frequency_penalty": 0.5}
                }
            }
        }

        with open(yaml_file, 'w') as f:
            yaml.dump(yaml_content, f)

        # Load
        registry = PromptRegistry(str(yaml_file))

        # Validate
        assert registry.validate()

        # Resolve default
        system1, params1 = registry.resolve("default", channel="chat")
        assert "IntegrationBot" in system1
        assert params1["temperature"] == 0.5

        # Resolve FastModel con tools
        tools = "* **calc** — Calculate"
        system2, params2 = registry.resolve("FastModel", tools_markdown=tools, channel="report")
        assert "Fast IntegrationBot" in system2
        assert "Be concise" in system2
        assert "calc" in system2
        assert params2["temperature"] == 0.1
        assert params2["max_tokens"] == 3500  # report channel
