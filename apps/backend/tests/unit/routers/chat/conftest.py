"""
Shared fixtures for chat router tests.

Contains reusable mocks and test data for all chat endpoint tests.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from uuid import uuid4

from src.models.chat import ChatMessage, MessageRole, MessageStatus, FileMetadata
from src.schemas.chat import ChatRequest, ChatResponse, ChatSessionListResponse, ChatSession
from src.schemas.common import ApiResponse
from src.core.config import Settings
from src.domain import ChatContext, ChatProcessingResult


@pytest.fixture
def mock_settings():
    """Create mock settings for all chat tests."""
    # Use MagicMock without spec to avoid iteration issues with rich library
    settings = MagicMock()
    settings.saptiva_base_url = "https://api.test.com"
    settings.saptiva_api_key = "test-key"
    settings.deep_research_kill_switch = False
    settings.max_file_size_mb = 50
    settings.tool_retail_advisor_enabled = True
    settings.retail_advisor_url = "http://retail-advisor:8002"
    settings.enable_model_system_prompt = True
    settings.mongodb_url = "mongodb://localhost:27017"
    settings.weaviate_url = "http://localhost:8080"
    settings.redis_url = "redis://localhost:6379"
    # Iterable fields must have proper values
    settings.parsed_cors_origins = ["http://localhost:3000"]
    settings.parsed_allowed_hosts = ["localhost", "testserver"]
    # Prevent Mock iteration issues
    settings.__iter__ = lambda self: iter([])
    return settings


from pydantic import ConfigDict

class MockDbSession(ChatSession):
    """Mock session that looks like a DB object but validates as a Schema."""
    model_config = ConfigDict(extra='allow')

    def __init__(self, **data):
        super().__init__(**data)
        self.update = AsyncMock()
        self.delete = AsyncMock()
        self.save = AsyncMock()
        self.insert = AsyncMock()
        self.get_messages = AsyncMock(return_value=[])

@pytest.fixture
def mock_chat_session():
    """Create a mock chat session."""
    session = MockDbSession(
        id="test-chat-id-123",
        user_id="test-user-456",
        title="Test Chat Session",
        tools_enabled={"web_search": True},
        message_count=2,
        pinned=False,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    return session


@pytest.fixture
def mock_chat_message():
    """Create a mock chat message."""
    message = AsyncMock(spec=ChatMessage)
    message.id = "msg-123"
    message.chat_id = "test-chat-id-123"
    message.role = MessageRole.USER
    message.content = "Hello, world!"
    message.status = MessageStatus.DELIVERED
    message.created_at = datetime.utcnow()
    message.updated_at = datetime.utcnow()
    message.file_ids = []
    message.metadata = {}
    message.model = None
    message.tokens = 10
    message.latency_ms = 100
    message.task_id = None

    return message


@pytest.fixture
def mock_chat_request():
    """Create a valid ChatRequest."""
    return ChatRequest(
        message="What is the capital of France?",
        model="saptiva-turbo",
        tools_enabled={"web_search": True},
        temperature=0.7,
        max_tokens=2000,
        stream=False,
        metadata={"source": "test"}
    )


@pytest.fixture
def mock_chat_streaming_request():
    """Create a ChatRequest with streaming enabled."""
    return ChatRequest(
        message="Explain quantum computing",
        model="saptiva-turbo",
        stream=True,
        temperature=0.8,
        max_tokens=3000
    )


@pytest.fixture
def mock_chat_context():
    """Create a ChatContext for testing."""
    return ChatContext(
        user_id="test-user-456",
        request_id="req-789",
        timestamp=datetime.utcnow(),
        chat_id="test-chat-id-123",
        session_id="sess-123",
        message="What is AI?",
        context=None,
        document_ids=["doc-1", "doc-2"],
        model="saptiva-turbo",
        tools_enabled={"web_search": True},
        stream=False,
        temperature=0.7,
        max_tokens=2000,
        kill_switch_active=False
    )


@pytest.fixture
def mock_chat_processing_result():
    """Create a ChatProcessingResult."""
    metadata = Mock()
    metadata.message_id = "msg-123"
    metadata.chat_id = "test-chat-id-123"
    metadata.user_message_id = "user-msg-123"
    metadata.assistant_message_id = "asst-msg-123"
    metadata.model_used = "saptiva-turbo"
    metadata.tokens_used = {"prompt": 20, "completion": 100}
    metadata.latency_ms = 500
    metadata.decision_metadata = {"tool_invocations": []}

    return ChatProcessingResult(
        content="Paris is the capital of France.",
        sanitized_content="Paris is the capital of France.",
        metadata=metadata,
        processing_time_ms=500,
        strategy_used="StandardChat",
        task_id=None,
        research_triggered=False,
        session_title=None,
        session_updated=False
    )


@pytest.fixture
def mock_redis_cache():
    """Create a mock Redis cache."""
    cache = AsyncMock()
    cache.get_chat_history = AsyncMock(return_value=None)
    cache.set_chat_history = AsyncMock()
    cache.invalidate_chat_history = AsyncMock()
    cache.invalidate_all_for_chat = AsyncMock()
    cache.get_research_tasks = AsyncMock(return_value=None)
    cache.set_research_tasks = AsyncMock()
    return cache


@pytest.fixture
def mock_chat_service(mock_chat_session):
    """Create a mock ChatService."""
    service = AsyncMock()
    service.get_or_create_session = AsyncMock(return_value=mock_chat_session)
    service.get_session = AsyncMock(return_value=mock_chat_session)
    service.add_user_message = AsyncMock()
    service.add_assistant_message = AsyncMock()
    return service


@pytest.fixture
def mock_history_service(mock_chat_session):
    """Create a mock HistoryService."""
    service = AsyncMock()
    service.get_chat_sessions = AsyncMock(return_value={
        "sessions": [mock_chat_session],
        "total_count": 1,
        "has_more": False
    })
    service.get_session_with_permission_check = AsyncMock(return_value=mock_chat_session)
    return service


@pytest.fixture
def mock_http_request_with_user():
    """Create a mock HTTP request with user_id in state."""
    request = Mock()
    request.state = Mock()
    request.state.user_id = "test-user-456"
    return request


@pytest.fixture
def mock_response():
    """Create a mock HTTP response."""
    response = Mock()
    response.headers = {}
    response.headers.update = Mock()
    return response


@pytest.fixture
def mock_handler_chain():
    """Create a mock message handler chain."""
    chain = AsyncMock()
    chain.handle = AsyncMock()
    return chain


@pytest.fixture
def mock_streaming_handler():
    """Create a mock StreamingHandler."""
    handler = AsyncMock()
    handler.handle_stream = AsyncMock()
    return handler


class MockBeanieQueryBuilder:
    """
    Robust mock for Beanie query chaining.

    Simulates Beanie's query builder with proper method chaining support.
    Each method returns self to enable fluent interface.
    """
    def __init__(self, messages=None, total_count=100):
        """
        Initialize mock query builder.

        Args:
            messages: List of mock message objects to return from to_list()
            total_count: Total count to return from count()
        """
        self._messages = messages or []
        self._total_count = total_count
        self._skip_value = 0
        self._limit_value = None
        self.find_called_with = []
        self.sort_called_with = None
        self.skip_called_with = None
        self.limit_called_with = None

    def find(self, *conditions):
        """Mock find method with chaining support."""
        self.find_called_with.append(conditions)
        return self

    def sort(self, *args, **kwargs):
        """Mock sort method with chaining support."""
        self.sort_called_with = (args, kwargs)
        return self

    def skip(self, value):
        """Mock skip method with chaining support."""
        self._skip_value = value
        self.skip_called_with = value
        return self

    def limit(self, value):
        """Mock limit method with chaining support."""
        self._limit_value = value
        self.limit_called_with = value
        return self

    async def count(self):
        """Async count method."""
        return self._total_count

    async def to_list(self):
        """Async to_list method with pagination support."""
        # Apply skip and limit to the messages
        skip_val = self._skip_value or 0
        limit_val = self._limit_value

        messages = self._messages[skip_val:]
        if limit_val is not None:
            messages = messages[:limit_val]

        return messages

    async def delete(self):
        """Async delete method."""
        pass


@pytest.fixture
def mock_chat_message_query():
    """Create a mock Beanie query chain for ChatMessage.find()."""
    async def async_count():
        return 100

    async def async_to_list():
        return []

    # Create a mock query object that supports method chaining
    query = MagicMock()

    # Make all methods return self for chaining
    def chain(*args, **kwargs):
        return query

    query.find = MagicMock(side_effect=chain)
    query.sort = MagicMock(side_effect=chain)
    query.skip = MagicMock(side_effect=chain)
    query.limit = MagicMock(side_effect=chain)
    query.count = async_count  # Async callable
    query.to_list = async_to_list  # Async callable
    query.delete = AsyncMock()

    return query
