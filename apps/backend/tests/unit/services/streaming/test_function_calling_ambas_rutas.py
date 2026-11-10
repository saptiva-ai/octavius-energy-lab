"""
Paridad de function-calling entre las DOS rutas del chat.

Card 2026-07-23__TASK__function-calling-fuera-del-streaming: las tools del
plugin de dominio deben ejecutarse igual con y sin streaming. El mismo
escenario (pill de retail encendido, el LLM decide llamar la tool y luego
narra) debe producir en ambas rutas:
- el `retail_analytics` crudo del plugin, y
- una narración basada en los mensajes `tool` (grounding con las cifras).

También fija el contrato de los avisos anti-alucinación del paso compartido
`augmentar_con_tools_de_dominio`: pill apagado → DATA_TOOL_OFF_NOTICE; infra
caída → TOOLS_UNAVAILABLE_NOTICE. Un fallo nunca es silencioso.
"""

import json
from asyncio import Queue
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.chat_service import ChatService
from src.services.streaming.chat_stream_producer import (
    ChatStreamProducer,
    ProducerContext,
)
from src.services.streaming.function_calling import (
    DATA_TOOL_OFF_NOTICE,
    TOOLS_UNAVAILABLE_NOTICE,
    augmentar_con_tools_de_dominio,
)

ANALYTICS = {
    "metric_name": "ventas_totales",
    "series": [
        {
            "name": "Tienda Centro",
            "points": [
                {"x": "2026-07-01", "y": 1234.5},
                {"x": "2026-07-02", "y": 987.0},
            ],
        }
    ],
}

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "retail_analytics",
            "parameters": {"type": "object", "properties": {}},
        },
    }
]

NARRACION = "Las ventas de Tienda Centro fueron 1234.5 y 987.0 en el periodo."

MENSAJES_BASE = [
    {"role": "system", "content": "Eres un asistente de retail."},
    {"role": "user", "content": "¿Cómo van las ventas de Tienda Centro?"},
]


def _respuesta_decide_con_tool_call():
    """Respuesta OpenAI-style del step decide: el LLM pide la tool."""
    return SimpleNamespace(
        choices=[
            {
                "message": {
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "function": {
                                "name": "retail_analytics",
                                "arguments": json.dumps(
                                    {"metric_or_query": "ventas Tienda Centro"}
                                ),
                            },
                        }
                    ]
                }
            }
        ]
    )


def _respuesta_narracion():
    return SimpleNamespace(choices=[{"message": {"content": NARRACION}}])


def _settings_fc_on(directa: bool = False):
    # `directa`: el atajo que publica el texto del plugin sin narrador. Apagado
    # por omisión desde el 2026-10-15 (el chat siempre explica con el LLM); las
    # pruebas del atajo lo encienden.
    return SimpleNamespace(
        retail_advisor_function_calling=True,
        retail_advisor_decide_model=None,
        retail_advisor_direct_narration=directa,
        memory_enabled=False,
    )


def _provider_mock():
    provider = MagicMock()
    provider.tool_schemas = AsyncMock(return_value=TOOL_SCHEMAS)
    provider.call = AsyncMock(return_value=ANALYTICS)
    return provider


def _tiene_tool_result_con_cifras(messages):
    """¿Los mensajes de la narración incluyen el resultado de la tool?"""
    return any(
        m.get("role") == "tool" and "1234.5" in m.get("content", "") for m in messages
    )


