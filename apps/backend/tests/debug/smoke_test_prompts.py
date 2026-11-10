#!/usr/bin/env python
"""
Smoke test para el sistema de prompts por modelo.
Valida que el sistema funcione end-to-end sin llamar a la API real.

Ejecutar: python apps/api/smoke_test_prompts.py
"""

import sys
import os
import hashlib
from pathlib import Path

# Agregar paths para imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Mock de structlog si no está instalado
try:
    import structlog
except ImportError:
    print("⚠️  structlog no disponible, usando mock")
    import logging
    class MockLogger:
        def __getattr__(self, name):
            def log_method(*args, **kwargs):
                print(f"[{name.upper()}]", args, kwargs)
            return log_method

    class MockStructlog:
        @staticmethod
        def get_logger(name):
            return MockLogger()

    sys.modules['structlog'] = MockStructlog()
    structlog = MockStructlog()

from core.prompt_registry import PromptRegistry, get_prompt_registry
from services.tools import describe_tools_markdown, build_tools_context, DEFAULT_AVAILABLE_TOOLS
from services.saptiva_client import build_messages, build_payload


def print_section(title):
    """Imprimir sección de test"""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def test_registry_load():
    """Test 1: Cargar registry desde YAML"""
    print_section("TEST 1: Cargar Registry YAML")

    registry = PromptRegistry()
    registry_path = os.path.join(
        os.path.dirname(__file__),
        'prompts',
        'registry.yaml'
    )

    print(f"📂 Cargando: {registry_path}")
    registry.load(registry_path)

    print(f"✅ Version: {registry.version}")
    print(f"✅ Copilot: {registry.copilot_name}")
    print(f"✅ Org: {registry.org_name}")
    print(f"✅ Modelos cargados: {list(registry.models.keys())}")

    assert "default" in registry.models, "❌ Modelo 'default' no encontrado"
    assert "Saptiva Turbo" in registry.models, "❌ Modelo 'Saptiva Turbo' no encontrado"

    print("\n✅ Registry cargado correctamente\n")
    return registry


def test_placeholder_substitution(registry):
    """Test 2: Sustitución de placeholders"""
    print_section("TEST 2: Sustitución de Placeholders")

    system_text, params = registry.resolve("default", channel="chat")

    # Verificar que NO hay placeholders sin resolver
    assert "{CopilotOS}" not in system_text, "❌ {CopilotOS} no fue sustituido"
    assert "{Saptiva}" not in system_text, "❌ {Saptiva} no fue sustituido"

    # Verificar que SÍ están los valores reales
    assert registry.copilot_name in system_text, f"❌ {registry.copilot_name} no encontrado"
    assert registry.org_name in system_text, f"❌ {registry.org_name} no encontrado"

    print(f"✅ CopilotOS → {registry.copilot_name}")
    print(f"✅ Saptiva → {registry.org_name}")
    print(f"✅ System prompt length: {len(system_text)} chars")
    print(f"✅ System hash: {params['_metadata']['system_hash']}")

    print("\n✅ Placeholders sustituidos correctamente\n")


def test_tools_injection(registry):
    """Test 3: Inyección de herramientas"""
    print_section("TEST 3: Inyección de Herramientas")

    # Construir tools markdown
    tools_enabled = {"web_search": True, "calculator": True}
    tools_md, tools_schemas = build_tools_context(tools_enabled, DEFAULT_AVAILABLE_TOOLS)

    print(f"✅ Tools markdown generado ({len(tools_md)} chars):")
    print(tools_md)

    print(f"\n✅ Tools schemas: {len(tools_schemas)} herramientas")
    for schema in tools_schemas:
        print(f"  - {schema['function']['name']}")

    # Resolver con tools
    system_text, params = registry.resolve("default", tools_markdown=tools_md, channel="chat")

    assert "{TOOLS}" not in system_text, "❌ {TOOLS} placeholder no fue sustituido"
    assert "web_search" in system_text, "❌ web_search no inyectado"
    assert "calculator" in system_text, "❌ calculator no inyectado"

    print(f"\n✅ Herramientas inyectadas correctamente")


def test_model_specific_params():
    """Test 4: Parámetros específicos por modelo"""
    print_section("TEST 4: Parámetros por Modelo")

    # Forzar reload para tener instancia fresca
    from core import prompt_registry
    prompt_registry._prompt_registry = None

    registry = PromptRegistry()
    registry_path = os.path.join(
        os.path.dirname(__file__),
        'prompts',
        'registry.yaml'
    )
    registry.load(registry_path)

    models_to_test = ["Saptiva Turbo", "Saptiva Cortex", "Saptiva Ops"]

    for model in models_to_test:
        _, params = registry.resolve(model, channel="chat")
        print(f"\n📊 {model}:")
        print(f"  - temperature: {params['temperature']}")
        print(f"  - top_p: {params['top_p']}")
        print(f"  - frequency_penalty: {params['frequency_penalty']}")
        print(f"  - max_tokens: {params['max_tokens']}")
        print(f"  - has_addendum: {params['_metadata']['has_addendum']}")

    # Verificar que son diferentes
    _, params_turbo = registry.resolve("Saptiva Turbo", channel="chat")
    _, params_cortex = registry.resolve("Saptiva Cortex", channel="chat")

    assert params_turbo['temperature'] != params_cortex['temperature'], \
        "❌ Temperaturas deben ser diferentes entre modelos"

    print("\n✅ Parámetros específicos por modelo funcionan correctamente")


