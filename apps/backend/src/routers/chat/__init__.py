"""
Chat Router Package - Modular chat API endpoints.

This package organizes chat-related endpoints into focused modules
following Single Responsibility Principle.

Structure:
    endpoints/
        message_endpoints.py  - POST /chat, escalate
        session_endpoints.py  - GET/PATCH/DELETE sessions
        history_endpoints.py  - GET history, research tasks
    handlers/
        streaming_handler.py  - SSE streaming logic

Architecture Benefits:
    ✅ Single Responsibility: Each module has one clear purpose
    ✅ Open/Closed: Easy to add new endpoint modules
    ✅ Testability: Handlers and endpoints testable independently
    ✅ Maintainability: Changes localized to specific modules
    ✅ Scalability: Easy to extend with new modules

Endpoint Distribution:
    message_endpoints.py (290 lines):
        - POST   /chat                      # Send message
        - POST   /chat/{id}/escalate        # Escalate to research

    session_endpoints.py (350 lines):
        - GET    /sessions                  # List sessions
        - GET    /sessions/{id}/research    # Get research tasks
        - PATCH  /sessions/{id}             # Update session
        - DELETE /sessions/{id}             # Delete session

    history_endpoints.py (180 lines):
        - GET    /history/{id}              # Get chat history
"""

from fastapi import APIRouter

from .endpoints.history_endpoints import router as history_router

# Import endpoint routers
from .endpoints.message_endpoints import router as message_router
from .endpoints.session_endpoints import router as session_router

# Create main router and include sub-routers
router = APIRouter()
router.include_router(message_router)
router.include_router(session_router)
router.include_router(history_router)

# Export for use in main app
__all__ = ["router"]