@pytest.mark.unit
class TestParidadAmbasRutas:
    """El mismo escenario produce retail_analytics y grounding en ambas rutas."""

    @pytest.mark.asyncio
    async def test_ruta_streaming_ejecuta_tool_y_narra(self):
        narracion_recibio = {}

        async def stream_narracion(*args, **kwargs):
            narracion_recibio["messages"] = kwargs.get("messages") or args[0]
            for chunk in [NARRACION]:
                yield SimpleNamespace(choices=[{"delta": {"content": chunk}}])

        saptiva_client = MagicMock()
        saptiva_client.chat_completion = AsyncMock(
            return_value=_respuesta_decide_con_tool_call()
        )
        saptiva_client.chat_completion_stream = stream_narracion

        chat_service = AsyncMock()
        chat_service.settings = _settings_fc_on()
        chat_service.build_message_context_with_memory = AsyncMock(
            return_value=list(MENSAJES_BASE)
        )

        context = MagicMock()
        context.model = "gemma-4-26b"
        context.user_id = "user-1"
        context.temperature = 0.7
        context.message = MENSAJES_BASE[-1]["content"]
        context.document_ids = []
        context.tools_enabled = {"retail_advisor": True}

        chat_session = MagicMock()
        chat_session.id = "chat-1"
        chat_session.tools_enabled = {}

        user_message = MagicMock()
        user_message.id = "msg-1"

        producer_ctx = ProducerContext(
            event_queue=Queue(maxsize=100),
            context=context,
            chat_session=chat_session,
            user_message=user_message,
            saptiva_client=saptiva_client,
            chat_service=chat_service,
            system_prompt=MENSAJES_BASE[0]["content"],
            model_params={"temperature": 0.7, "max_tokens": 3000},
        )

        with patch(
            "src.services.streaming.function_calling.DomainToolProvider",
            return_value=_provider_mock(),
        ):
            result = await ChatStreamProducer().produce(producer_ctx)

        assert result.completed is True
        assert result.retail_analytics == ANALYTICS
        assert "1234.5" in result.full_response
        # La narración corrió sobre los mensajes aumentados (grounding real).
        assert _tiene_tool_result_con_cifras(narracion_recibio["messages"])

    @pytest.mark.asyncio
    async def test_ruta_no_streaming_ejecuta_la_misma_tool_y_narra(self):
        llamadas = []

        async def chat_completion(*args, **kwargs):
            llamadas.append(kwargs)
            if kwargs.get("tools"):
                return _respuesta_decide_con_tool_call()
            return _respuesta_narracion()

        saptiva_client = MagicMock()
        saptiva_client.chat_completion = AsyncMock(side_effect=chat_completion)

        service = ChatService(_settings_fc_on(), saptiva_client=saptiva_client)

        with (
            patch(
                "src.services.chat_service.build_payload",
                new_callable=AsyncMock,
                return_value=(
                    {
                        "messages": list(MENSAJES_BASE),
                        "temperature": 0.7,
                        "max_tokens": 3000,
                        # Pseudo-tool legacy que build_payload inyecta con el
                        # pill encendido; la narración NO debe ofrecerlo.
                        "tools": [
                            {
                                "type": "function",
                                "function": {
                                    "name": "retail_advisor",
                                    "parameters": {"type": "object"},
                                },
                            }
                        ],
                    },
                    {"request_id": "req-1", "system_hash": "hash"},
                ),
            ),
            patch(
                "src.services.streaming.function_calling.DomainToolProvider",
                return_value=_provider_mock(),
            ),
            patch("src.services.chat_service.trace_span"),
        ):
            resultado = await service.process_with_saptiva(
                message=MENSAJES_BASE[-1]["content"],
                model="gemma-4-26b",
                user_id="user-1",
                chat_id="",
                # Mismo merge que streaming: el pill vive en la SESIÓN
                # (follow-ups llegan con tools_enabled vacío en el request).
                tools_enabled={},
                session_tools_enabled={"retail_advisor": True},
            )

        # Mismo artefacto crudo que la ruta de streaming.
        assert resultado["retail_analytics"] == ANALYTICS
        assert resultado["function_calling_status"] == "ok"

        # La narración (llamada SIN tools) recibió el resultado de la tool y
        # devolvió las cifras.
        narracion = [kw for kw in llamadas if not kw.get("tools")]
        assert len(narracion) == 1
        # Paridad con streaming: la narración NO ofrece el pseudo-tool legacy
        # del payload — con tools, modelos ansiosos (qwen3.6) responden con
        # otro tool_call y contenido vacío en vez de narrar (visto en vivo).
        assert narracion[0]["tools"] is None
        assert _tiene_tool_result_con_cifras(narracion[0]["messages"])
        contenido = resultado["response"].choices[0]["message"]["content"]
        assert "1234.5" in contenido

    @pytest.mark.asyncio
    async def test_ruta_no_streaming_pasa_el_usuario_para_resolver_el_ambito(self):
        """Paridad T3: la ruta que usa la web (POST /api/chat) debe entregar el
        `user_id` al paso compartido; sin él el ámbito del perfil no llegaba a
        las tools y el gerente recibía `tienda_requerida` (visto 2026-09-02)."""
        saptiva_client = MagicMock()
        saptiva_client.chat_completion = AsyncMock(return_value=_respuesta_narracion())
        service = ChatService(_settings_fc_on(), saptiva_client=saptiva_client)
        augmentar = AsyncMock(return_value=(list(MENSAJES_BASE), None, "no_calls"))

        with (
            patch(
                "src.services.chat_service.build_payload",
                new_callable=AsyncMock,
                return_value=(
                    {"messages": list(MENSAJES_BASE), "temperature": 0.7},
                    {"request_id": "req-1", "system_hash": "hash"},
                ),
            ),
            patch(
                "src.services.streaming.function_calling.augmentar_con_tools_de_dominio",
                augmentar,
            ),
            patch("src.services.chat_service.trace_span"),
        ):
            await service.process_with_saptiva(
                message=MENSAJES_BASE[-1]["content"],
                model="gemma-4-26b",
                user_id="user-gerente",
                chat_id="",
                tools_enabled={"retail_advisor": True},
            )

        assert augmentar.await_args.kwargs["user_id"] == "user-gerente"


