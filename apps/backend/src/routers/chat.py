"""
Chat Router - Main entry point for chat API endpoints.

This module acts as a compatibility layer and router agregator,
importing from the modular chat package.

ARCHITECTURE:
    chat/                         # Package
    ├── __init__.py              # Main router aggregator
    ├── endpoints/
    │   └── message_endpoints.py # POST /chat, escalate
    └── handlers/
        └── streaming_handler.py # SSE streaming logic

MIGRATION NOTE:
    Legacy monolithic chat.py (1155 lines) has been refactored into:
    - chat/handlers/streaming_handler.py (330 lines)
    - chat/endpoints/message_endpoints.py (290 lines)
    - Remaining endpoints still in chat_legacy.py (pending migration)

BENEFITS:
    ✅ Modular: Each module has single responsibility
    ✅ Testable: Handlers and endpoints testable independently
    ✅ Maintainable: Changes localized to specific files
    ✅ Scalable: Easy to add new endpoint modules
"""

# Import modular router from chat package
from .chat import router

# Export router for main app
__all__ = ["router"]
