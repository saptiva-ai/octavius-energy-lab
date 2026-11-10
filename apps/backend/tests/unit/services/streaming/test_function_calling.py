"""
Unit tests for FunctionCallingOrchestrator.

Tests cover:
- Fail-safe fallback (no schemas, no tool_calls, exceptions)
- Augmented messages shape (assistant tool_calls + tool result messages)
- Captura del último resultado crudo (AnalyticsResponse) para adjuntar a metadata
- Segundo round acotado: solo cuando el round 1 no trae datos (meta-only/error),
  y con fail-safe que conserva los rounds completos si el round 2 explota
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.streaming.function_calling import (
    FunctionCallingOrchestrator,
    narracion_directa_del_plugin,
)


def _decide_response(tool_calls):
    """Build a minimal OpenAI-shaped chat_completion response with tool_calls."""
    message = {"tool_calls": tool_calls} if tool_calls else {}
    return MagicMock(choices=[{"message": message}])


@pytest.mark.unit
@pytest.mark.asyncio
class TestFunctionCallingOrchestrator:
    async def test_no_schemas_returns_messages_unchanged(self):
        provider = MagicMock()
        provider.tool_schemas = AsyncMock(return_value=[])
        orchestrator = FunctionCallingOrchestrator(provider=provider)

        messages = [{"role": "user", "content": "hola"}]
        result_messages, tool_result, status = await orchestrator.augment(
            MagicMock(), messages, model="turbo"
        )

        assert result_messages is messages
        assert tool_result is None
        # discovery vacío con la tool activada = plugin caído, no "sin tools"
        assert status == "failed"

    async def test_no_tool_calls_returns_messages_unchanged(self):
        provider = MagicMock()
        provider.tool_schemas = AsyncMock(return_value=[{"type": "function"}])
        saptiva_client = MagicMock()
        saptiva_client.chat_completion = AsyncMock(
            return_value=_decide_response(tool_calls=None)
        )
        orchestrator = FunctionCallingOrchestrator(provider=provider)

        messages = [{"role": "user", "content": "hola"}]
        result_messages, tool_result, status = await orchestrator.augment(
            saptiva_client, messages, model="turbo"
        )

        assert result_messages is messages
        assert tool_result is None
        assert status == "no_calls"

    async def test_no_calls_en_primer_intento_reintenta_una_vez(self):
        analytics = {"metric_name": "venta_hora", "series": []}
        provider = MagicMock()
        provider.tool_schemas = AsyncMock(return_value=[{"type": "function"}])
        provider.call = AsyncMock(return_value=analytics)
        tool_calls = [
            {
                "id": "call-2",
                "function": {
                    "name": "retail_analytics",
                    "arguments": '{"metric_or_query": "venta"}',
                },
            }
        ]
        saptiva_client = MagicMock()
        saptiva_client.chat_completion = AsyncMock(
            side_effect=[
                _decide_response(tool_calls=None),
                _decide_response(tool_calls=tool_calls),
            ]
        )

        result_messages, tool_result, status = await FunctionCallingOrchestrator(
            provider=provider
        ).augment(
            saptiva_client,
            [{"role": "user", "content": "dame la venta"}],
            model="turbo",
        )

        assert status == "ok"
        assert tool_result == analytics
        assert len(result_messages) == 3
        assert saptiva_client.chat_completion.await_count == 2
        retry = saptiva_client.chat_completion.await_args_list[1]
        assert (
            "omitiste las llamadas" in retry.kwargs["messages"][-1]["content"].lower()
        )

    async def test_tool_call_executed_augments_messages_and_captures_result(self):
        analytics = {
            "metric_name": "disponibilidad",
            "chart_type": "bar",
            "series": [{"name": "Mundo E", "points": []}],
        }
        provider = MagicMock()
        provider.tool_schemas = AsyncMock(return_value=[{"type": "function"}])
        provider.call = AsyncMock(return_value=analytics)

        tool_calls = [
            {
                "id": "call-1",
                "function": {
                    "name": "retail_analytics",
                    "arguments": '{"metric_or_query": "disponibilidad"}',
                },
            }
        ]
        saptiva_client = MagicMock()
        saptiva_client.chat_completion = AsyncMock(
            return_value=_decide_response(tool_calls=tool_calls)
        )
        orchestrator = FunctionCallingOrchestrator(provider=provider)

        messages = [{"role": "user", "content": "disponibilidad hoy"}]
        result_messages, tool_result, status = await orchestrator.augment(
            saptiva_client, messages, model="turbo"
        )

        assert tool_result == analytics
        assert status == "ok"
        assert len(result_messages) == 3  # original + assistant(tool_calls) + tool
        assert result_messages[1]["role"] == "assistant"
        assert (
            result_messages[1]["tool_calls"][0]["function"]["name"]
            == "retail_analytics"
        )
        assert result_messages[2]["role"] == "tool"
        assert result_messages[2]["tool_call_id"] == "call-1"

    async def test_tool_error_result_not_captured_as_analytics(self):
        """Un resultado con 'error' no debe promoverse a metadata (no hay dato real)."""
        provider = MagicMock()
        provider.tool_schemas = AsyncMock(return_value=[{"type": "function"}])
        provider.call = AsyncMock(return_value={"error": "sin datos cargados"})

        tool_calls = [
            {
                "id": "call-1",
                "function": {"name": "retail_analytics", "arguments": "{}"},
            }
        ]
        saptiva_client = MagicMock()
        saptiva_client.chat_completion = AsyncMock(
            return_value=_decide_response(tool_calls=tool_calls)
        )
        orchestrator = FunctionCallingOrchestrator(provider=provider)

        _, tool_result, status = await orchestrator.augment(
            saptiva_client, [{"role": "user", "content": "x"}], model="turbo"
        )

        assert tool_result is None
        assert status == "ok"  # la tool corrió; su error es grounding real

    async def test_exception_is_fail_safe(self):
        provider = MagicMock()
        provider.tool_schemas = AsyncMock(side_effect=RuntimeError("boom"))
        orchestrator = FunctionCallingOrchestrator(provider=provider)

        messages = [{"role": "user", "content": "hola"}]
        result_messages, tool_result, status = await orchestrator.augment(
            MagicMock(), messages, model="turbo"
        )

        assert result_messages == messages
        assert tool_result is None
        assert status == "failed"

    async def test_meta_only_round_triggers_second_hop_to_data(self):
        """Round 1 solo trae catálogo (get_presets) → round 2 ejecuta la tool de datos."""
        presets = {"presets": [{"id": "comparar_control"}]}  # sin metric_name/series
        analytics = {
            "metric_name": "venta_hora",
            "chart_type": "bar",
            "series": [{"name": "comparación", "points": []}],
        }
        provider = MagicMock()
        provider.tool_schemas = AsyncMock(return_value=[{"type": "function"}])
        provider.call = AsyncMock(side_effect=[presets, analytics])

        round1 = [
            {"id": "call-1", "function": {"name": "get_presets", "arguments": "{}"}}
        ]
        round2 = [
            {
                "id": "call-2",
                "function": {
                    "name": "run_preset",
                    "arguments": '{"preset_id": "comparar_control"}',
                },
            }
        ]
        saptiva_client = MagicMock()
        saptiva_client.chat_completion = AsyncMock(
            side_effect=[
                _decide_response(tool_calls=round1),
                _decide_response(tool_calls=round2),
            ]
        )
        orchestrator = FunctionCallingOrchestrator(provider=provider)

        messages = [{"role": "user", "content": "compárame vs tienda control"}]
        result_messages, tool_result, status = await orchestrator.augment(
            saptiva_client, messages, model="turbo"
        )

        assert tool_result == analytics
        assert status == "ok"
        # original + [assistant+tool] round 1 + [assistant+tool] round 2
        assert len(result_messages) == 5
        assert saptiva_client.chat_completion.await_count == 2
        # El round 2 recibió los mensajes aumentados del round 1 + el nudge de
        # sistema (solo en la llamada decide, NO en los mensajes devueltos)
        segunda_llamada = saptiva_client.chat_completion.await_args_list[1]
        assert len(segunda_llamada.kwargs["messages"]) == 4
        assert segunda_llamada.kwargs["messages"][2]["name"] == "get_presets"
        assert segunda_llamada.kwargs["messages"][3]["role"] == "system"
        assert (
            "Decide usando las herramientas"
            in segunda_llamada.kwargs["messages"][3]["content"]
        )
        assert all(
            "Decide usando las herramientas" not in str(m.get("content", ""))
            for m in result_messages
        )

    async def test_data_in_round_one_skips_second_hop(self):
        """Si el round 1 ya trajo datos, NO hay segunda llamada al LLM (latencia intacta)."""
        analytics = {"metric_name": "venta_hora", "series": []}
        provider = MagicMock()
        provider.tool_schemas = AsyncMock(return_value=[{"type": "function"}])
        provider.call = AsyncMock(return_value=analytics)

        tool_calls = [
            {
                "id": "call-1",
                "function": {"name": "retail_analytics", "arguments": "{}"},
            }
        ]
        saptiva_client = MagicMock()
        saptiva_client.chat_completion = AsyncMock(
            return_value=_decide_response(tool_calls=tool_calls)
        )
        orchestrator = FunctionCallingOrchestrator(provider=provider)

        result_messages, tool_result, status = await orchestrator.augment(
            saptiva_client, [{"role": "user", "content": "venta hoy"}], model="turbo"
        )

        assert tool_result == analytics
        assert status == "ok"
        assert len(result_messages) == 3
        assert saptiva_client.chat_completion.await_count == 1

    async def test_meta_only_then_no_calls_narrates_over_meta(self):
        """Round 2 sin tool_calls → se narra sobre la metadata del round 1 (como hoy)."""
        presets = {"presets": []}
        provider = MagicMock()
        provider.tool_schemas = AsyncMock(return_value=[{"type": "function"}])
        provider.call = AsyncMock(return_value=presets)

        round1 = [
            {"id": "call-1", "function": {"name": "get_presets", "arguments": "{}"}}
        ]
        saptiva_client = MagicMock()
        saptiva_client.chat_completion = AsyncMock(
            side_effect=[
                _decide_response(tool_calls=round1),
                _decide_response(tool_calls=None),
            ]
        )
        orchestrator = FunctionCallingOrchestrator(provider=provider)

        result_messages, tool_result, status = await orchestrator.augment(
            saptiva_client, [{"role": "user", "content": "x"}], model="turbo"
        )

        # La metadata de catálogo NO se promueve al canvas
        assert tool_result is None
        assert status == "ok"
        # ...pero los mensajes tool del round 1 sí quedan para narrar
        assert len(result_messages) == 3
        assert result_messages[2]["role"] == "tool"

    async def test_second_hop_exception_keeps_round_one_augmentation(self):
        """Si el round 2 explota, se conserva el round 1 completo (fail-safe)."""
        presets = {"presets": []}
        provider = MagicMock()
        provider.tool_schemas = AsyncMock(return_value=[{"type": "function"}])
        provider.call = AsyncMock(return_value=presets)

        round1 = [
            {"id": "call-1", "function": {"name": "get_presets", "arguments": "{}"}}
        ]
        saptiva_client = MagicMock()
        saptiva_client.chat_completion = AsyncMock(
            side_effect=[
                _decide_response(tool_calls=round1),
                RuntimeError("timeout en round 2"),
            ]
        )
        orchestrator = FunctionCallingOrchestrator(provider=provider)

        result_messages, tool_result, status = await orchestrator.augment(
            saptiva_client, [{"role": "user", "content": "x"}], model="turbo"
        )

        assert tool_result is None
        assert status == "ok"  # el round 1 completo es grounding real
        assert len(result_messages) == 3  # round 1 completo conservado
        assert result_messages[1]["role"] == "assistant"
        assert result_messages[2]["role"] == "tool"

    async def test_tool_call_exception_contained_and_retried_in_round_two(self):
        """Un call que LANZA (ej. kwarg inválido) se contiene como error-resultado
        y el round 2 puede auto-corregir la llamada."""
        analytics = {"metric_name": "venta_hora", "series": [{"points": []}]}
        provider = MagicMock()
        provider.tool_schemas = AsyncMock(return_value=[{"type": "function"}])
        provider.call = AsyncMock(
            side_effect=[
                RuntimeError("unexpected keyword argument 'categoria'"),
                analytics,
            ]
        )

        round1 = [
            {
                "id": "call-1",
                "function": {
                    "name": "retail_analytics",
                    "arguments": '{"categoria": "refrescos"}',
                },
            }
        ]
        round2 = [
            {
                "id": "call-2",
                "function": {
                    "name": "retail_analytics",
                    "arguments": '{"metric_or_query": "venta refrescos"}',
                },
            }
        ]
        saptiva_client = MagicMock()
        saptiva_client.chat_completion = AsyncMock(
            side_effect=[
                _decide_response(tool_calls=round1),
                _decide_response(tool_calls=round2),
            ]
        )
        orchestrator = FunctionCallingOrchestrator(provider=provider)

        result_messages, tool_result, status = await orchestrator.augment(
            saptiva_client, [{"role": "user", "content": "refrescos"}], model="turbo"
        )

        assert status == "ok"
        assert tool_result == analytics
        # El error del round 1 quedó como mensaje tool (grounding del retry)
        assert "tool_call_failed" in result_messages[2]["content"]
        assert saptiva_client.chat_completion.await_count == 2

    async def test_two_meta_rounds_stop_at_max(self):
        """El LLM insiste en meta-tools ambos rounds → tope en 2, sin loop."""
        presets = {"presets": []}
        provider = MagicMock()
        provider.tool_schemas = AsyncMock(return_value=[{"type": "function"}])
        provider.call = AsyncMock(return_value=presets)

        round_calls = [
            {"id": "call-1", "function": {"name": "get_presets", "arguments": "{}"}}
        ]
        saptiva_client = MagicMock()
        saptiva_client.chat_completion = AsyncMock(
            return_value=_decide_response(tool_calls=round_calls)
        )
        orchestrator = FunctionCallingOrchestrator(provider=provider)

        result_messages, tool_result, status = await orchestrator.augment(
            saptiva_client, [{"role": "user", "content": "x"}], model="turbo"
        )

        assert tool_result is None
        assert status == "ok"
        assert saptiva_client.chat_completion.await_count == 2  # nunca 3
        assert len(result_messages) == 5  # original + 2 rounds completos


@pytest.mark.unit
class TestDataToolOffNotice:
    """El aviso del flanco "tool apagada" (card pill-retail-default-nudge)."""

    def test_notice_shape_and_content(self):
        from src.services.streaming.function_calling import DATA_TOOL_OFF_NOTICE

        assert DATA_TOOL_OFF_NOTICE["role"] == "system"
        content = DATA_TOOL_OFF_NOTICE["content"]
        # Debe prohibir cifras de memoria y el falso "llamando a la herramienta"
        assert "DESACTIVADA" in content
        assert "cifras" in content
        # Debe empujar la acción correcta (activar la tool), no solo negar
        assert "activarla" in content or "activada" in content

    async def test_promueve_el_resultado_mas_rico_no_el_ultimo(self):
        """Compare por-entidad: la última llamada suele ser la más pobre; el
        canvas debe recibir el resultado con MÁS puntos del turno."""
        rico = {
            "metric_name": "venta_hora",
            "series": [
                {
                    "name": "v",
                    "points": [{"label": "a", "value": 1}, {"label": "b", "value": 2}],
                }
            ],
        }
        pobre = {
            "metric_name": "venta_hora",
            "series": [{"name": "v", "points": [{"label": "b", "value": 2}]}],
        }
        provider = MagicMock()
        provider.tool_schemas = AsyncMock(return_value=[{"type": "function"}])
        provider.call = AsyncMock(side_effect=[rico, pobre])
        calls = [
            {"id": "c1", "function": {"name": "t", "arguments": "{}"}},
            {"id": "c2", "function": {"name": "t", "arguments": "{}"}},
        ]
        saptiva_client = MagicMock()
        saptiva_client.chat_completion = AsyncMock(
            return_value=_decide_response(tool_calls=calls)
        )
        orchestrator = FunctionCallingOrchestrator(provider=provider)

        _, tool_result, status = await orchestrator.augment(
            saptiva_client, [{"role": "user", "content": "x"}], model="turbo"
        )

        assert status == "ok"
        assert tool_result is rico  # no el último (pobre)


@pytest.mark.unit
@pytest.mark.asyncio
class TestDecideModelDedicado:
    """Modelo dedicado al decide (card decide-robusto): Turbo emite args
    rotos según el fraseo; el decide puede correr en otro modelo sin tocar
    la narración, con fallback al de la sesión si el dedicado falla."""

    def _provider_con_datos(self):
        provider = MagicMock()
        provider.tool_schemas = AsyncMock(return_value=[{"type": "function"}])
        provider.call = AsyncMock(
            return_value={
                "metric_name": "venta_hora",
                "series": [{"name": "v", "points": [{"label": "a", "value": 1}]}],
            }
        )
        return provider

    async def test_decide_usa_el_modelo_dedicado(self):
        provider = self._provider_con_datos()
        calls = [{"id": "c1", "function": {"name": "t", "arguments": "{}"}}]
        saptiva_client = MagicMock()
        saptiva_client.chat_completion = AsyncMock(
            return_value=_decide_response(tool_calls=calls)
        )
        orchestrator = FunctionCallingOrchestrator(provider=provider)

        _, _, status = await orchestrator.augment(
            saptiva_client,
            [{"role": "user", "content": "x"}],
            model="turbo",
            decide_model="ops",
        )

        assert status == "ok"
        assert saptiva_client.chat_completion.await_args.kwargs["model"] == "ops"

    async def test_fallback_al_modelo_de_la_sesion_si_el_dedicado_falla(self):
        provider = self._provider_con_datos()
        calls = [{"id": "c1", "function": {"name": "t", "arguments": "{}"}}]
        saptiva_client = MagicMock()
        saptiva_client.chat_completion = AsyncMock(
            side_effect=[
                RuntimeError("404 model not found"),
                _decide_response(tool_calls=calls),
            ]
        )
        orchestrator = FunctionCallingOrchestrator(provider=provider)

        _, tool_result, status = await orchestrator.augment(
            saptiva_client,
            [{"role": "user", "content": "x"}],
            model="turbo",
            decide_model="ops-caido",
        )

        assert status == "ok"
        assert tool_result is not None
        modelos = [
            c.kwargs["model"] for c in saptiva_client.chat_completion.await_args_list
        ]
        assert modelos == ["ops-caido", "turbo"]

    async def test_sin_decide_model_no_hay_fallback_extra(self):
        provider = self._provider_con_datos()
        saptiva_client = MagicMock()
        saptiva_client.chat_completion = AsyncMock(
            side_effect=RuntimeError("proveedor caído")
        )
        orchestrator = FunctionCallingOrchestrator(provider=provider)

        messages = [{"role": "user", "content": "x"}]
        result_messages, tool_result, status = await orchestrator.augment(
            saptiva_client, messages, model="turbo"
        )

        # Fail-safe exterior intacto: sin decide_model, el error sube y se
        # degrada a "failed" (aviso TOOLS_UNAVAILABLE en el caller).
        assert status == "failed"
        assert tool_result is None
        assert result_messages == messages
        assert saptiva_client.chat_completion.await_count == 1


def _mensaje_tool(result: dict) -> dict:
    return {
        "role": "tool",
        "tool_call_id": "call-1",
        "name": "retail_analytics",
        "content": json.dumps(result, ensure_ascii=False),
    }


@pytest.mark.unit
class TestNarracionDirectaDelPlugin:
    """Card latencia-chat-retail-prediccion: con UNA tool de datos y
    `response_text` confiable, la segunda narración LLM es redundante.
    Detección SOLO por forma del contrato genérico (regla anti-deuda #1)."""

    BASE = [{"role": "user", "content": "faltante hoy"}]
    ANALYTICS = {
        "metric_name": "prediccion_faltante",
        "series": [],
        "table_data": [{"articulo_id": "SKU001"}],
        "response_text": "3 artículos en riesgo de faltante hoy.",
    }

    def _aumentados(self, *results: dict) -> list:
        return [
            *self.BASE,
            {"role": "assistant", "content": "", "tool_calls": []},
            *[_mensaje_tool(r) for r in results],
        ]

    def test_una_tool_de_datos_con_texto_devuelve_narracion(self):
        aumentados = self._aumentados(self.ANALYTICS)
        assert (
            narracion_directa_del_plugin(self.BASE, aumentados, self.ANALYTICS)
            == "3 artículos en riesgo de faltante hoy."
        )

    def test_varias_tools_de_datos_conservan_narracion_llm(self):
        # Comparaciones (una llamada por tienda): el LLM SÍ sintetiza.
        otro = {**self.ANALYTICS, "metric_name": "ventas_totales"}
        aumentados = self._aumentados(self.ANALYTICS, otro)
        assert (
            narracion_directa_del_plugin(self.BASE, aumentados, self.ANALYTICS) is None
        )

    def test_sin_tool_result_no_hay_narracion_directa(self):
        assert narracion_directa_del_plugin(self.BASE, list(self.BASE), None) is None

    def test_response_text_vacio_conserva_narracion_llm(self):
        sin_texto = {"metric_name": "x", "series": [], "response_text": "  "}
        aumentados = self._aumentados(sin_texto)
        assert narracion_directa_del_plugin(self.BASE, aumentados, sin_texto) is None

    def test_resultado_con_error_conserva_narracion_llm(self):
        con_error = {**self.ANALYTICS, "error": "no_data"}
        aumentados = self._aumentados(con_error)
        assert narracion_directa_del_plugin(self.BASE, aumentados, con_error) is None

    def test_con_el_atajo_apagado_siempre_narra_el_llm(self):
        # Equipo, 2026-10-15: "siempre en el chat explique con un LLM y bien
        # formateado; en el panel ya pones la gráfica". El atajo queda como
        # palanca de latencia, apagada por omisión.
        aumentados = self._aumentados(self.ANALYTICS)
        apagado = MagicMock(retail_advisor_direct_narration=False)
        assert (
            narracion_directa_del_plugin(
                self.BASE, aumentados, self.ANALYTICS, settings=apagado
            )
            is None
        )
        encendido = MagicMock(retail_advisor_direct_narration=True)
        assert (
            narracion_directa_del_plugin(
                self.BASE, aumentados, self.ANALYTICS, settings=encendido
            )
            == "3 artículos en riesgo de faltante hoy."
        )

    def test_texto_identico_a_la_respuesta_anterior_lo_narra_el_llm(self):
        # "explícame" tras un ranking: el decide repite la consulta y el
        # plugin devuelve el mismo texto; publicarlo directo repetía la
        # respuesta letra por letra (producción, 2026-10-15).
        previa = [
            {"role": "user", "content": "refrescos más vendidos"},
            {"role": "assistant", "content": self.ANALYTICS["response_text"]},
            {"role": "user", "content": "explícame"},
        ]
        aumentados = [
            *previa,
            {"role": "assistant", "content": "", "tool_calls": []},
            _mensaje_tool(self.ANALYTICS),
        ]
        assert narracion_directa_del_plugin(previa, aumentados, self.ANALYTICS) is None

    def test_texto_distinto_al_anterior_conserva_la_narracion_directa(self):
        previa = [
            {"role": "user", "content": "venta de ayer"},
            {"role": "assistant", "content": "Ayer: 1,200 unidades."},
            {"role": "user", "content": "faltante hoy"},
        ]
        aumentados = [*previa, _mensaje_tool(self.ANALYTICS)]
        assert (
            narracion_directa_del_plugin(previa, aumentados, self.ANALYTICS)
            == "3 artículos en riesgo de faltante hoy."
        )

    def test_tool_de_catalogo_extra_no_bloquea_la_narracion_directa(self):
        # Metadata de catálogo (get_presets) NO es resultado de datos: no
        # cuenta para el criterio de "exactamente una tool de datos".
        catalogo = {"presets": ["faltante", "ventas"]}
        aumentados = self._aumentados(catalogo, self.ANALYTICS)
        assert (
            narracion_directa_del_plugin(self.BASE, aumentados, self.ANALYTICS)
            == "3 artículos en riesgo de faltante hoy."
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ambito_del_perfil_se_inyecta_y_pisa_al_llm():
    """T3 perfiles: el ámbito del usuario viaja en cada tool que lo declara y
    manda sobre lo que el LLM haya puesto; las tools sin `ambito` no lo reciben."""
    provider = MagicMock()
    provider.tool_schemas = AsyncMock(
        return_value=[
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
    )
    provider.call = AsyncMock(
        return_value={"metric_name": "venta_hora", "chart_type": "line", "series": []}
    )
    tool_calls = [
        {
            "id": "c1",
            "function": {
                "name": "retail_analytics",
                # El LLM intenta ampliar el ámbito: se ignora.
                "arguments": '{"metric_or_query": "venta", "ambito": {"rol": "compras"}}',
            },
        },
        {"id": "c2", "function": {"name": "get_presets", "arguments": "{}"}},
    ]
    saptiva_client = MagicMock()
    saptiva_client.chat_completion = AsyncMock(
        return_value=_decide_response(tool_calls=tool_calls)
    )
    ambito = {"rol": "gerente_tienda", "tienda_id": "652", "usuario": "gerente.centro"}
    _, _, status = await FunctionCallingOrchestrator(provider=provider).augment(
        saptiva_client,
        [{"role": "user", "content": "venta"}],
        model="turbo",
        ambito=ambito,
    )
    assert status == "ok"
    llamadas = {c.args[0]: c.args[1] for c in provider.call.await_args_list}
    assert llamadas["retail_analytics"]["ambito"] == ambito
    assert llamadas["retail_analytics"]["metric_or_query"] == "venta"
    assert "ambito" not in llamadas["get_presets"]
    # El perfil se muestra al decide como PRIMER mensaje (para que sepa quién
    # pregunta) y nunca viaja a la narración.
    decide_msgs = saptiva_client.chat_completion.await_args.kwargs["messages"]
    assert decide_msgs[0]["role"] == "system"
    assert "gerente.centro" in decide_msgs[0]["content"]
    assert "652" in decide_msgs[0]["content"]
    assert decide_msgs[1] == {"role": "user", "content": "venta"}


@pytest.mark.unit
def test_narracion_llm_cuando_una_tool_del_turno_declaro_un_hueco():
    """Turno con un hueco declarado (error) + otra tool con datos: publicar
    solo el texto de la segunda ocultaba la limitación (visto 2026-09-03 con
    "¿qué está hoy sin existencia?": se perdía la mención de P-03)."""
    originales = [{"role": "user", "content": "¿qué está hoy sin existencia?"}]
    con_datos = {
        "metric_name": "quiebre_probable",
        "series": [],
        "response_text": "Quiebre probable: 34 SKUs con confianza alta.",
    }
    aumentados = [
        *originales,
        {"role": "assistant", "content": "", "tool_calls": []},
        {
            "role": "tool",
            "content": json.dumps(
                {
                    "metric_name": "faltante",
                    "error": "dato_faltante",
                    "response_text": "No puedo calcular Faltante: falta stock diario (P-03).",
                    "grounding": {"router": {"ruta": "cannot_answer"}},
                }
            ),
        },
        {"role": "tool", "content": json.dumps(con_datos)},
    ]
    assert narracion_directa_del_plugin(originales, aumentados, con_datos) is None
    # Y la narración recibe el aviso de reproducir el motivo del hueco.
    from src.services.streaming.function_calling import (
        HUECO_DECLARADO_NOTICE,
        aviso_post_decide,
        hubo_hueco_declarado,
    )

    assert hubo_hueco_declarado(originales, aumentados) is True
    assert (
        aviso_post_decide(originales, "ok", got_data=True, hueco_declarado=True)
        is HUECO_DECLARADO_NOTICE
    )
    # Sin hueco, el atajo de latencia se conserva.
    sin_hueco = [*originales, {"role": "tool", "content": json.dumps(con_datos)}]
    assert (
        narracion_directa_del_plugin(originales, sin_hueco, con_datos)
        == con_datos["response_text"]
    )
    # Un error de ACLARACIÓN no es hueco: suele ser un intento fallido que otra
    # llamada del mismo turno ya corrigió; tratarlo como hueco tapaba la
    # respuesta buena (ranking de refrescos, 2026-09-03).
    con_aclaracion = [
        *originales,
        {
            "role": "tool",
            "content": json.dumps(
                {
                    "error": "unknown_articulo",
                    "response_text": "No identifico un único artículo para 'refrescos'.",
                    "grounding": {"router": {"ruta": "clarify"}},
                }
            ),
        },
        {"role": "tool", "content": json.dumps(con_datos)},
    ]
    assert hubo_hueco_declarado(originales, con_aclaracion) is False
    assert (
        narracion_directa_del_plugin(originales, con_aclaracion, con_datos)
        == con_datos["response_text"]
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("dedicado", "status", "esperado"),
    [
        # Turno con datos: narrar con el modelo sin thinking.
        ("gemma-4-26b", "ok", "gemma-4-26b"),
        # La infra falló: también narra el dedicado (hay que redactar el aviso).
        ("gemma-4-26b", "failed", "gemma-4-26b"),
        # "Explícame" no llama tools pero narra el turno previo: con el modelo
        # de la sesión costaba 39.6 s en producción (2026-09-03).
        ("gemma-4-26b", "no_calls", "gemma-4-26b"),
        # Pill apagado: conversación general, respeta al usuario.
        ("gemma-4-26b", "off", "qwen-de-la-sesion"),
        ("gemma-4-26b", "disabled", "qwen-de-la-sesion"),
        # Sin configurar: comportamiento previo.
        (None, "ok", "qwen-de-la-sesion"),
    ],
)
def test_modelo_para_narrar(dedicado, status, esperado):
    """Un turno con datos solo se redacta, y ahí un razonador estorba: gasta
    el presupuesto pensando y puede devolver vacío (medido 2026-09-03)."""
    from src.services.streaming.function_calling import modelo_para_narrar

    settings = MagicMock(retail_advisor_narration_model=dedicado)
    assert modelo_para_narrar(settings, "qwen-de-la-sesion", status) == esperado


FOLLOW_UP = [
    {"role": "user", "content": "¿refrescos más vendidos?"},
    {"role": "assistant", "content": "Top 10: 1. Coca-Cola 472 u..."},
    {"role": "user", "content": "explícame"},
]


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("historial", "status", "tool_result", "espera_aviso"),
    [
        # Follow-up sin llamada a tool (visto en local).
        (FOLLOW_UP, "no_calls", None, "seguimiento"),
        # Follow-up CON llamada que volvió vacía (visto en producción): la
        # narración explicaba el hueco e inventaba causas.
        (FOLLOW_UP, "ok", None, "seguimiento"),
        # Turno con datos nuevos: narra sobre ellos, sin aviso.
        (FOLLOW_UP, "ok", {"metric_name": "venta_hora", "series": []}, None),
        # Primer turno sin llamada: el aviso también va (2026-10-20: sin él
        # el narrador negaba datos que no consultó), el de primer turno desde
        # el 2026-10-21 (P1.4); con "hola" no estorba.
        ([{"role": "user", "content": "hola"}], "no_calls", None, "primer_turno"),
    ],
)
async def test_turno_sin_datos_nuevos_anexa_aviso_para_narrar(
    historial, status, tool_result, espera_aviso
):
    """ "Explícame" tras una respuesta con cifras: sin datos nuevos, la
    narración debe explicar lo ya dicho, no inventar causas ni escribir tool
    calls como texto."""
    from unittest.mock import patch

    from src.services.streaming.function_calling import (
        FOLLOW_UP_SIN_DATOS_NOTICE,
        PRIMER_TURNO_SIN_CONSULTA_NOTICE,
        augmentar_con_tools_de_dominio,
    )

    settings = MagicMock(
        retail_advisor_function_calling=True, retail_advisor_decide_model=None
    )
    with patch(
        "src.services.streaming.function_calling.FunctionCallingOrchestrator.augment",
        new=AsyncMock(return_value=(list(historial), tool_result, status)),
    ):
        mensajes, resultado, status_out = await augmentar_con_tools_de_dominio(
            settings=settings,
            saptiva_client=MagicMock(),
            messages=historial,
            model="turbo",
            request_tools={"retail_advisor": True},
        )
    assert status_out == status and resultado == tool_result
    assert (FOLLOW_UP_SIN_DATOS_NOTICE in mensajes) is (espera_aviso == "seguimiento")
    assert (PRIMER_TURNO_SIN_CONSULTA_NOTICE in mensajes) is (
        espera_aviso == "primer_turno"
    )


def _turno_con_tools(historial, *resultados):
    """Historial + la llamada del decide + un mensaje `tool` por resultado."""
    return [
        *historial,
        {"role": "assistant", "content": "", "tool_calls": [{"id": "c1"}]},
        *({"role": "tool", "content": json.dumps(r)} for r in resultados),
    ]


async def _augmentar_con(historial, aumentados, tool_result, status="ok"):
    from unittest.mock import patch

    from src.services.streaming.function_calling import augmentar_con_tools_de_dominio

    settings = MagicMock(
        retail_advisor_function_calling=True, retail_advisor_decide_model=None
    )
    with patch(
        "src.services.streaming.function_calling.FunctionCallingOrchestrator.augment",
        new=AsyncMock(return_value=(aumentados, tool_result, status)),
    ):
        mensajes, _, _ = await augmentar_con_tools_de_dominio(
            settings=settings,
            saptiva_client=MagicMock(),
            messages=historial,
            model="turbo",
            request_tools={"retail_advisor": True},
        )
    return mensajes


@pytest.mark.unit
@pytest.mark.asyncio
async def test_turno_con_datos_anexa_el_aviso_de_formato_para_narrar():
    """Con resultados de datos la narración LLM recibe cómo formatear la
    respuesta (frase con la cifra principal, viñetas con las cifras tal cual,
    cierre con periodo y fecha); la gráfica ya va en el panel."""
    from src.services.streaming.function_calling import NARRACION_DATOS_NOTICE

    historial = [{"role": "user", "content": "venta de ayer"}]
    datos = {"metric_name": "venta_hora", "series": [], "response_text": "Ayer: 1,200."}
    mensajes = await _augmentar_con(
        historial, _turno_con_tools(historial, datos), datos
    )
    assert mensajes[-1] is NARRACION_DATOS_NOTICE
    assert "markdown" in NARRACION_DATOS_NOTICE["content"].lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tool_con_contenido_sin_datos_no_anexa_aviso_de_seguimiento():
    """ "¿qué datos de venta tienes?" tras dos presentaciones: el decide llamó
    al catálogo y el catálogo llegó, pero no es un resultado de datos. El
    aviso "En este turno no se obtuvieron datos nuevos" hacía que el narrador
    lo repitiera al usuario en vez de usar el catálogo (producción,
    2026-10-15)."""
    from src.services.streaming.function_calling import FOLLOW_UP_SIN_DATOS_NOTICE

    historial = [
        {"role": "user", "content": "Hola, que puedes hacer?"},
        {"role": "assistant", "content": "Puedo responder sobre las catorce tiendas."},
        {"role": "user", "content": "que datos de venta tienes?"},
    ]
    catalogo = {"metrics": [{"id": "venta_hora", "label": "Venta por hora"}]}
    mensajes = await _augmentar_con(
        historial, _turno_con_tools(historial, catalogo), None
    )
    assert FOLLOW_UP_SIN_DATOS_NOTICE not in mensajes


@pytest.mark.unit
@pytest.mark.asyncio
async def test_follow_up_con_aclaracion_no_narra_cifras_viejas():
    """P0-4 de la auditoría: "¿y Xalapa?" ambiguo devolvía clarify y el aviso
    de follow-up pedía narrar "citando esas cifras tal cual" del turno
    anterior: la respuesta nueva salía con las cifras de Centro."""
    from src.services.streaming.function_calling import (
        ACLARACION_NOTICE,
        FOLLOW_UP_SIN_DATOS_NOTICE,
    )

    aclaracion = {
        "error": "unknown_tienda",
        "response_text": "Hay dos tiendas Xalapa: Crystal (4) y Animas (48).",
        "grounding": {"router": {"ruta": "clarify"}},
    }
    mensajes = await _augmentar_con(
        FOLLOW_UP, _turno_con_tools(FOLLOW_UP, aclaracion), None
    )
    # Desde FEAT aclaracion-salida-valida la aclaración tiene su propio aviso
    # (transmitir la pregunta); lo que no cambia es que no se citan cifras viejas.
    assert ACLARACION_NOTICE in mensajes
    assert FOLLOW_UP_SIN_DATOS_NOTICE not in mensajes


@pytest.mark.unit
@pytest.mark.asyncio
async def test_follow_up_con_tools_caidas_declara_la_falla():
    """Todas las llamadas fallaron por excepción (contenidas como
    tool_call_failed): es infraestructura, no una aclaración."""
    from src.services.streaming.function_calling import (
        FOLLOW_UP_SIN_DATOS_NOTICE,
        TOOLS_UNAVAILABLE_NOTICE,
    )

    caida = {"error": "tool_call_failed: ConnectError"}
    mensajes = await _augmentar_con(
        FOLLOW_UP, _turno_con_tools(FOLLOW_UP, caida, caida), None
    )
    assert TOOLS_UNAVAILABLE_NOTICE in mensajes
    assert FOLLOW_UP_SIN_DATOS_NOTICE not in mensajes


@pytest.mark.unit
@pytest.mark.asyncio
async def test_error_corregido_en_el_mismo_turno_no_agrega_aviso():
    from src.services.streaming.function_calling import CONSULTA_FALLIDA_NOTICE

    datos = {"metric_name": "venta_hora", "series": [], "response_text": "ok"}
    aclaracion = {
        "error": "unknown_categoria",
        "grounding": {"router": {"ruta": "clarify"}},
    }
    mensajes = await _augmentar_con(
        FOLLOW_UP, _turno_con_tools(FOLLOW_UP, aclaracion, datos), datos
    )
    assert CONSULTA_FALLIDA_NOTICE not in mensajes


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sin_ambito_no_anexa_perfil_al_decide():
    provider = MagicMock()
    provider.tool_schemas = AsyncMock(return_value=[{"type": "function"}])
    provider.call = AsyncMock(return_value={"metric_name": "x", "series": []})
    saptiva_client = MagicMock()
    saptiva_client.chat_completion = AsyncMock(
        return_value=_decide_response(tool_calls=None)
    )
    await FunctionCallingOrchestrator(provider=provider).augment(
        saptiva_client, [{"role": "user", "content": "hola"}], model="turbo"
    )
    for llamada in saptiva_client.chat_completion.await_args_list:
        assert all(
            "Perfil del usuario" not in m["content"] for m in llamada.kwargs["messages"]
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sin_ambito_no_toca_los_argumentos():
    provider = MagicMock()
    provider.tool_schemas = AsyncMock(
        return_value=[
            {
                "type": "function",
                "function": {
                    "name": "retail_analytics",
                    "parameters": {"properties": {"metric_or_query": {}, "ambito": {}}},
                },
            }
        ]
    )
    provider.call = AsyncMock(return_value={"metric_name": "x", "series": []})
    saptiva_client = MagicMock()
    saptiva_client.chat_completion = AsyncMock(
        return_value=_decide_response(
            tool_calls=[
                {
                    "id": "c1",
                    "function": {
                        "name": "retail_analytics",
                        "arguments": '{"metric_or_query": "venta"}',
                    },
                }
            ]
        )
    )
    await FunctionCallingOrchestrator(provider=provider).augment(
        saptiva_client, [{"role": "user", "content": "venta"}], model="turbo"
    )
    assert provider.call.await_args.args[1] == {"metric_or_query": "venta"}


@pytest.mark.unit
def test_avisos_del_host_no_conocen_el_dominio():
    """Vicio 9 de la auditoría: reglas del dominio retail en el host. Los
    avisos del orquestador son genéricos; el detalle lo da el resultado de la
    tool."""
    import re

    from src.services.streaming import function_calling as fc

    avisos = {
        nombre: valor["content"]
        for nombre, valor in vars(fc).items()
        if nombre.endswith("_NOTICE") and isinstance(valor, dict)
    }
    assert "CONSULTA_FALLIDA_NOTICE" in avisos
    dominio = re.compile(
        r"\b(tiendas?|art[ií]culos?|categor[ií]as?|sku|refrescos?|inventario|merma)\b",
        re.IGNORECASE,
    )
    assert {n: dominio.findall(t) for n, t in avisos.items() if dominio.search(t)} == {}


# ---------------------------------------------------------------------------
# FEAT aclaracion-salida-valida (2026-10-09): una tool que pide precisar al
# usuario cierra el turno; un error de argumentos del modelo (reintentable)
# sigue permitiendo el round 2. Solo forma del contrato, sin dominio.
# ---------------------------------------------------------------------------


def _call(nombre, args):
    return {
        "id": f"c-{nombre}",
        "function": {"name": nombre, "arguments": json.dumps(args)},
    }


ACLARA = {
    "error": "aclaracion",
    "response_text": "¿Quieres venta o faltante?",
    "grounding": {
        "router": {"ruta": "clarify", "aclaracion": ["Venta por hora", "Faltante"]}
    },
}
REINTENTABLE = {
    "error": "missing_metric_or_query",
    "response_text": "Faltó metric_or_query.",
    "grounding": {"router": {"ruta": "clarify", "reintentable": True}},
}
DATOS = {"metric_name": "venta_hora", "series": [], "response_text": "ok"}


async def _augment_dos_rounds(resultados_round1, resultado_round2=DATOS):
    provider = MagicMock()
    provider.tool_schemas = AsyncMock(return_value=[{"type": "function"}])
    provider.call = AsyncMock(side_effect=[*resultados_round1, resultado_round2])
    client = MagicMock()
    client.chat_completion = AsyncMock(
        side_effect=[
            _decide_response([_call("t", {}) for _ in resultados_round1]),
            _decide_response([_call("t", {"metric_or_query": "venta"})]),
        ]
    )
    mensajes = [{"role": "user", "content": "¿cómo vamos?"}]
    aumentados, resultado, status = await FunctionCallingOrchestrator(
        provider=provider
    ).augment(client, mensajes, model="m")
    return aumentados, resultado, status, client.chat_completion.await_count


@pytest.mark.unit
@pytest.mark.asyncio
async def test_aclaracion_no_reintentable_cierra_el_turno_sin_round_2():
    aumentados, resultado, status, decides = await _augment_dos_rounds([ACLARA])
    assert status == "ok" and resultado is None
    assert decides == 1
    assert sum(m.get("role") == "tool" for m in aumentados) == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_error_reintentable_permite_round_2():
    _, resultado, status, decides = await _augment_dos_rounds([REINTENTABLE])
    assert status == "ok" and resultado == DATOS
    assert decides == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_aclaracion_y_datos_en_el_mismo_round_ganan_los_datos():
    from src.services.streaming.function_calling import ACLARACION_NOTICE

    _, resultado, _, decides = await _augment_dos_rounds([ACLARA, DATOS])
    assert resultado == DATOS and decides == 1
    mensajes = await _augmentar_con(
        FOLLOW_UP, _turno_con_tools(FOLLOW_UP, ACLARA, DATOS), DATOS
    )
    assert ACLARACION_NOTICE not in mensajes


@pytest.mark.unit
@pytest.mark.asyncio
async def test_aclaracion_sin_datos_anexa_su_aviso_y_no_el_de_consulta_fallida():
    from src.services.streaming.function_calling import (
        ACLARACION_NOTICE,
        CONSULTA_FALLIDA_NOTICE,
    )

    mensajes = await _augmentar_con(
        FOLLOW_UP, _turno_con_tools(FOLLOW_UP, ACLARA), None
    )
    assert ACLARACION_NOTICE in mensajes
    assert CONSULTA_FALLIDA_NOTICE not in mensajes


@pytest.mark.unit
def test_nudge_de_decide_ya_no_manda_adivinar():
    from src.services.streaming.function_calling import _NUDGE_DECIDE

    texto = _NUDGE_DECIDE["content"].lower()
    assert "más cercana" not in texto
    assert "no le pidas confirmación" not in texto
    assert "aclaración" in texto


@pytest.mark.unit
@pytest.mark.asyncio
async def test_pregunta_del_usuario_la_pone_el_host_en_las_tools_que_la_declaran():
    """Simulador de usuario (2026-10-11): gemma no llena `pregunta_usuario` ni
    en el reintento y el plugin no puede validar la métrica. El host conoce la
    pregunta: la copia tal cual (y los mensajes previos del usuario en
    `contexto_usuario`) en las tools que declaran esos parámetros. Es texto del
    usuario, no dominio; pisa lo que el modelo haya escrito."""
    provider = MagicMock()
    provider.tool_schemas = AsyncMock(
        return_value=[
            {
                "type": "function",
                "function": {
                    "name": "retail_analytics",
                    "parameters": {
                        "properties": {
                            "metric_or_query": {},
                            "pregunta_usuario": {},
                            "contexto_usuario": {},
                            "contexto_asistente": {},
                        }
                    },
                },
            },
            {
                "type": "function",
                "function": {"name": "get_presets", "parameters": {"properties": {}}},
            },
        ]
    )
    provider.call = AsyncMock(
        return_value={"metric_name": "venta_hora", "chart_type": "line", "series": []}
    )
    tool_calls = [
        {
            "id": "c1",
            "function": {
                "name": "retail_analytics",
                "arguments": '{"metric_or_query": "venta", "pregunta_usuario": "otra cosa"}',
            },
        },
        {"id": "c2", "function": {"name": "get_presets", "arguments": "{}"}},
    ]
    saptiva_client = MagicMock()
    saptiva_client.chat_completion = AsyncMock(
        return_value=_decide_response(tool_calls=tool_calls)
    )
    historial = [
        {"role": "system", "content": "prompt"},
        {"role": "user", "content": "cuanto vendimos de refrescos"},
        {"role": "assistant", "content": "Vendiste 10."},
        {
            "role": "user",
            "content": [{"type": "text", "text": "y la semana anterior?"}],
        },
    ]
    await FunctionCallingOrchestrator(provider=provider).augment(
        saptiva_client, historial, model="turbo"
    )
    llamadas = {c.args[0]: c.args[1] for c in provider.call.await_args_list}
    assert llamadas["retail_analytics"]["pregunta_usuario"] == "y la semana anterior?"
    assert llamadas["retail_analytics"]["contexto_usuario"] == [
        "cuanto vendimos de refrescos"
    ]
    # Lo que el chat ya mostró: "¿y de ese?" nombra un producto de la
    # respuesta anterior, no de lo que escribió el usuario (examen v2).
    assert llamadas["retail_analytics"]["contexto_asistente"] == ["Vendiste 10."]
    assert "pregunta_usuario" not in llamadas["get_presets"]
    assert "contexto_asistente" not in llamadas["get_presets"]


@pytest.mark.unit
def test_contexto_usuario_toma_los_ultimos_mensajes_del_usuario():
    from src.services.streaming.function_calling import textos_del_usuario

    historial = [{"role": "user", "content": f"m{i}"} for i in range(6)]
    historial.insert(2, {"role": "assistant", "content": "x"})
    pregunta, contexto = textos_del_usuario(historial)
    assert pregunta == "m5"
    assert contexto == ["m2", "m3", "m4"]
    assert textos_del_usuario([{"role": "system", "content": "s"}]) == (None, [])


@pytest.mark.unit
def test_contexto_asistente_toma_las_ultimas_respuestas_con_texto():
    from src.services.streaming.function_calling import textos_del_asistente

    historial = [
        {"role": "user", "content": "q productos estan en riesgo"},
        {"role": "assistant", "content": "r1"},
        {"role": "user", "content": "por q el primero"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "c1"}]},
        {"role": "tool", "content": "{}"},
        {"role": "assistant", "content": [{"type": "text", "text": "r2"}]},
        {"role": "assistant", "content": "r3"},
        {"role": "user", "content": "cuanto se vende de ese al dia"},
    ]
    assert textos_del_asistente(historial) == ["r2", "r3"]
    assert textos_del_asistente([{"role": "user", "content": "hola"}]) == []


@pytest.mark.unit
def test_avisos_piden_lenguaje_de_usuario_sin_referencias_tecnicas():
    """Respuestas sin jerga (2026-10-11): los avisos pedían reproducir el
    motivo "con sus referencias tal como aparecen" y el modelo copiaba códigos,
    "router de datos" y formatos de fecha."""
    from src.services.streaming.function_calling import (
        ACLARACION_NOTICE,
        CONSULTA_FALLIDA_NOTICE,
        HUECO_DECLARADO_NOTICE,
    )

    for aviso in (HUECO_DECLARADO_NOTICE, CONSULTA_FALLIDA_NOTICE, ACLARACION_NOTICE):
        texto = aviso["content"]
        assert "tal como aparecen" not in texto
        assert "con qué identificador" not in texto
        assert "sin códigos" in texto


@pytest.mark.unit
def test_nudge_no_prohibe_comparar_periodos():
    """FEAT comparar-periodos: "la semana pasada contra la anterior" es una
    comparación de ventanas distintas; el nudge la declaraba inválida."""
    from src.services.streaming.function_calling import _NUDGE_DECIDE

    texto = _NUDGE_DECIDE["content"]
    assert "ventanas distintas es inválida" not in texto
    assert "entre periodos" in texto


@pytest.mark.unit
async def test_nombre_de_argumento_casi_igual_se_corrige_contra_el_schema():
    """Conjunto de desarrollo (2026-10-11): gemma mandó `metrica_or_query` en
    lugar de `metric_or_query` en los dos rounds; la tool rechazó la llamada
    y el chat dijo "fallo técnico". El host conoce el schema de cada tool: un
    nombre casi idéntico a un parámetro declarado se corrige antes de llamar.
    Uno que no se parece a ninguno se deja para que el modelo lo corrija."""
    provider = MagicMock()
    provider.tool_schemas = AsyncMock(
        return_value=[
            {
                "type": "function",
                "function": {
                    "name": "retail_analytics",
                    "parameters": {
                        "properties": {
                            "metric_or_query": {},
                            "metrica": {},
                            "tienda": {},
                        }
                    },
                },
            }
        ]
    )
    provider.call = AsyncMock(
        return_value={"metric_name": "venta_hora", "chart_type": "line", "series": []}
    )
    tool_calls = [
        {
            "id": "c1",
            "function": {
                "name": "retail_analytics",
                "arguments": json.dumps(
                    {"metrica_or_query": "venta total", "tiendaa": "Cancún", "zzz": 1}
                ),
            },
        }
    ]
    saptiva_client = MagicMock()
    saptiva_client.chat_completion = AsyncMock(
        return_value=_decide_response(tool_calls=tool_calls)
    )
    await FunctionCallingOrchestrator(provider=provider).augment(
        saptiva_client,
        [{"role": "system", "content": "p"}, {"role": "user", "content": "venta"}],
        model="turbo",
    )
    args = provider.call.await_args_list[0].args[1]
    assert args["metric_or_query"] == "venta total"
    assert args["tienda"] == "Cancún"
    assert "metrica_or_query" not in args and "tiendaa" not in args
    assert "metrica" not in args  # no se corrige hacia un parámetro más lejano
    assert args["zzz"] == 1  # sin parecido: se deja y el error vuelve al modelo


@pytest.mark.unit
def test_correccion_de_argumentos_no_pisa_uno_ya_presente():
    from src.services.streaming.function_calling import ajustar_argumentos

    schema = {"properties": {"metric_or_query": {}, "metrica": {}}}
    args, cambios = ajustar_argumentos(
        schema, {"metric_or_query": "venta", "metrica_or_query": "otra"}
    )
    assert args["metric_or_query"] == "venta"
    assert args["metrica_or_query"] == "otra"
    assert cambios == {}


# feedback round 1 (2026-10-16, punto 13): el saludo del chat decía
# "analizar el desempeño de tu tienda... datos precisos y accionables" y
# "datos en tiempo real"; nada de eso lo dice el plugin. Un resultado que se
# declara literal (`grounding.narracion == "literal"`, contrato genérico) se
# entrega tal cual, sin capacidades ni promesas inventadas.
def _resultado_literal(texto: str) -> dict:
    return {
        "metric_name": "x",
        "chart_type": "none",
        "series": [],
        "table_data": [],
        "response_text": texto,
        "grounding": {"source": "plugin", "narracion": "literal"},
    }


@pytest.mark.unit
def test_hubo_narracion_literal_por_forma_del_contrato():
    from src.services.streaming.function_calling import hubo_narracion_literal

    original = [{"role": "user", "content": "hola"}]
    con_literal = [*original, _mensaje_tool(_resultado_literal("Soy el asistente."))]
    sin_literal = [*original, _mensaje_tool({"response_text": "x", "grounding": {}})]
    assert hubo_narracion_literal(original, con_literal) is True
    assert hubo_narracion_literal(original, sin_literal) is False
    # Solo cuenta lo de ESTE turno.
    assert hubo_narracion_literal(con_literal, con_literal) is False


@pytest.mark.unit
def test_aviso_literal_gana_al_de_datos_y_pide_entregar_el_texto_tal_cual():
    from src.services.streaming.function_calling import (
        NARRACION_DATOS_NOTICE,
        NARRACION_LITERAL_NOTICE,
        aviso_post_decide,
    )

    aviso = aviso_post_decide(
        [{"role": "user", "content": "hola"}], "ok", got_data=True, literal=True
    )
    assert aviso is NARRACION_LITERAL_NOTICE
    assert aviso is not NARRACION_DATOS_NOTICE
    texto = aviso["content"].lower()
    assert "tal cual" in texto
    assert "tiempo real" in texto


@pytest.mark.unit
def test_el_aviso_de_narracion_conserva_los_porcentajes_y_no_inventa_columnas():
    """Listado del 20 de octubre: con el mismo resultado del plugin, el
    narrador pasó de una tabla con "Diferencia (%)" a una con pesos y una
    columna "Calificación" (Baja/Alta) que el resultado no trae; G17, J08 y
    J13 quedaron 0 de 3 porque la respuesta perdió el porcentaje de cambio.
    El aviso pide conservar los porcentajes y prohíbe columnas inventadas."""
    from src.services.streaming.function_calling import NARRACION_DATOS_NOTICE

    texto = NARRACION_DATOS_NOTICE["content"].lower()
    assert "porcentaje" in texto
    assert "no agregues columnas" in texto
    # La frase que inducía la columna inventada ya no está.
    assert "la calificación de cada fila va en su columna" not in texto


# Producción, 2026-10-20: "Inventario de refrescos en Centro" y
# "¿Cuál es el precio de proveedor...?" terminaron en no_calls y el narrador
# afirmó "No tengo datos de inventario" y ofreció "consultar la base de datos
# de costos". Sin consulta no hay base para negar un dato ni para prometer
# una búsqueda: se pide la precisión que falta o se dice qué sí hay.
@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "historial",
    [
        [{"role": "user", "content": "Inventario de refrescos en Centro"}],
        FOLLOW_UP,
    ],
)
async def test_sin_consulta_el_aviso_prohibe_negar_datos_o_prometer_busquedas(
    historial,
):
    from src.services.streaming.function_calling import aviso_post_decide

    aviso = aviso_post_decide(historial, "no_calls", got_data=False)
    assert aviso is not None
    texto = aviso["content"].lower()
    assert "no afirmes que" in texto and "no existe" in texto
    assert "no ofrezcas" in texto and "buscar" in texto
    assert "precisión" in texto or "precision" in texto


