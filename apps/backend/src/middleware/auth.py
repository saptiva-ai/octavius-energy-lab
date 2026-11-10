"""
Authentication middleware for JWT token validation.
"""

from typing import Optional

import structlog
from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from ..core.config import get_settings
from ..services.cache_service import is_token_blacklisted

logger = structlog.get_logger(__name__)


class AuthMiddleware(BaseHTTPMiddleware):
    """JWT authentication middleware."""

    # Public endpoints that don't require authentication
    PUBLIC_PATHS = {
        "/api/health",
        "/api/health/live",
        "/api/health/ready",
        "/api/feature-flags",  # P0-DR-002: Feature flags need to be public for frontend
        "/api/models",  # Models endpoint needs to be public for model selector
        "/api/title",  # Title generation - lightweight endpoint, no sensitive data
        "/api/auth/login",
        "/api/auth/register",
        "/api/auth/refresh",
        "/api/auth/forgot-password",
        "/api/auth/reset-password",
        "/api/features/tools",
        "/api/features/suggestions",  # Chips de prompts (config de UI, sin datos sensibles)
        "/api/features/views",  # Vistas predefinidas (config de UI, sin datos sensibles)
        "/api/features/guide",  # Guía de la ayuda (capacidades y fechas, sin datos sensibles)
        "/docs",
        "/redoc",
        "/openapi.json",
        "/tidewave/mcp",
        "/tidewave/messages",
    }

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self.settings = get_settings()

    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request and validate JWT token if required."""

        # Skip authentication for public endpoints, internal API, and preflight requests
        if (
            request.method == "OPTIONS"
            or request.url.path in self.PUBLIC_PATHS
            or request.url.path.startswith("/api/internal/")
        ):
            return await call_next(request)

        # Extract JWT token from request
        token = self._extract_token(request)
        if not token:
            logger.warning("Missing authentication token", path=request.url.path)
            self._token_error_code = "token_missing"
            return self._unauthorized_response("token_missing", request=request)

        # Validate JWT token
        payload = self._validate_token(token)
        if not payload:
            logger.warning("Invalid JWT token", path=request.url.path)
            # _token_error_code is set by _validate_token
            return self._unauthorized_response(request=request)

        # Check if token has been revoked (blacklisted)
        is_blacklisted = await is_token_blacklisted(token)
        if is_blacklisted:
            logger.warning("Token has been revoked", path=request.url.path)
            self._token_error_code = "token_revoked"
            return self._unauthorized_response("token_revoked", request=request)

        # Add user context to request
        request.state.user_id = payload.get("sub") or payload.get("user_id")
        request.state.authenticated = True
        request.state.user_claims = payload

        logger.debug(
            "Authenticated request",
            user_id=request.state.user_id,
            path=request.url.path,
        )

        return await call_next(request)

    def _extract_token(self, request: Request) -> Optional[str]:
        """
        Extract JWT token from Authorization header or query string.

        Query string support is for EventSource (SSE) which can't send custom headers.
        """
        # Try Authorization header first
        auth_header = request.headers.get("Authorization")
        if auth_header:
            try:
                scheme, token = auth_header.split()
                if scheme.lower() == "bearer":
                    return token
            except ValueError:
                pass

        # Fallback to query string for EventSource compatibility
        # Only for SSE endpoints (/events/)
        if "/events/" in request.url.path:
            token = request.query_params.get("token")
            if token:
                return token

        return None

    def _validate_token(self, token: str) -> Optional[dict]:
        """Validate JWT token and return payload."""
        try:
            import jwt
            from jwt.exceptions import ExpiredSignatureError
            from jwt.exceptions import PyJWTError as JWTError

            payload = jwt.decode(
                token,
                self.settings.jwt_secret_key,
                algorithms=[self.settings.jwt_algorithm],
                options={"verify_exp": True},
            )

            logger.debug(
                "JWT token validated successfully",
                user_id=payload.get("sub") or payload.get("user_id"),
            )
            return payload

        except ExpiredSignatureError:
            logger.warning("JWT token expired")
            # Store error code for response
            self._token_error_code = "token_expired"
            return None
        except JWTError as exc:
            logger.warning("JWT token validation failed", error=str(exc))
            # Determine if it's invalid signature or other JWT error
            error_str = str(exc).lower()
            if "signature" in error_str:
                self._token_error_code = "token_invalid"
            else:
                self._token_error_code = "token_invalid"
            return None
        except Exception as e:
            logger.error("Unexpected error validating JWT token", error=str(e))
            self._token_error_code = "token_invalid"
            return None

    def _unauthorized_response(
        self, code: str = "token_invalid", request: Optional[Request] = None
    ) -> JSONResponse:
        """Return standardized unauthorized response with error codes and CORS headers."""
        # Use stored error code if available
        error_code = getattr(self, "_token_error_code", code)

        error_messages = {
            "token_expired": "El token ha expirado",
            "token_invalid": "Token inválido",
            "token_revoked": "La sesión ha sido revocada",
            "token_missing": "Token de autenticación requerido",
        }

        # Build CORS headers so browsers can read the 401 response
        headers: dict[str, str] = {}
        if request:
            origin = request.headers.get("origin")
            if origin and origin in self.settings.parsed_cors_origins:
                headers["access-control-allow-origin"] = origin
                headers["access-control-allow-credentials"] = "true"

        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={
                "code": error_code,
                "message": error_messages.get(error_code, "No autenticado"),
            },
            headers=headers,
        )
