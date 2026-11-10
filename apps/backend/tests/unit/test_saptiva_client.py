"""
Comprehensive tests for services/saptiva_client.py - SAPTIVA API client

Coverage:
- Client initialization: API key, headers, timeouts, HTTP/2
- Model mapping: Internal names → API names
- Retry logic: Exponential backoff, max retries
- Chat completion: Success, errors, API key validation
- Chat streaming: AsyncGenerator, SSE parsing
- Unified interface: chat_completion_or_stream for both modes
- Health check: API availability
- Payload building: Messages, system prompts, tools
- Singleton pattern: get_saptiva_client
- Error handling: HTTP errors, timeouts, invalid responses
"""

import pytest
import json
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch, MagicMock
import httpx

from src.services.saptiva_client import (
    SaptivaClient,
    SaptivaMessage,
    SaptivaRequest,
    SaptivaResponse,
    SaptivaStreamChunk,
    get_saptiva_client,
    close_saptiva_client,
    build_messages,
    build_payload,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_settings():
    """Mock settings for SAPTIVA client."""
    with patch("src.services.saptiva_client.get_settings") as mock:
        settings = Mock()
        settings.saptiva_base_url = "https://api.saptiva.test"
        settings.saptiva_api_key = "test-api-key-123"
        settings.saptiva_timeout = 30
        settings.saptiva_max_retries = 3
        settings.enable_model_system_prompt = True
        mock.return_value = settings
        yield settings


@pytest.fixture
def mock_httpx_client():
    """Mock httpx.AsyncClient."""
    client = AsyncMock(spec=httpx.AsyncClient)
    client.headers = {}
    client.request = AsyncMock()
    client.stream = AsyncMock()
    client.get = AsyncMock()
    client.aclose = AsyncMock()
    return client


@pytest.fixture
def saptiva_client(mock_settings):
    """Create SaptivaClient instance with mocked dependencies."""
    with patch("src.services.saptiva_client.httpx.AsyncClient") as MockAsyncClient:
        mock_client = AsyncMock()
        mock_client.headers = {}
        mock_client.aclose = AsyncMock()
        MockAsyncClient.return_value = mock_client

        # Disable mock mode for tests - we want to test HTTP behavior
        with patch.dict(
            "os.environ",
            {"SAPTIVA_FORCE_MOCK": "0", "SAPTIVA_ALLOW_MOCK_FALLBACK": "0"},
        ):
            client = SaptivaClient()
            # Explicitly disable mock mode
            client.force_mock = False
            client.mock_mode = False
            client.allow_mock_fallback = False
            yield client


# ============================================================================
# CLIENT INITIALIZATION
# ============================================================================


class TestClientInitialization:
    """Test SaptivaClient initialization."""

    def test_client_initialization_sets_api_key(self, mock_settings):
        """Should set API key in Authorization header."""
        with patch("src.services.saptiva_client.httpx.AsyncClient") as MockAsyncClient:
            mock_client = AsyncMock()
            mock_client.headers = {}
            MockAsyncClient.return_value = mock_client

            client = SaptivaClient()

            assert client.api_key == "test-api-key-123"
            assert "Authorization" in mock_client.headers
            assert mock_client.headers["Authorization"] == "Bearer test-api-key-123"

    def test_client_initialization_without_api_key(self):
        """Should initialize without API key if not configured."""
        with patch("src.services.saptiva_client.get_settings") as mock_get_settings:
            settings = Mock()
            settings.saptiva_base_url = "https://api.saptiva.test"
            settings.saptiva_api_key = ""
            settings.saptiva_timeout = 30
            settings.saptiva_max_retries = 3
            mock_get_settings.return_value = settings

            with patch(
                "src.services.saptiva_client.httpx.AsyncClient"
            ) as MockAsyncClient:
                mock_client = AsyncMock()
                mock_client.headers = {}
                MockAsyncClient.return_value = mock_client

                client = SaptivaClient()

                assert client.api_key == ""
                assert "Authorization" not in mock_client.headers

    def test_set_api_key_updates_headers(self, saptiva_client):
        """Should update Authorization header when API key is set."""
        saptiva_client.set_api_key("new-api-key-456")

        assert saptiva_client.api_key == "new-api-key-456"
        assert (
            saptiva_client.client.headers["Authorization"] == "Bearer new-api-key-456"
        )

    def test_set_api_key_removes_header_when_empty(self, saptiva_client):
        """Should remove Authorization header when API key is cleared."""
        saptiva_client.client.headers["Authorization"] = "Bearer old-key"

        saptiva_client.set_api_key("")

        assert saptiva_client.api_key == ""
        assert "Authorization" not in saptiva_client.client.headers


# ============================================================================
# MODEL MAPPING
# ============================================================================


class TestModelMapping:
    """Test model name mapping."""

    def test_get_model_name_maps_internal_names(self, saptiva_client):
        """Should map internal model names to API names."""
        assert saptiva_client._get_model_name("SAPTIVA_CORTEX") == "Saptiva Cortex"
        assert saptiva_client._get_model_name("SAPTIVA_TURBO") == "Saptiva Turbo"
        assert saptiva_client._get_model_name("SAPTIVA_GUARD") == "Saptiva Guard"

    def test_get_model_name_handles_lowercase(self, saptiva_client):
        """Should handle lowercase aliases."""
        assert saptiva_client._get_model_name("saptiva-cortex") == "Saptiva Cortex"
        assert saptiva_client._get_model_name("saptiva-turbo") == "Saptiva Turbo"

    def test_get_model_name_returns_original_if_not_mapped(self, saptiva_client):
        """Should return original name if not in mapping."""
        assert saptiva_client._get_model_name("Unknown Model") == "Unknown Model"


# ============================================================================
# RETRY LOGIC
# ============================================================================


class TestRetryLogic:
    """Test HTTP retry logic."""

    @pytest.mark.asyncio
    async def test_make_request_success_first_try(self, saptiva_client):
        """Should succeed on first try."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()

        saptiva_client.client.request = AsyncMock(return_value=mock_response)

        response = await saptiva_client._make_request("POST", "/v1/test")

        assert response.status_code == 200
        saptiva_client.client.request.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_make_request_retries_on_http_error(self, saptiva_client):
        """Should retry on HTTP errors."""
        # Fail twice, succeed on third attempt
        saptiva_client.client.request = AsyncMock(
            side_effect=[
                httpx.HTTPError("Connection failed"),
                httpx.HTTPError("Timeout"),
                Mock(status_code=200, raise_for_status=Mock()),
            ]
        )

        with patch("asyncio.sleep", return_value=None):  # Skip actual sleep
            response = await saptiva_client._make_request("POST", "/v1/test")

        assert response.status_code == 200
        assert saptiva_client.client.request.await_count == 3

    @pytest.mark.asyncio
    async def test_make_request_raises_after_max_retries(self, saptiva_client):
        """Should raise after exhausting retries."""
        saptiva_client.client.request = AsyncMock(
            side_effect=httpx.HTTPError("Persistent error")
        )

        with patch("asyncio.sleep", return_value=None):
            with pytest.raises(httpx.HTTPError) as exc_info:
                await saptiva_client._make_request("POST", "/v1/test")

        assert "Persistent error" in str(exc_info.value)
        # Should attempt: initial + max_retries(3) = 4 total attempts
        assert saptiva_client.client.request.await_count == 4

    @pytest.mark.asyncio
    async def test_make_request_exponential_backoff(self, saptiva_client):
        """Should use exponential backoff between retries."""
        saptiva_client.client.request = AsyncMock(
            side_effect=[
                httpx.HTTPError("Error 1"),
                httpx.HTTPError("Error 2"),
                Mock(status_code=200, raise_for_status=Mock()),
            ]
        )

        sleep_times = []

        async def mock_sleep(duration):
            sleep_times.append(duration)

        with patch("asyncio.sleep", side_effect=mock_sleep):
            await saptiva_client._make_request("POST", "/v1/test")

        # Should have exponential backoff: min(2^0, 10), min(2^1, 10)
        assert len(sleep_times) == 2
        assert sleep_times[0] == 1  # 2^0
        assert sleep_times[1] == 2  # 2^1


# ============================================================================
# CHAT COMPLETION
# ============================================================================


class TestChatCompletion:
    """Test chat completion methods."""

    @pytest.mark.asyncio
    async def test_chat_completion_success(self, saptiva_client):
        """Should complete chat successfully."""
        mock_response = Mock()
        mock_response.status_code = 200  # Required for response validation
        mock_response.json = Mock(
            return_value={
                "id": "chatcmpl-123",
                "object": "chat.completion",
                "model": "Saptiva Cortex",
                "choices": [
                    {"message": {"role": "assistant", "content": "Hello!"}, "index": 0}
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                },
            }
        )
        mock_response.raise_for_status = Mock()

        saptiva_client.client.request = AsyncMock(return_value=mock_response)

        messages = [{"role": "user", "content": "Hi"}]
        response = await saptiva_client.chat_completion(
            messages, model="SAPTIVA_CORTEX"
        )

        assert isinstance(response, SaptivaResponse)
        assert response.id == "chatcmpl-123"
        assert response.model == "Saptiva Cortex"
        assert len(response.choices) == 1

    @pytest.mark.asyncio
    async def test_chat_completion_requires_api_key(self):
        """Should raise error if API key not configured."""
        with patch("src.services.saptiva_client.get_settings") as mock_get_settings:
            settings = Mock()
            settings.saptiva_base_url = "https://api.saptiva.test"
            settings.saptiva_api_key = ""
            settings.saptiva_timeout = 30
            settings.saptiva_max_retries = 3
            mock_get_settings.return_value = settings

            # Disable mock mode so it raises ValueError instead of falling back
            with patch.dict(
                "os.environ",
                {"SAPTIVA_FORCE_MOCK": "0", "SAPTIVA_ALLOW_MOCK_FALLBACK": "0"},
            ):
                with patch("src.services.saptiva_client.httpx.AsyncClient"):
                    client = SaptivaClient()
                    # Explicitly disable mock fallback
                    client.allow_mock_fallback = False
                    client.force_mock = False
                    client.mock_mode = False

                    messages = [{"role": "user", "content": "Hi"}]

                    with pytest.raises(ValueError) as exc_info:
                        await client.chat_completion(messages)

                    assert "API key is required" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_chat_completion_with_custom_params(self, saptiva_client):
        """Should pass custom parameters correctly."""
        mock_response = Mock()
        mock_response.status_code = 200  # Required for response validation
        mock_response.json = Mock(
            return_value={
                "id": "chatcmpl-123",
                "object": "chat.completion",
                "model": "Saptiva Turbo",
                "choices": [{"message": {"content": "Response"}, "index": 0}],
            }
        )
        mock_response.raise_for_status = Mock()

        saptiva_client.client.request = AsyncMock(return_value=mock_response)

        messages = [{"role": "user", "content": "Test"}]
        await saptiva_client.chat_completion(
            messages, model="SAPTIVA_TURBO", temperature=0.9, max_tokens=2000
        )

        # Check that request was made with correct parameters
        call_args = saptiva_client.client.request.call_args
        request_data = call_args.kwargs["json"]

        assert request_data["model"] == "Saptiva Turbo"
        assert request_data["temperature"] == 0.9
        assert request_data["max_tokens"] == 2000

    @pytest.mark.asyncio
    async def test_chat_completion_handles_api_error(self, saptiva_client):
        """Should propagate API errors."""
        saptiva_client.client.request = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "API error", request=Mock(), response=Mock(status_code=500)
            )
        )

        messages = [{"role": "user", "content": "Test"}]

        with pytest.raises(httpx.HTTPStatusError):
            await saptiva_client.chat_completion(messages)


# ============================================================================
# CHAT STREAMING
# ============================================================================


class TestChatStreaming:
    """Test chat completion streaming."""

    @pytest.mark.asyncio
    async def test_chat_completion_stream_yields_chunks(self, saptiva_client):
        """Should yield streaming chunks."""
        # Mock SSE stream data
        sse_lines = [
            "data: "
            + json.dumps(
                {
                    "id": "chatcmpl-123",
                    "object": "chat.completion.chunk",
                    "model": "Saptiva Cortex",
                    "choices": [{"delta": {"content": "Hello"}, "index": 0}],
                }
            ),
            "data: "
            + json.dumps(
                {
                    "id": "chatcmpl-123",
                    "object": "chat.completion.chunk",
                    "model": "Saptiva Cortex",
                    "choices": [{"delta": {"content": " world"}, "index": 0}],
                }
            ),
            "data: [DONE]",
        ]

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()

        async def mock_aiter_lines():
            for line in sse_lines:
                yield line

        mock_response.aiter_lines = mock_aiter_lines

        mock_stream_context = AsyncMock()
        mock_stream_context.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_context.__aexit__ = AsyncMock(return_value=None)

        saptiva_client.client.stream = Mock(return_value=mock_stream_context)

        messages = [{"role": "user", "content": "Hi"}]

        chunks = []
        async for chunk in saptiva_client.chat_completion_stream(messages):
            chunks.append(chunk)

        assert len(chunks) == 2
        assert all(isinstance(chunk, SaptivaStreamChunk) for chunk in chunks)

    @pytest.mark.asyncio
    async def test_chat_completion_stream_requires_api_key(self):
        """Should raise error if API key not configured."""
        with patch("src.services.saptiva_client.get_settings") as mock_get_settings:
            settings = Mock()
            settings.saptiva_base_url = "https://api.saptiva.test"
            settings.saptiva_api_key = ""
            settings.saptiva_timeout = 30
            settings.saptiva_max_retries = 3
            mock_get_settings.return_value = settings

            # Disable mock mode so it raises ValueError instead of falling back
            with patch.dict(
                "os.environ",
                {"SAPTIVA_FORCE_MOCK": "0", "SAPTIVA_ALLOW_MOCK_FALLBACK": "0"},
            ):
                with patch("src.services.saptiva_client.httpx.AsyncClient"):
                    client = SaptivaClient()
                    # Explicitly disable mock fallback
                    client.allow_mock_fallback = False
                    client.force_mock = False
                    client.mock_mode = False

                    messages = [{"role": "user", "content": "Hi"}]

                    with pytest.raises(ValueError) as exc_info:
                        async for _ in client.chat_completion_stream(messages):
                            pass

                    assert "API key is required" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_chat_completion_stream_handles_invalid_json(self, saptiva_client):
        """Should skip invalid JSON chunks."""
        sse_lines = [
            "data: invalid-json",
            "data: "
            + json.dumps(
                {
                    "id": "chatcmpl-123",
                    "object": "chat.completion.chunk",
                    "model": "Saptiva Cortex",
                    "choices": [{"delta": {"content": "Valid"}, "index": 0}],
                }
            ),
            "data: [DONE]",
        ]

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()

        async def mock_aiter_lines():
            for line in sse_lines:
                yield line

        mock_response.aiter_lines = mock_aiter_lines

        mock_stream_context = AsyncMock()
        mock_stream_context.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_context.__aexit__ = AsyncMock(return_value=None)

        saptiva_client.client.stream = Mock(return_value=mock_stream_context)

        messages = [{"role": "user", "content": "Test"}]

        chunks = []
        async for chunk in saptiva_client.chat_completion_stream(messages):
            chunks.append(chunk)

        # Should only get the valid chunk
        assert len(chunks) == 1


# ============================================================================
# UNIFIED INTERFACE
# ============================================================================


class TestUnifiedInterface:
    """Test chat_completion_or_stream unified interface."""

    @pytest.mark.asyncio
    async def test_unified_interface_non_streaming(self, saptiva_client):
        """Should yield single final response when stream=False."""
        mock_response = Mock()
        mock_response.status_code = 200  # Required for response validation
        mock_response.json = Mock(
            return_value={
                "id": "chatcmpl-123",
                "object": "chat.completion",
                "model": "Saptiva Cortex",
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "Final response"},
                        "index": 0,
                    }
                ],
            }
        )
        mock_response.raise_for_status = Mock()

        saptiva_client.client.request = AsyncMock(return_value=mock_response)

        messages = [{"role": "user", "content": "Test"}]

        results = []
        async for chunk in saptiva_client.chat_completion_or_stream(
            messages, stream=False
        ):
            results.append(chunk)

        assert len(results) == 1
        assert results[0]["type"] == "final"
        assert results[0]["content"] == "Final response"
        assert "response" in results[0]

    @pytest.mark.asyncio
    async def test_unified_interface_streaming(self, saptiva_client):
        """Should yield chunks when stream=True."""
        sse_lines = [
            "data: "
            + json.dumps(
                {
                    "id": "chatcmpl-123",
                    "object": "chat.completion.chunk",
                    "model": "Saptiva Cortex",
                    "choices": [{"delta": {"content": "Chunk 1"}, "index": 0}],
                }
            ),
            "data: [DONE]",
        ]

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()

        async def mock_aiter_lines():
            for line in sse_lines:
                yield line

        mock_response.aiter_lines = mock_aiter_lines

        mock_stream_context = AsyncMock()
        mock_stream_context.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_context.__aexit__ = AsyncMock(return_value=None)

        saptiva_client.client.stream = Mock(return_value=mock_stream_context)

        messages = [{"role": "user", "content": "Test"}]

        results = []
        async for chunk in saptiva_client.chat_completion_or_stream(
            messages, stream=True
        ):
            results.append(chunk)

        assert len(results) == 1
        assert results[0]["type"] == "chunk"
        assert "data" in results[0]


# ============================================================================
# HEALTH CHECK
# ============================================================================


class TestHealthCheck:
    """Test health check methods."""

    @pytest.mark.asyncio
    async def test_health_check_success(self, saptiva_client):
        """Should return True if API is available."""
        mock_response = Mock()
        mock_response.status_code = 200

        saptiva_client.client.get = AsyncMock(return_value=mock_response)

        result = await saptiva_client.health_check()

        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self, saptiva_client):
        """Should return False if API is unavailable."""
        saptiva_client.client.get = AsyncMock(
            side_effect=httpx.HTTPError("Connection failed")
        )

        result = await saptiva_client.health_check()

        assert result is False

    @pytest.mark.asyncio
    async def test_health_check_no_api_key(self):
        """Should return False if no API key configured."""
        with patch("src.services.saptiva_client.get_settings") as mock_get_settings:
            settings = Mock()
            settings.saptiva_base_url = "https://api.saptiva.test"
            settings.saptiva_api_key = ""
            settings.saptiva_timeout = 30
            settings.saptiva_max_retries = 3
            mock_get_settings.return_value = settings

            with patch("src.services.saptiva_client.httpx.AsyncClient"):
                client = SaptivaClient()

                result = await client.health_check()

                assert result is False


# ============================================================================
# MESSAGE BUILDING
# ============================================================================


class TestMessageBuilding:
    """Test build_messages helper function."""

    @pytest.mark.asyncio
    async def test_build_messages_basic(self):
        """Should build messages with system and user prompts."""
        messages = await build_messages(
            user_prompt="Hello",
            user_context=None,
            system_text="You are a helpful assistant",
        )

        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "You are a helpful assistant"
        assert messages[1]["role"] == "user"
        assert "Hello" in messages[1]["content"]

    @pytest.mark.asyncio
    async def test_build_messages_with_context(self):
        """Should include context in user message."""
        messages = await build_messages(
            user_prompt="What is my name?",
            user_context={"user_name": "Alice", "session_id": "123"},
            system_text="You are helpful",
        )

        assert len(messages) == 2
        user_content = messages[1]["content"]
        assert "Contexto:" in user_content
        assert "user_name" in user_content
        assert "Alice" in user_content
        assert "What is my name?" in user_content

    @pytest.mark.asyncio
    async def test_build_messages_empty_context(self):
        """Should handle empty context dictionary."""
        messages = await build_messages(
            user_prompt="Test", user_context={}, system_text="System"
        )

        assert len(messages) == 2
        # Should not include "Contexto:" if context is empty
        assert "Contexto:" not in messages[1]["content"]


# ============================================================================
# SINGLETON PATTERN
# ============================================================================


class TestSingletonPattern:
    """Test singleton client management."""

    @pytest.mark.asyncio
    async def test_get_saptiva_client_returns_instance(self, mock_settings):
        """Should return singleton client instance."""
        with patch(
            "src.services.saptiva_client.load_saptiva_api_key",
            return_value="stored-key",
        ):
            with patch("src.services.saptiva_client.httpx.AsyncClient"):
                # Reset singleton
                import src.services.saptiva_client

                src.services.saptiva_client._saptiva_client = None

                client1 = await get_saptiva_client()
                client2 = await get_saptiva_client()

                assert client1 is client2

    @pytest.mark.asyncio
    async def test_close_saptiva_client_closes_connection(self, mock_settings):
        """Should close client connection."""
        with patch(
            "src.services.saptiva_client.load_saptiva_api_key", return_value=None
        ):
            with patch(
                "src.services.saptiva_client.httpx.AsyncClient"
            ) as MockAsyncClient:
                mock_client = AsyncMock()
                mock_client.headers = {}
                mock_client.aclose = AsyncMock()
                MockAsyncClient.return_value = mock_client

                # Reset and create singleton
                import src.services.saptiva_client

                src.services.saptiva_client._saptiva_client = None

                client = await get_saptiva_client()
                await close_saptiva_client()

                mock_client.aclose.assert_awaited_once()


# ============================================================================
# Adaptación de mensajes al gateway (function calling)
# ============================================================================


class TestPrepararMensajes:
    """`preparar_mensajes` adapta el protocolo de tools al gateway.

    Regresión que cubre: la conversión anterior descartaba `tool_calls` y
    `tool_call_id`, y además InferNode ignora los mensajes con rol `tool`, así
    que el modelo respondía "no tengo datos" mientras la tarjeta mostraba el
    resultado real de la herramienta.
    """

    MENSAJES = [
        {"role": "system", "content": "eres un copiloto"},
        {"role": "user", "content": "¿qué me va a faltar?"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "predecir", "arguments": "{}"},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call_1",
            "name": "predecir",
            "content": "20 articulos en riesgo",
        },
    ]

    def test_por_default_conserva_el_protocolo_estandar(self, monkeypatch):
        monkeypatch.delenv("SAPTIVA_TOOL_ROLE_AS_SYSTEM", raising=False)
        from src.services.saptiva_client import preparar_mensajes

        out = preparar_mensajes(self.MENSAJES)

        assert [m.role for m in out] == ["system", "user", "assistant", "tool"]
        # Los campos de function-calling ya NO se pierden en la conversión.
        assert out[2].tool_calls[0]["id"] == "call_1"
        assert out[3].tool_call_id == "call_1"
        assert out[3].name == "predecir"

    def test_con_flag_el_resultado_viaja_como_system(self, monkeypatch):
        monkeypatch.setenv("SAPTIVA_TOOL_ROLE_AS_SYSTEM", "true")
        from src.services.saptiva_client import preparar_mensajes

        out = preparar_mensajes(self.MENSAJES)

        # El assistant que solo llevaba tool_calls se omite (quedaría huérfano).
        assert [m.role for m in out] == ["system", "user", "system"]
        assert "20 articulos en riesgo" in out[-1].content
        assert "predecir" in out[-1].content

    def test_con_flag_no_altera_una_conversacion_sin_tools(self, monkeypatch):
        monkeypatch.setenv("SAPTIVA_TOOL_ROLE_AS_SYSTEM", "true")
        from src.services.saptiva_client import preparar_mensajes

        simple = [
            {"role": "system", "content": "eres un copiloto"},
            {"role": "user", "content": "hola"},
        ]
        out = preparar_mensajes(simple)

        assert [(m.role, m.content) for m in out] == [
            ("system", "eres un copiloto"),
            ("user", "hola"),
        ]

    def test_assistant_con_texto_y_tool_calls_se_conserva(self, monkeypatch):
        monkeypatch.setenv("SAPTIVA_TOOL_ROLE_AS_SYSTEM", "true")
        from src.services.saptiva_client import preparar_mensajes

        msgs = [
            {
                "role": "assistant",
                "content": "voy a revisar",
                "tool_calls": [{"id": "c1", "type": "function", "function": {}}],
            }
        ]
        out = preparar_mensajes(msgs)

        assert len(out) == 1
        assert out[0].content == "voy a revisar"

    def test_content_nulo_no_truena(self, monkeypatch):
        monkeypatch.delenv("SAPTIVA_TOOL_ROLE_AS_SYSTEM", raising=False)
        from src.services.saptiva_client import preparar_mensajes

        out = preparar_mensajes([{"role": "assistant", "content": None}])

        assert out[0].content == ""
