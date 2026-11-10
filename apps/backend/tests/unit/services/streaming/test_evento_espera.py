"""
Evento `status` del stream con la tool que eligió el decide.

Equipo (2026-10-21): mientras se prepara la respuesta, la burbuja de espera
cambia de ícono y frase según el tema de la consulta (ventas, ranking,
inventario, riesgo, ayuda). La web solo puede saberlo si el backend avisa en
cuanto el decide elige la tool, antes de ejecutarla y de narrar. El evento
lleva el nombre de la tool y los ids de métrica y dimensión; nunca texto libre
del usuario.
"""

import json
from asyncio import Queue
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.streaming.chat_stream_producer import (
    ChatStreamProducer,
    ProducerContext,
)

MENSAJES_BASE = [
    {"role": "system", "content": "Eres un asistente de retail."},
    {"role": "user", "content": "¿Cuánto vendió cada tienda el último mes?"},
]
NARRACION = "Polanco vendió 782,847 piezas el último mes."
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "retail_analytics",
            "parameters": {"type": "object", "properties": {}},
        },
    }
]


def _settings_fc_on() -> SimpleNamespace:
    return SimpleNamespace(
        retail_advisor_function_calling=True,
        retail_advisor_decide_model=None,
        retail_advisor_direct_narration=False,
        memory_enabled=False,
    )


def _provider_mock() -> MagicMock:
    provider = MagicMock()
    provider.tool_schemas = AsyncMock(return_value=TOOL_SCHEMAS)
    provider.call = AsyncMock(return_value={"metric_name": "venta_hora", "series": []})
    return provider


def _decide(argumentos: dict) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            {
                "message": {
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "function": {
                                "name": "retail_analytics",
                                "arguments": json.dumps(argumentos),
                            },
                        }
                    ]
                }
            }
        ]
    )


async def _eventos_del_stream(argumentos: dict) -> list[dict]:
    async def stream_narracion(*args, **kwargs):
        yield SimpleNamespace(choices=[{"delta": {"content": NARRACION}}])

    saptiva_client = MagicMock()
    saptiva_client.chat_completion = AsyncMock(return_value=_decide(argumentos))
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

    cola: Queue = Queue(maxsize=100)
    producer_ctx = ProducerContext(
        event_queue=cola,
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
        await ChatStreamProducer().produce(producer_ctx)

    eventos = []
    while not cola.empty():
        evento = cola.get_nowait()
        if evento is not None:
            eventos.append(evento)
    return eventos


@pytest.mark.unit
class TestEventoEspera:
    @pytest.mark.asyncio
    async def test_avisa_la_tool_elegida_antes_del_primer_chunk(self):
        eventos = await _eventos_del_stream(
            {"metrica": "venta_hora", "dimension": "tienda", "period": "last_month"}
        )
        tipos = [e["event"] for e in eventos]

        assert "status" in tipos
        assert tipos.index("status") < tipos.index("chunk")
        datos = json.loads(eventos[tipos.index("status")]["data"])
        assert datos == {
            "fase": "consultando",
            "tools": [
                {
                    "tool": "retail_analytics",
                    "metrica": "venta_hora",
                    "dimension": "tienda",
                }
            ],
        }

    @pytest.mark.asyncio
    async def test_no_manda_texto_libre_del_usuario(self):
        eventos = await _eventos_del_stream(
            {
                "metric_or_query": "cuánto vendió Juan Pérez en Polanco",
                "pregunta_usuario": "cuánto vendió Juan Pérez en Polanco",
                "dimension": "lo que más se vendió",
            }
        )
        status = next(e for e in eventos if e["event"] == "status")

        assert "Juan" not in status["data"]
        assert json.loads(status["data"])["tools"] == [
            {"tool": "retail_analytics", "metrica": None, "dimension": None}
        ]

    @pytest.mark.asyncio
    async def test_metric_or_query_con_id_del_catalogo_cuenta_como_metrica(self):
        eventos = await _eventos_del_stream({"metric_or_query": "faltante"})
        status = next(e for e in eventos if e["event"] == "status")

        assert json.loads(status["data"])["tools"][0]["metrica"] == "faltante"

    # Equipo (2026-10-21): "en orden y relacionados con la tarea". Además de la
    # tool elegida, el stream avisa cuando ya llegaron los datos y empieza la
    # redacción, para que la burbuja siga los pasos reales.
    @pytest.mark.asyncio
    async def test_avisa_que_empieza_a_redactar_despues_de_consultar(self):
        eventos = await _eventos_del_stream({"metrica": "venta_hora"})
        status = [json.loads(e["data"]) for e in eventos if e["event"] == "status"]
        tipos = [e["event"] for e in eventos]

        assert [s["fase"] for s in status] == ["consultando", "redactando"]
        assert status[1]["tools"] == status[0]["tools"]
        ultimo_status = max(i for i, t in enumerate(tipos) if t == "status")
        assert ultimo_status < tipos.index("chunk")