def test_channel_max_tokens(registry):
    """Test 5: Max tokens por canal"""
    print_section("TEST 5: Max Tokens por Canal")

    channels = ["chat", "report", "title", "summary", "code"]

    for channel in channels:
        _, params = registry.resolve("default", channel=channel)
        max_tokens = params['max_tokens']
        print(f"  {channel:12} → max_tokens: {max_tokens}")

    # Verificar valores específicos
    _, params_chat = registry.resolve("default", channel="chat")
    _, params_report = registry.resolve("default", channel="report")
    _, params_title = registry.resolve("default", channel="title")

    assert params_chat['max_tokens'] == 1200, "❌ chat debe ser 1200"
    assert params_report['max_tokens'] == 3500, "❌ report debe ser 3500"
    assert params_title['max_tokens'] == 64, "❌ title debe ser 64"

    print("\n✅ Max tokens por canal configurados correctamente")


def test_build_messages():
    """Test 6: Builder de mensajes"""
    print_section("TEST 6: Build Messages (System → User)")

    system_text = "Eres CopilotOS de Saptiva"
    user_prompt = "¿Qué es Python?"
    user_context = {
        "session_id": "test-123",
        "user_id": "user-456"
    }

    messages = build_messages(user_prompt, user_context, system_text)

    print(f"✅ Mensajes generados: {len(messages)}")
    print(f"\n  [0] role: {messages[0]['role']}")
    print(f"      content: {messages[0]['content'][:60]}...")
    print(f"\n  [1] role: {messages[1]['role']}")
    print(f"      content: {messages[1]['content'][:80]}...")

    assert messages[0]['role'] == "system", "❌ Primer mensaje debe ser system"
    assert messages[1]['role'] == "user", "❌ Segundo mensaje debe ser user"
    assert "session_id" in messages[1]['content'], "❌ Contexto no incluido"

    print("\n✅ Mensajes construidos en orden correcto (System → User)")


def test_build_payload():
    """Test 7: Build payload completo"""
    print_section("TEST 7: Build Payload Completo")

    # Mock settings
    class MockSettings:
        enable_model_system_prompt = True
        prompt_registry_path = os.path.join(
            os.path.dirname(__file__),
            'prompts',
            'registry.yaml'
        )

    # Inyectar mock
    from core import config
    original_get_settings = config.get_settings
    config.get_settings = lambda: MockSettings()

    try:
        payload, metadata = build_payload(
            model="Saptiva Turbo",
            user_prompt="Dame 3 bullets sobre Python",
            user_context={"session": "abc"},
            tools_enabled={"web_search": True},
            channel="chat"
        )

        print(f"✅ Payload generado:")
        print(f"  - model: {payload['model']}")
        print(f"  - temperature: {payload['temperature']}")
        print(f"  - max_tokens: {payload['max_tokens']}")
        print(f"  - messages: {len(payload['messages'])}")
        print(f"  - tools: {len(payload.get('tools', []))} herramientas")

        print(f"\n✅ Metadata:")
        print(f"  - request_id: {metadata['request_id']}")
        print(f"  - system_hash: {metadata['system_hash']}")
        print(f"  - prompt_version: {metadata['prompt_version']}")
        print(f"  - model: {metadata['model']}")
        print(f"  - channel: {metadata['channel']}")

        # Validaciones
        assert payload['model'] == "Saptiva Turbo"
        assert payload['temperature'] == 0.25  # Saptiva Turbo específico
        assert payload['max_tokens'] == 1200  # chat channel
        assert len(payload['messages']) == 2
        assert payload['messages'][0]['role'] == 'system'

        print("\n✅ Payload completo generado correctamente")

    finally:
        config.get_settings = original_get_settings


def test_hash_consistency():
    """Test 8: Consistencia de hashes"""
    print_section("TEST 8: Consistencia de Hashes")

    registry = PromptRegistry()
    registry_path = os.path.join(
        os.path.dirname(__file__),
        'prompts',
        'registry.yaml'
    )
    registry.load(registry_path)

    # Generar hash 3 veces
    hashes = []
    for i in range(3):
        _, params = registry.resolve("default", channel="chat")
        hash_val = params['_metadata']['system_hash']
        hashes.append(hash_val)
        print(f"  Run {i+1}: {hash_val}")

    # Verificar que son todos iguales
    assert len(set(hashes)) == 1, "❌ Hashes deben ser idénticos"
    print(f"\n✅ Hash consistente: {hashes[0]}")


def main():
    """Ejecutar todos los smoke tests"""
    print("\n" + "="*70)
    print("  🧪 SMOKE TESTS — Sistema de Prompts por Modelo")
    print("="*70)

    try:
        # Test 1: Cargar registry
        registry = test_registry_load()

        # Test 2: Placeholders
        test_placeholder_substitution(registry)

        # Test 3: Tools
        test_tools_injection(registry)

        # Test 4: Params por modelo
        test_model_specific_params()

        # Test 5: Max tokens por canal
        test_channel_max_tokens(registry)

        # Test 6: Build messages
        test_build_messages()

        # Test 7: Build payload
        test_build_payload()

        # Test 8: Hash consistency
        test_hash_consistency()

        # RESUMEN FINAL
        print("\n" + "="*70)
        print("  ✅ TODOS LOS SMOKE TESTS PASARON")
        print("="*70)
        print("\n📋 Resumen de validaciones:")
        print("  ✅ Registry YAML cargado correctamente")
        print("  ✅ Placeholders sustituidos (CopilotOS, Saptiva, TOOLS)")
        print("  ✅ Herramientas inyectadas correctamente")
        print("  ✅ Parámetros específicos por modelo")
        print("  ✅ Max tokens por canal (chat:1200, report:3500, title:64)")
        print("  ✅ Mensajes en orden correcto (System → User)")
        print("  ✅ Payload completo generado")
        print("  ✅ Hashes consistentes para telemetría")
        print("\n🎉 Sistema listo para deployment\n")

        return 0

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n💥 ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