@pytest.mark.unit
def test_el_aviso_de_seguimiento_sigue_pidiendo_explicar_con_lo_previo():
    from src.services.streaming.function_calling import aviso_post_decide

    aviso = aviso_post_decide(FOLLOW_UP, "no_calls", got_data=False)
    assert "respuesta anterior" in aviso["content"].lower()


@pytest.mark.unit
def test_el_aviso_de_narracion_exige_la_salvedad_y_prohibe_negar_lo_no_consultado():
    """Local, 2026-10-20: con el aviso del plugin ("No tengo existencias de
    julio: la única foto es la del 26 de agosto") el narrador escribió "Al
    cierre de julio..."; y tras consultar una sola ubicación afirmó "no tengo
    datos" de la otra, que nunca se consultó. Contrato genérico: el resultado
    trae `aviso_usuario` y la respuesta empieza con él."""
    from src.services.streaming.function_calling import NARRACION_DATOS_NOTICE

    texto = NARRACION_DATOS_NOTICE["content"]
    assert "aviso_usuario" in texto and "empieza la respuesta" in texto.lower()
    assert "no se consultó" in texto.lower()


# Ruteo del 20 de octubre (local 6 de 10, producción 0 de 1): ante "explícame"
# el decide repitió la consulta del ranking. El turno traía "datos", pero eran
# los ya respondidos, y con el aviso de datos nuevos el narrador repetía la
# tabla, cambiaba "Centro" por "tu tienda" e inventaba ("la que más dinero
# aporta" en un ranking por unidades). Un resultado cuyas cifras ya están todas
# en la respuesta anterior es un seguimiento sin datos nuevos.
RANKING_PREVIO = [
    {"role": "user", "content": "¿Cuáles son los refrescos más vendidos en Centro?"},
    {
        "role": "assistant",
        "content": (
            "La **Coca Cola 600 Ml** lidera con **4,042** unidades.\n\n"
            "| Artículo | Unidades |\n|---|---|\n"
            "| Coca Cola 600 Ml | **4,042** |\n"
            "| Coca Cola Regular 355 Ml | 2,882 |\n"
            "| Topo Chico 600 Ml | 1,239 |"
        ),
    },
    {"role": "user", "content": "explícame"},
]