ANALYTICS_CON_TEXTO = {
    **ANALYTICS,
    "response_text": "Tienda Centro vendió 1234.5 y 987.0 unidades en el periodo.",
}


def _producer_ctx(saptiva_client, chat_service):
    context = MagicMock()
    context.model = "gemma-4-26b"
    context.user_id = "user-1"
    context.temperature = 0.7
    context.message = MENSAJES_BASE[-1]["content"]
    context.document_ids = []
    context.tools_enabled = {"retail_advisor": True}

    chat_session = MagicMock()
    chat_session.id = "chat-1"
    chat_session.tools_enabled = {}

    user_message = MagicMock()
    user_message.id = "msg-1"

    return ProducerContext(
        event_queue=Queue(maxsize=100),
        context=context,
        chat_session=chat_session,
        user_message=user_message,
        saptiva_client=saptiva_client,
        chat_service=chat_service,
        system_prompt=MENSAJES_BASE[0]["content"],
        model_params={"temperature": 0.7, "max_tokens": 3000},
    )


@pytest.mark.unit
class TestNarracionDirectaAmbasRutas:
    """Card latencia-chat-retail-prediccion: con UNA tool de datos y
    `response_text` confiable, ninguna ruta re-narra con el LLM. La metadata
    (`retail_analytics`) y el texto emitido salen del contrato genérico."""

    @pytest.mark.asyncio
    async def test_streaming_emite_response_text_sin_segunda_llamada_llm(self):
        saptiva_client = MagicMock()
        saptiva_client.chat_completion = AsyncMock(
            return_value=_respuesta_decide_con_tool_call()
        )
        # Si la ruta intenta narrar por stream, el test debe fallar.
        saptiva_client.chat_completion_stream = MagicMock(
            side_effect=AssertionError("narración LLM redundante")
        )

        chat_service = AsyncMock()
        chat_service.settings = _settings_fc_on(directa=True)
        chat_service.build_message_context_with_memory = AsyncMock(
            return_value=list(MENSAJES_BASE)
        )

        provider = _provider_mock()
        provider.call = AsyncMock(return_value=ANALYTICS_CON_TEXTO)
        producer_ctx = _producer_ctx(saptiva_client, chat_service)

        with patch(
            "src.services.streaming.function_calling.DomainToolProvider",
            return_value=provider,
        ):
            result = await ChatStreamProducer().produce(producer_ctx)

        assert result.completed is True
        assert result.retail_analytics == ANALYTICS_CON_TEXTO
        assert result.full_response == ANALYTICS_CON_TEXTO["response_text"]
        assert result.path_taken == "tool_direct"
        saptiva_client.chat_completion_stream.assert_not_called()

        # El texto llegó al consumer como chunks normales (contrato SSE).
        eventos = []
        while not producer_ctx.event_queue.empty():
            eventos.append(producer_ctx.event_queue.get_nowait())
        chunks = [e for e in eventos if e and e.get("event") == "chunk"]
        texto = "".join(json.loads(c["data"])["content"] for c in chunks)
        assert texto == ANALYTICS_CON_TEXTO["response_text"]
        assert eventos[-1] is None  # señal de fin para el consumer

    @pytest.mark.asyncio
    async def test_no_streaming_responde_con_el_texto_del_plugin_en_una_llamada(self):
        llamadas = []

        async def chat_completion(*args, **kwargs):
            llamadas.append(kwargs)
            if kwargs.get("tools"):
                return _respuesta_decide_con_tool_call()
            raise AssertionError("narración LLM redundante")

        saptiva_client = MagicMock()
        saptiva_client.chat_completion = AsyncMock(side_effect=chat_completion)

        provider = _provider_mock()
        provider.call = AsyncMock(return_value=ANALYTICS_CON_TEXTO)

        service = ChatService(
            _settings_fc_on(directa=True), saptiva_client=saptiva_client
        )

        with (
            patch(
                "src.services.chat_service.build_payload",
                new_callable=AsyncMock,
                return_value=(
                    {
                        "messages": list(MENSAJES_BASE),
                        "temperature": 0.7,
                        "max_tokens": 3000,
                    },
                    {"request_id": "req-1", "system_hash": "hash"},
                ),
            ),
            patch(
                "src.services.streaming.function_calling.DomainToolProvider",
                return_value=provider,
            ),
            patch("src.services.chat_service.trace_span"),
        ):
            resultado = await service.process_with_saptiva(
                message=MENSAJES_BASE[-1]["content"],
                model="gemma-4-26b",
                user_id="user-1",
                chat_id="",
                tools_enabled={},
                session_tools_enabled={"retail_advisor": True},
            )

        assert resultado["retail_analytics"] == ANALYTICS_CON_TEXTO
        assert resultado["function_calling_status"] == "ok"
        # Una sola llamada al LLM: el decide. Cero narración redundante.
        assert len(llamadas) == 1 and llamadas[0].get("tools")
        contenido = resultado["response"].choices[0]["message"]["content"]
        assert contenido == ANALYTICS_CON_TEXTO["response_text"]


