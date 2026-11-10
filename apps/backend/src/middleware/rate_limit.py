"""
Rate limiting middleware using slowapi.

Prevents abuse of API endpoints by limiting request rates per user/IP.
Uses Redis storage when available for shared state across workers/instances.
"""

import os

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware


async def _rate_limit_exceeded_handler(
    request: Request, exc: RateLimitExceeded
) -> JSONResponse:
    """
    Handle rate limit exceeded errors.

    Returns a 429 Too Many Requests response with retry information.
    """
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Rate limit exceeded. Please try again later.",
            "retry_after": getattr(exc, "retry_after", 60),
        },
        headers={"Retry-After": str(getattr(exc, "retry_after", 60))},
    )


def get_user_id_or_ip(request: Request) -> str:
    """
    Get user ID from JWT token, fallback to IP address.

    This ensures:
    - Authenticated users are rate-limited per user
    - Anonymous users are rate-limited per IP
    """
    # Try to get user from request state (set by auth middleware)
    user = getattr(request.state, "user", None)
    if user and hasattr(user, "id"):
        return f"user:{user.id}"

    # Fallback to IP address
    return f"ip:{get_remote_address(request)}"


def _get_rate_limit_storage_uri() -> str:
    """Get storage URI for rate limiter. Prefers Redis, falls back to memory."""
    redis_url = os.getenv("REDIS_URL", "")
    if redis_url:
        return redis_url
    return "memory://"


# Initialize rate limiter
limiter = Limiter(
    key_func=get_user_id_or_ip,
    default_limits=["1000/hour"],  # Global default: 1000 requests per hour
    storage_uri=_get_rate_limit_storage_uri(),
    strategy="fixed-window",  # Fixed window strategy
)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Placeholder middleware for rate limiting.

    Actual rate limiting is done via @limiter.limit() decorator on endpoints.
    This middleware is just for compatibility with the main.py middleware chain.
    """

    async def dispatch(self, request: Request, call_next):
        # Pass through - actual rate limiting handled by decorators
        response = await call_next(request)
        return response