def _ranking(*valores):
    return {
        "metric_name": "m",
        "series": [],
        "table_data": [{"label": f"a{i}", "value": v} for i, v in enumerate(valores)],
        "response_text": "Top 3 en Centro, últimos 28 días.",
    }


@pytest.mark.unit
@pytest.mark.parametrize(
    ("historial", "valores", "esperado"),
    [
        # Mismas cifras que la respuesta anterior: consulta repetida.
        (RANKING_PREVIO, (4042.0, 2882.0, 1239.0), True),
        # Una cifra que no se dijo: hay datos nuevos.
        (RANKING_PREVIO, (4042.0, 2882.0, 5310.0), False),
        # Sin respuesta anterior no hay qué repetir.
        (RANKING_PREVIO[:1], (4042.0, 2882.0, 1239.0), False),
        # Sin cifras en la tabla no hay base para decir que se repite.
        (RANKING_PREVIO, (), False),
        # "¿Por qué está en riesgo el primero?" (g05 del listado, 2026-10-20):
        # un solo renglón cuya cifra ya se dijo trae la explicación nueva; un
        # dato repetido no prueba que la consulta sea la misma.
        (RANKING_PREVIO, (4042.0,), False),
        (RANKING_PREVIO, (4042.0, 2882.0), False),
    ],
)
def test_resultado_repetido_por_las_cifras_de_la_respuesta_anterior(
    historial, valores, esperado
):
    from src.services.streaming.function_calling import resultado_repetido

    aumentados = _turno_con_tools(historial, _ranking(*valores))
    assert resultado_repetido(historial, aumentados) is esperado