@pytest.mark.unit
class TestAvisosAntiAlucinacion:
    """Contrato del paso compartido: un fallo nunca es silencioso."""

    @pytest.mark.asyncio
    async def test_pill_apagado_inyecta_aviso_de_tool_desactivada(self):
        mensajes, analytics, status = await augmentar_con_tools_de_dominio(
            settings=_settings_fc_on(),
            saptiva_client=MagicMock(),
            messages=list(MENSAJES_BASE),
            model="gemma-4-26b",
            request_tools={},
            session_tools={},
        )

        assert status == "off"
        assert analytics is None
        assert mensajes[-1] == DATA_TOOL_OFF_NOTICE

    @pytest.mark.asyncio
    async def test_infra_caida_inyecta_aviso_de_tools_no_disponibles(self):
        provider = MagicMock()
        # Discovery vacío = plugin caído (el provider se traga el error).
        provider.tool_schemas = AsyncMock(return_value=[])

        with patch(
            "src.services.streaming.function_calling.DomainToolProvider",
            return_value=provider,
        ):
            mensajes, analytics, status = await augmentar_con_tools_de_dominio(
                settings=_settings_fc_on(),
                saptiva_client=MagicMock(),
                messages=list(MENSAJES_BASE),
                model="gemma-4-26b",
                request_tools={"retail_advisor": True},
                session_tools={},
            )

        assert status == "failed"
        assert analytics is None
        assert mensajes[-1] == TOOLS_UNAVAILABLE_NOTICE

    @pytest.mark.asyncio
    async def test_deployment_sin_function_calling_no_toca_mensajes(self):
        mensajes, analytics, status = await augmentar_con_tools_de_dominio(
            settings=SimpleNamespace(retail_advisor_function_calling=False),
            saptiva_client=MagicMock(),
            messages=list(MENSAJES_BASE),
            model="gemma-4-26b",
            request_tools={"retail_advisor": True},
            session_tools={},
        )

        assert status == "disabled"
        assert analytics is None
        assert mensajes == MENSAJES_BASE
