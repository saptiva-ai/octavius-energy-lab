"""Unit tests for the generic ChatContext domain object."""

from datetime import datetime

import pytest

from src.domain.chat_context import ChatContext

pytestmark = [pytest.mark.unit]


class TestChatContextWithModel:
    """`with_model` returns a new frozen instance with the model swapped."""

    def _make_ctx(self) -> ChatContext:
        return ChatContext(
            user_id="u1",
            request_id="r1",
            timestamp=datetime.utcnow(),
            chat_id="c1",
            session_id="s1",
            message="hola",
            context=None,
            model="Saptiva Turbo",
            tools_enabled={},
            stream=True,
        )

    def test_with_model_creates_new_instance(self):
        ctx = self._make_ctx()
        new_ctx = ctx.with_model("Saptiva Legacy")

        assert new_ctx.model == "Saptiva Legacy"
        assert ctx.model == "Saptiva Turbo"  # original unchanged
        assert new_ctx.user_id == ctx.user_id
        assert new_ctx.message == ctx.message
        assert new_ctx is not ctx  # different instance