@pytest.mark.unit
def test_resultado_repetido_solo_mira_las_tools_de_este_turno():
    from src.services.streaming.function_calling import resultado_repetido

    previo = _turno_con_tools(RANKING_PREVIO, _ranking(4042.0, 2882.0, 1239.0))
    assert resultado_repetido(previo, previo) is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_consulta_repetida_se_narra_como_seguimiento_sin_datos_nuevos():
    from src.services.streaming.function_calling import (
        FOLLOW_UP_SIN_DATOS_NOTICE,
        NARRACION_DATOS_NOTICE,
    )

    repetido = _ranking(4042.0, 2882.0, 1239.0)
    mensajes = await _augmentar_con(
        RANKING_PREVIO, _turno_con_tools(RANKING_PREVIO, repetido), repetido
    )
    assert FOLLOW_UP_SIN_DATOS_NOTICE in mensajes
    assert NARRACION_DATOS_NOTICE not in mensajes

    nuevo = _ranking(4042.0, 2882.0, 5310.0)
    mensajes = await _augmentar_con(
        RANKING_PREVIO, _turno_con_tools(RANKING_PREVIO, nuevo), nuevo
    )
    assert NARRACION_DATOS_NOTICE in mensajes


@pytest.mark.unit
def test_aviso_del_turno_es_el_mismo_que_usa_el_chat():
    """El runner de ruteo, el holdout y el simulador eligen el aviso con la
    misma función que el chat: con la consulta repetida, el de seguimiento."""
    from src.services.streaming.function_calling import (
        FOLLOW_UP_SIN_DATOS_NOTICE,
        aviso_del_turno,
    )

    repetido = _ranking(4042.0, 2882.0, 1239.0)
    aumentados = _turno_con_tools(RANKING_PREVIO, repetido)
    aviso = aviso_del_turno(RANKING_PREVIO, aumentados, "ok", got_data=True)
    assert aviso is FOLLOW_UP_SIN_DATOS_NOTICE


