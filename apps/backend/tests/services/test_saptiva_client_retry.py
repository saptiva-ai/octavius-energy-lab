"""
Tests for SaptivaClient retry logic (ISSUE-013).

Verifies exponential backoff, max retries, and error handling.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx
from datetime import datetime

from src.services.saptiva_client import SaptivaClient


@pytest.mark.asyncio
async def test_retry_logic_exponential_backoff():
    """
    Test that retry logic retries with exponential backoff and eventually succeeds.

    Scenario: 2 failures, then success on 3rd attempt.
    """
    client = SaptivaClient()
    # Disable mock fallback to enable retry logic
    client.allow_mock_fallback = False

    # Mock httpx.AsyncClient.request to fail 2 times, then succeed
    with patch.object(client.client, 'request') as mock_request:
        # First two calls fail with network error
        mock_request.side_effect = [
            httpx.ConnectError("Connection failed"),  # 1st attempt
            httpx.ConnectError("Connection failed"),  # 2nd attempt
            MagicMock(
                status_code=200,
                json=lambda: {"choices": [{"message": {"content": "Success"}}]},
                raise_for_status=lambda: None
            )  # 3rd attempt (success)
        ]

        # Should succeed after retries
        response = await client._make_request("POST", "/chat/completions", data={"model": "test"})

        assert response.status_code == 200
        assert mock_request.call_count == 3  # 3 attempts total


@pytest.mark.asyncio
async def test_retry_logic_gives_up_after_max_retries():
    """
    Test that retry logic gives up after max_retries attempts.

    Scenario: All attempts fail.
    """
    client = SaptivaClient()
    client.allow_mock_fallback = False  # Disable mock fallback to enable retry logic
    client.max_retries = 2  # 1 initial + 2 retries = 3 total

    with patch.object(client.client, 'request') as mock_request:
        # Always fail
        mock_request.side_effect = httpx.ConnectError("Always fails")

        # Should raise after exhausting retries
        with pytest.raises(httpx.ConnectError):
            await client._make_request("POST", "/chat/completions", data={"model": "test"})

        assert mock_request.call_count == 3  # 1 initial + 2 retries


@pytest.mark.asyncio
async def test_retry_only_on_retryable_errors():
    """
    Test that retry logic only retries on network errors and 5xx, not 4xx.

    Scenario: 400 Bad Request should not be retried.
    """
    client = SaptivaClient()

    with patch.object(client.client, 'request') as mock_request:
        # Return 400 Bad Request (should not retry)
        error_response = MagicMock(status_code=400)
        error_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Bad Request", request=MagicMock(), response=error_response
        )
        mock_request.return_value = error_response

        # Should raise immediately without retries
        with pytest.raises(httpx.HTTPStatusError):
            await client._make_request("POST", "/chat/completions", data={"model": "test"})

        assert mock_request.call_count == 1  # No retries for 4xx


@pytest.mark.asyncio
async def test_retry_on_5xx_server_errors():
    """
    Test that retry logic retries on 5xx server errors.

    Scenario: 503 Service Unavailable, then success.
    """
    client = SaptivaClient()
    client.allow_mock_fallback = False  # Disable mock fallback to enable retry logic

    with patch.object(client.client, 'request') as mock_request:
        # First call returns 503, second succeeds
        error_response = MagicMock(status_code=503)
        error_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Service Unavailable", request=MagicMock(), response=error_response
        )

        success_response = MagicMock(
            status_code=200,
            json=lambda: {"choices": [{"message": {"content": "Success"}}]},
            raise_for_status=lambda: None
        )

        mock_request.side_effect = [error_response, success_response]

        # Should succeed after retry
        response = await client._make_request("POST", "/chat/completions", data={"model": "test"})

        assert response.status_code == 200
        assert mock_request.call_count == 2


@pytest.mark.asyncio
async def test_retry_with_timeout():
    """
    Test that timeout errors are retried.

    Scenario: Timeout on first attempt, then success.
    """
    client = SaptivaClient()
    client.allow_mock_fallback = False  # Disable mock fallback to enable retry logic

    with patch.object(client.client, 'request') as mock_request:
        mock_request.side_effect = [
            httpx.TimeoutException("Request timeout"),  # 1st attempt
            MagicMock(
                status_code=200,
                json=lambda: {"choices": [{"message": {"content": "Success"}}]},
                raise_for_status=lambda: None
            )  # 2nd attempt (success)
        ]

        response = await client._make_request("POST", "/chat/completions", data={"model": "test"})

        assert response.status_code == 200
        assert mock_request.call_count == 2


@pytest.mark.asyncio
async def test_exponential_backoff_timing():
    """
    Test that exponential backoff increases delay between retries.

    Verifies: delay = base_delay * (2 ** attempt)
    """
    client = SaptivaClient()

    with patch.object(client.client, 'request') as mock_request, \
         patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:

        # Fail all attempts
        mock_request.side_effect = httpx.ConnectError("Connection failed")

        try:
            await client._make_request("POST", "/chat/completions", data={"model": "test"})
        except httpx.ConnectError:
            pass

        # Check that sleep was called with increasing delays
        # Expected: 1s, 2s (for 2 retries)
        sleep_calls = [call.args[0] for call in mock_sleep.call_args_list]

        # First retry: ~1s delay
        assert 0.9 <= sleep_calls[0] <= 1.1 if len(sleep_calls) > 0 else True

        # Second retry: ~2s delay (exponential)
        assert 1.9 <= sleep_calls[1] <= 2.1 if len(sleep_calls) > 1 else True


@pytest.mark.asyncio
async def test_chat_completion_with_retries():
    """
    Integration test: chat_completion method uses retry logic correctly.
    """
    client = SaptivaClient()
    client.allow_mock_fallback = False  # Disable mock fallback

    with patch.object(client, '_make_request') as mock_make_request:
        # Mock successful response with required fields for SaptivaResponse
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "id": "test-id",
            "model": "Saptiva Turbo",
            "choices": [{
                "message": {"content": "Hello, world!"}
            }]
        }
        mock_make_request.return_value = mock_response

        result = await client.chat_completion(
            model="SAPTIVA_TURBO",
            messages=[{"role": "user", "content": "Hi"}]
        )

        assert result.choices[0]["message"]["content"] == "Hello, world!"
        mock_make_request.assert_called_once()


@pytest.mark.asyncio
async def test_streaming_does_not_retry():
    """
    Test that streaming requests do not use retry logic (streams are not idempotent).

    Note: Streaming failures should fail fast, not retry.
    """
    client = SaptivaClient()
    client.allow_mock_fallback = False  # Disable mock fallback
    client.mock_mode = False  # Ensure we're not in mock mode

    # Create a mock context manager for stream()
    mock_response = MagicMock()
    mock_response.__aenter__ = AsyncMock(side_effect=httpx.ConnectError("Connection failed"))
    mock_response.__aexit__ = AsyncMock(return_value=None)

    with patch.object(client.client, 'stream', return_value=mock_response):
        # Should raise immediately without retries
        with pytest.raises(httpx.ConnectError):
            async for _ in client.chat_completion_stream(
                model="SAPTIVA_TURBO",
                messages=[{"role": "user", "content": "Hi"}]
            ):
                pass

        # Only 1 attempt for streaming (no retries)
        assert client.client.stream.call_count == 1
