"""P0-8 de la auditoría (9 de octubre): los logs INFO de producción no llevan
prompts, resultados de tools, perfil del usuario ni contraseñas."""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from structlog.testing import capture_logs

from src.services.saptiva_client import SaptivaClient

SECRETO = "contenido-del-usuario-que-no-debe-loguearse"


@pytest.fixture
def saptiva_client():
    """Cliente real con HTTP y settings simulados (como test_saptiva_client)."""
    ajustes = Mock(
        saptiva_base_url="https://api.saptiva.test",
        saptiva_api_key="YOUR_API_KEY_HERE",
        saptiva_timeout=30,
        saptiva_max_retries=3,
        enable_model_system_prompt=True,
    )
    with (
        patch("src.services.saptiva_client.get_settings", return_value=ajustes),
        patch("src.services.saptiva_client.httpx.AsyncClient") as http,
        patch.dict(
            "os.environ",
            {"SAPTIVA_FORCE_MOCK": "0", "SAPTIVA_ALLOW_MOCK_FALLBACK": "0"},
        ),
    ):
        http.return_value = AsyncMock(headers={}, aclose=AsyncMock())
        cliente = SaptivaClient()
        cliente.force_mock = cliente.mock_mode = cliente.allow_mock_fallback = False
        yield cliente


@pytest.mark.asyncio
async def test_peticion_al_llm_no_loguea_el_payload(saptiva_client):
    respuesta = Mock(status_code=200, raise_for_status=Mock())
    respuesta.json = Mock(
        return_value={
            "id": "x",
            "object": "chat.completion",
            "model": "m",
            "choices": [
                {"message": {"role": "assistant", "content": "ok"}, "index": 0}
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
    )
    saptiva_client.client.request = AsyncMock(return_value=respuesta)
    with capture_logs() as eventos:
        await saptiva_client.chat_completion(
            [
                {"role": "system", "content": f"perfil: {SECRETO}"},
                {"role": "user", "content": SECRETO},
            ],
            model="SAPTIVA_CORTEX",
        )
    peticion = [e for e in eventos if e["event"] == "Making SAPTIVA API request"]
    assert peticion and peticion[0]["log_level"] == "info"
    assert "request_payload" not in peticion[0]
    assert peticion[0]["message_count"] == 2
    assert SECRETO not in repr(eventos)


@pytest.mark.asyncio
async def test_url_de_redis_se_loguea_sin_contrasena():
    import src.services.cache_service as cache_module

    ajustes = MagicMock()
    ajustes.redis_url = "redis://default:YOUR_PASSWORD_HERE@localhost:6379/0"
    cache_module._redis_client = None
    with (
        patch.object(cache_module, "get_settings", return_value=ajustes),
        patch.object(cache_module.redis, "from_url", return_value=AsyncMock()),
        capture_logs() as eventos,
    ):
        await cache_module.get_redis_client()
    cache_module._redis_client = None
    assert "YOUR_PASSWORD_HERE" not in repr(eventos)
    assert any("localhost:6379/0" in repr(e) for e in eventos)