@pytest.mark.unit
@pytest.mark.parametrize(
    "nombre", ["NARRACION_DATOS_NOTICE", "FOLLOW_UP_SIN_DATOS_NOTICE"]
)
def test_los_avisos_piden_el_alcance_con_los_nombres_del_resultado(nombre):
    """Con "Centro, últimos 28 días" en el resultado, la respuesta decía "tu
    tienda": el alcance va con los nombres del resultado, sin posesivos."""
    import src.services.streaming.function_calling as fc

    texto = getattr(fc, nombre)["content"].lower()
    assert "alcance" in texto
    assert "mismos nombres" in texto
    assert "posesivo" in texto


@pytest.mark.unit
@pytest.mark.parametrize(
    "nombre", ["NARRACION_DATOS_NOTICE", "FOLLOW_UP_SIN_DATOS_NOTICE"]
)
def test_los_avisos_piden_las_fechas_en_palabras(nombre):
    """Sonda del 20 de octubre: las cuatro respuestas cerraban con "Datos al
    2026-09-30" (el `data_as_of` del resultado copiado tal cual); al usuario
    las fechas se le dicen en palabras."""
    import src.services.streaming.function_calling as fc

    texto = getattr(fc, nombre)["content"].lower()
    assert "fechas en palabras" in texto
    assert "aaaa-mm-dd" in texto


# QA (2026-10-20, P0.1): "¿qué tan bien le atinan las alertas?" sin
# perfil devolvió 1,336 filas y 1,336 puntos (427 KB); el mensaje `tool` iba
# entero al narrador, el proveedor contestó HTTP 530 y el chat echó el system
# prompt. El mensaje que ve el narrador se recorta por tamaño; el resultado
# completo sigue llegando al panel (tool_result).


def _resultado_grande(filas: int) -> dict:
    return {
        "metric_name": "m",
        "chart_type": "bar",
        "response_text": "Resumen con las cifras principales.",
        "grounding": {"source": "plugin", "total": filas},
        "table_data": [
            {"label": f"producto {i}", "value": float(i)} for i in range(filas)
        ],
        "series": [
            {
                "name": "s",
                "points": [{"x": str(i), "y": float(i)} for i in range(filas)],
            }
        ],
    }


@pytest.mark.unit
def test_el_mensaje_para_el_narrador_se_recorta_por_tamano():
    from src.services.streaming.function_calling import (
        LIMITE_MENSAJE_TOOL_CHARS,
        contenido_para_narrar,
    )

    grande = _resultado_grande(1336)
    texto = contenido_para_narrar(grande)
    assert len(texto) <= LIMITE_MENSAJE_TOOL_CHARS
    recortado = json.loads(texto)
    # Lo que el narrador necesita sigue entero; las filas y los puntos, acotados.
    assert recortado["response_text"] == grande["response_text"]
    assert recortado["grounding"]["total"] == 1336
    assert 0 < len(recortado["table_data"]) < 1336
    assert 0 < len(recortado["series"][0]["points"]) < 1336
    assert recortado["recorte"]["table_data"] == {
        "mostradas": len(recortado["table_data"]),
        "total": 1336,
    }
    assert recortado["recorte"]["series"] == {
        "mostrados": len(recortado["series"][0]["points"]),
        "total": 1336,
    }
    # El resultado original no se toca (va al panel).
    assert len(grande["table_data"]) == 1336


@pytest.mark.unit
def test_un_resultado_chico_viaja_tal_cual():
    from src.services.streaming.function_calling import contenido_para_narrar

    chico = _resultado_grande(10)
    assert json.loads(contenido_para_narrar(chico)) == chico


@pytest.mark.unit
@pytest.mark.asyncio
async def test_el_orquestador_recorta_el_mensaje_tool_y_promueve_el_resultado_entero():
    from src.services.streaming.function_calling import (
        LIMITE_MENSAJE_TOOL_CHARS,
        FunctionCallingOrchestrator,
    )

    grande = _resultado_grande(1336)

    class _Provider:
        async def tool_schemas(self):
            return [
                {
                    "type": "function",
                    "function": {
                        "name": "evaluar_alertas",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ]

        async def call(self, name, arguments):
            return grande

    client = MagicMock()
    client.chat_completion = AsyncMock(
        return_value=_decide_response(
            [{"id": "c1", "function": {"name": "evaluar_alertas", "arguments": "{}"}}]
        )
    )
    mensajes, resultado, status = await FunctionCallingOrchestrator(
        provider=_Provider()
    ).augment(
        client,
        [{"role": "user", "content": "¿qué tan bien le atinan las alertas?"}],
        model="m",
    )
    assert status == "ok"
    assert len(resultado["table_data"]) == 1336  # al panel, completo
    tool_msgs = [m for m in mensajes if m.get("role") == "tool"]
    assert tool_msgs and all(
        len(m["content"]) <= LIMITE_MENSAJE_TOOL_CHARS for m in tool_msgs
    )


@pytest.mark.unit
def test_nudge_decide_pide_una_llamada_por_medida():
    """Reporte de QA (2026-10-20, P1.4): "pedimos productos y su
    inventario y no dio el inventario"; por OpenRouter, la misma pregunta
    terminó sin llamadas (no_calls, 68-200 s). Dos medidas en una pregunta
    son dos llamadas en el mismo paso."""
    from src.services.streaming.function_calling import _NUDGE_DECIDE

    texto = _NUDGE_DECIDE["content"].lower()
    assert "una llamada por medida" in texto


@pytest.mark.unit
def test_primer_turno_sin_consulta_dice_que_no_alcanzo_y_propone_por_partes():
    """Sonda por OpenRouter (2026-10-21, P1.4 del reporte de QA):
    "los 5 refrescos más vendidos en Centro y su inventario" terminó en
    no_calls y el narrador afirmó "No tengo datos para Centro". En el primer
    turno no hay respuesta anterior que explicar: el aviso de seguimiento no
    aplica."""
    from src.services.streaming.function_calling import aviso_post_decide

    historial = [
        {"role": "user", "content": "Dame los 5 refrescos más vendidos y su inventario"}
    ]
    texto = aviso_post_decide(historial, "no_calls", got_data=False)["content"].lower()
    assert "no alcanzaste a consultar" in texto
    assert "por partes" in texto
    assert "respuesta anterior" not in texto


@pytest.mark.unit
def test_el_aviso_de_narracion_no_inventa_causas_ni_ofrece_lo_dado_y_resume_series():
    """Reporte de QA (2026-10-20): P1.7 inventó que la mercancía
    "está en bodega y no llega al piso" y habló de "flujo de clientes"; P2.4
    ofreció "el importe en pesos" justo después de darlo; P2.5 puso la
    disponibilidad en una tabla de 30 filas. El plugin entrega
    `resumen_serie` para las series largas."""
    from src.services.streaming.function_calling import NARRACION_DATOS_NOTICE

    texto = NARRACION_DATOS_NOTICE["content"].lower()
    assert "no atribuyas causas" in texto
    assert "no ofrezcas lo que ya" in texto
    assert "resumen_serie" in texto


# QA (2026-10-20, P2.6): preguntó en inglés y contestó en español.
# Decisión del equipo (2026-10-21): en el idioma de la pregunta, con español
# por omisión. Los avisos van al final del contexto, en español, junto a los
# resultados en español: sin la regla ahí, el narrador seguía en español
# aunque el system prompt pide el idioma del usuario (sonda con gemma por
# Saptiva, 2026-10-21).
@pytest.mark.unit
@pytest.mark.parametrize(
    "kwargs",
    [
        {"status": "ok", "got_data": True},
        {"status": "no_calls"},
        {"status": "failed"},
        {"status": "ok", "got_data": False, "aclaracion": True},
        {"status": "ok", "got_data": False, "errores": {"con_error": 1, "tools": 1}},
        {"status": "ok", "got_data": True, "hueco_declarado": True},
        {"status": "ok", "got_data": True, "literal": True},
    ],
)
def test_cada_aviso_de_narracion_pide_el_idioma_de_la_pregunta(kwargs):
    from src.services.streaming.function_calling import aviso_post_decide

    status = kwargs.pop("status")
    aviso = aviso_post_decide(
        [{"role": "user", "content": "How much did we sell?"}], status, **kwargs
    )
    texto = aviso["content"].lower()
    assert "idioma" in texto and "español" in texto


@pytest.mark.unit
def test_el_aviso_de_herramienta_apagada_tambien_pide_el_idioma():
    from src.services.streaming.function_calling import DATA_TOOL_OFF_NOTICE

    assert "idioma" in DATA_TOOL_OFF_NOTICE["content"].lower()


@pytest.mark.unit
def test_el_aviso_literal_traduce_si_la_pregunta_vino_en_otro_idioma():
    """ "Hi" llegaba a la presentación y salía en español: "entrégalo con sus
    mismas palabras" ganaba a la regla de idioma (sonda, 2026-10-21)."""
    from src.services.streaming.function_calling import NARRACION_LITERAL_NOTICE

    assert "tradúce" in NARRACION_LITERAL_NOTICE["content"].lower()


# Usuario simulado, 2026-11-06 (gerente exigente y jefa de piso nueva): los
# datos llegan al 30 de septiembre y el narrador presentó una lista "para
# mañana viernes 7 de noviembre" y sugirió pedir 90-120 piezas que no salían
# del resultado. Genérico: solo el `data_as_of` del contrato.
@pytest.mark.unit
def test_datos_viejos_el_aviso_dice_su_fecha_y_no_los_presenta_como_de_hoy():
    from datetime import date

    from src.services.streaming.function_calling import aviso_del_turno

    historial = [{"role": "user", "content": "que se me acaba mañana"}]
    datos = {"metric_name": "alerta", "series": [], "data_as_of": "2026-09-30"}
    aumentados = [*historial, {"role": "tool", "content": json.dumps(datos)}]
    aviso = aviso_del_turno(
        historial, aumentados, "ok", got_data=True, hoy=date(2026, 11, 6)
    )
    texto = aviso["content"]
    assert "2026-09-30" in texto and "37 días" in texto
    assert "primera frase" in texto
    assert "cantidades" in texto  # no inventa cuánto pedir


@pytest.mark.unit
def test_datos_del_dia_no_agregan_aviso_de_frescura():
    from datetime import date

    from src.services.streaming.function_calling import (
        NARRACION_DATOS_NOTICE,
        aviso_del_turno,
    )

    historial = [{"role": "user", "content": "venta de ayer"}]
    datos = {"metric_name": "venta", "series": [], "data_as_of": "2026-11-05"}
    aumentados = [*historial, {"role": "tool", "content": json.dumps(datos)}]
    aviso = aviso_del_turno(
        historial, aumentados, "ok", got_data=True, hoy=date(2026, 11, 6)
    )
    assert aviso is NARRACION_DATOS_NOTICE


@pytest.mark.unit
def test_el_aviso_de_datos_prohibe_calcular_escenarios_propios():
    """Usuario simulado, 2026-11-06: "si hago 2x1 en Coca, ¿cuánto vendo de
    más?" y el narrador calculó un margen a mano con un error (con el mismo
    costo a mitad de precio el margen es negativo, dijo que bajaba a la mitad)
    y metió una regla de retail inventada."""
    from src.services.streaming.function_calling import NARRACION_DATOS_NOTICE

    texto = NARRACION_DATOS_NOTICE["content"].lower()
    assert "escenario" in texto and "no calcules" in texto


def test_avisos_piden_lenguaje_de_tienda_sin_jerga_del_sistema():
    """SIM-12 (2026-11-06): el narrador decía "la consulta no devolvió el
    dato", "la herramienta de datos" y "la información de esta prueba" a un
    gerente. Los avisos con y sin datos piden hablar como en la tienda."""
    from src.services.streaming.function_calling import (
        FOLLOW_UP_SIN_DATOS_NOTICE,
        NARRACION_DATOS_NOTICE,
        PRIMER_TURNO_SIN_CONSULTA_NOTICE,
    )

    for aviso in (
        NARRACION_DATOS_NOTICE,
        FOLLOW_UP_SIN_DATOS_NOTICE,
        PRIMER_TURNO_SIN_CONSULTA_NOTICE,
    ):
        texto = aviso["content"]
        assert "lenguaje del usuario" in texto
        assert "'esta prueba'" in texto and "'la herramienta'" in texto


# Memoria de conversación (FEAT 2026-11-07): el plugin necesita el id de la
# conversación para recordar lo mostrado; va en `ambito` aunque no haya perfil
# y nunca entra al prompt del decide.
@pytest.mark.unit
def test_el_ambito_lleva_la_conversacion_aunque_no_haya_perfil():
    from src.services.streaming.function_calling import ambito_con_conversacion

    assert ambito_con_conversacion(None, "ses-123") == {"conversacion": "ses-123"}
    assert ambito_con_conversacion(None, None) is None


@pytest.mark.unit
def test_el_ambito_con_perfil_suma_la_conversacion():
    from src.services.streaming.function_calling import ambito_con_conversacion

    a = ambito_con_conversacion(
        {"rol": "gerente_tienda", "tienda_id": "236"}, "ses-123"
    )
    assert a["rol"] == "gerente_tienda" and a["conversacion"] == "ses-123"


@pytest.mark.unit
def test_el_nudge_del_perfil_no_menciona_la_conversacion():
    from src.services.streaming.function_calling import _nudge_perfil

    nudge = _nudge_perfil({"rol": "compras", "conversacion": "ses-123"})
    assert "ses-123" not in nudge["content"] and "conversacion" not in nudge["content"]
    assert _nudge_perfil({"conversacion": "ses-123"}) is None


@pytest.mark.unit
async def test_augmentar_pasa_la_conversacion_al_orquestador(monkeypatch):
    from src.services.streaming import function_calling as fc

    visto = {}

    async def _augment(self, client, messages, **kw):
        visto.update(kw)
        return messages, None, "no_calls"

    monkeypatch.setattr(fc.FunctionCallingOrchestrator, "augment", _augment)

    async def _sin_perfil(user_id):
        return None

    monkeypatch.setattr("src.services.perfil_usuario.ambito_de_usuario", _sin_perfil)
    settings = MagicMock(
        retail_advisor_decide_model=None, retail_advisor_function_calling=True
    )
    await fc.augmentar_con_tools_de_dominio(
        request_tools={"retail_advisor": True},
        settings=settings,
        saptiva_client=MagicMock(),
        messages=[{"role": "user", "content": "hola"}],
        model="turbo",
        user_id=None,
        conversacion_id="ses-123",
    )
    assert visto["ambito"] == {"conversacion": "ses-123"}


# Línea de ámbito (FEAT memoria-de-conversacion): el plugin la manda en
# grounding.ambito_texto y el backend la anexa por código tras la narración,
# una sola vez, en las dos rutas del chat.
@pytest.mark.unit
def test_anexo_de_ambito_agrega_la_linea_una_vez():
    from src.services.streaming.function_calling import anexo_de_ambito

    tool = {"grounding": {"ambito_texto": "Ámbito: Mundo E, septiembre de 2026."}}
    assert (
        anexo_de_ambito("Vendiste 2,711 unidades.", tool)
        == "\n\nÁmbito: Mundo E, septiembre de 2026."
    )
    assert (
        anexo_de_ambito("Vendiste.\n\nÁmbito: Mundo E, septiembre de 2026.", tool)
        is None
    )
    assert anexo_de_ambito("Hola", None) is None
    assert anexo_de_ambito("Hola", {"grounding": {}}) is None


@pytest.mark.unit
def test_contenido_con_ambito_en_la_respuesta_no_streaming():
    from types import SimpleNamespace

    from src.services.streaming.function_calling import respuesta_con_ambito

    tool = {"grounding": {"ambito_texto": "Ámbito: Mundo E."}}
    r = SimpleNamespace(choices=[{"message": {"content": "Texto"}}])
    respuesta_con_ambito(r, tool)
    assert r.choices[0]["message"]["content"] == "Texto\n\nÁmbito: Mundo E."
    respuesta_con_ambito(r, tool)
    assert r.choices[0]["message"]["content"].count("Ámbito:") == 1
    obj = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="Otro"))]
    )
    respuesta_con_ambito(obj, tool)
    assert obj.choices[0].message.content == "Otro\n\nÁmbito: Mundo E."


# SIM-24 (2026-11-08): "no no, de todo el súper, no nomás refresco" quedó 2 de
# 3 veces sin tool_calls aun con el reintento. Ante una corrección en un
# seguimiento, el host llama la tool de datos solo con las palabras del
# usuario; el plugin completa desde su memoria de la conversación.
_SCHEMA_DATOS = [
    {
        "type": "function",
        "function": {
            "name": "retail_analytics",
            "parameters": {
                "properties": {
                    "metric_or_query": {},
                    "pregunta_usuario": {},
                    "contexto_usuario": {},
                    "contexto_asistente": {},
                }
            },
        },
    },
    {"type": "function", "function": {"name": "get_presets", "parameters": {}}},
]

_CORRECCION = [
    {"role": "user", "content": "cuáles refrescos se vendieron más?"},
    {"role": "assistant", "content": "Top 10 refrescos: 1. Coca-Cola 472 u..."},
    {"role": "user", "content": "no no, de todo el súper, no nomás refresco"},
]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_correccion_sin_tool_calls_fuerza_la_tool_de_datos():
    analytics = {"metric_name": "venta_hora", "series": [{"name": "x", "points": [1]}]}
    provider = MagicMock()
    provider.tool_schemas = AsyncMock(return_value=_SCHEMA_DATOS)
    provider.call = AsyncMock(return_value=analytics)
    saptiva_client = MagicMock()
    saptiva_client.chat_completion = AsyncMock(
        side_effect=[
            _decide_response(tool_calls=None),
            _decide_response(tool_calls=None),
        ]
    )

    mensajes, resultado, status = await FunctionCallingOrchestrator(
        provider=provider
    ).augment(saptiva_client, list(_CORRECCION), model="turbo")

    assert status == "ok" and resultado == analytics
    assert saptiva_client.chat_completion.await_count == 2
    nombre, args = provider.call.await_args.args
    assert nombre == "retail_analytics"
    assert "metric_or_query" not in args  # nada del modelo: el plugin completa
    assert args["pregunta_usuario"] == "no no, de todo el súper, no nomás refresco"
    assert args["contexto_asistente"] == ["Top 10 refrescos: 1. Coca-Cola 472 u..."]
    assert mensajes[-1]["role"] == "tool"


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "historial",
    [
        FOLLOW_UP,  # "explícame": no es corrección, sigue siendo conversacional
        [{"role": "user", "content": "no sé qué datos hay"}],  # primer turno
    ],
)
async def test_sin_correccion_o_sin_turno_previo_no_se_fuerza_nada(historial):
    provider = MagicMock()
    provider.tool_schemas = AsyncMock(return_value=_SCHEMA_DATOS)
    provider.call = AsyncMock()
    saptiva_client = MagicMock()
    saptiva_client.chat_completion = AsyncMock(
        return_value=_decide_response(tool_calls=None)
    )

    _, _, status = await FunctionCallingOrchestrator(provider=provider).augment(
        saptiva_client, list(historial), model="turbo"
    )

    assert status == "no_calls"
    provider.call.assert_not_awaited()


@pytest.mark.unit
def test_llamada_forzada_exige_una_sola_tool_de_datos():
    from src.services.streaming.function_calling import llamada_forzada_por_correccion

    assert llamada_forzada_por_correccion("No, en Centro", ["r"], {"a", "b"}) is None
    assert llamada_forzada_por_correccion("tampoco eso", ["r"], {"a"})["name"] == "a"
    assert llamada_forzada_por_correccion("nos fue bien?", ["r"], {"a"}) is None
