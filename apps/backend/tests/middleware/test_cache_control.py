"""
Tests for Cache-Control middleware (ISSUE-023).

Verifies that no-cache headers are applied to all API responses.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.middleware.cache_control import CacheControlMiddleware


@pytest.fixture
def app_with_cache_middleware():
    """Create FastAPI app with CacheControlMiddleware."""
    app = FastAPI()

    app.add_middleware(CacheControlMiddleware)

    @app.get("/api/test")
    async def test_endpoint():
        return {"message": "test"}

    @app.get("/public/test")
    async def public_endpoint():
        return {"message": "public"}

    return app


def test_cache_control_headers_on_api_routes(app_with_cache_middleware):
    """
    Test that Cache-Control headers are applied to /api/* routes.
    """
    client = TestClient(app_with_cache_middleware)

    response = client.get("/api/test")

    assert response.status_code == 200
    assert "Cache-Control" in response.headers
    assert response.headers["Cache-Control"] == "no-store, no-cache, must-revalidate, max-age=0"
    assert response.headers["Pragma"] == "no-cache"
    assert response.headers["Expires"] == "0"


def test_no_cache_headers_on_non_api_routes(app_with_cache_middleware):
    """
    Test that Cache-Control headers are NOT applied to non-API routes.
    """
    client = TestClient(app_with_cache_middleware)

    response = client.get("/public/test")

    assert response.status_code == 200
    # Cache-Control headers should not be present for non-API routes
    assert "Cache-Control" not in response.headers or \
           response.headers["Cache-Control"] != "no-store, no-cache, must-revalidate, max-age=0"


def test_cache_control_on_post_requests(app_with_cache_middleware):
    """
    Test that Cache-Control headers are applied to POST requests.
    """
    app = app_with_cache_middleware

    @app.post("/api/create")
    async def create_endpoint(data: dict):
        return {"created": True}

    client = TestClient(app)

    response = client.post("/api/create", json={"test": "data"})

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store, no-cache, must-revalidate, max-age=0"


def test_cache_control_on_nested_api_routes(app_with_cache_middleware):
    """
    Test that Cache-Control headers work on deeply nested API routes.
    """
    app = app_with_cache_middleware

    @app.get("/api/v1/users/123/profile")
    async def nested_endpoint():
        return {"user": "test"}

    client = TestClient(app)

    response = client.get("/api/v1/users/123/profile")

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store, no-cache, must-revalidate, max-age=0"
    assert response.headers["Pragma"] == "no-cache"
    assert response.headers["Expires"] == "0"


def test_cache_control_on_error_responses(app_with_cache_middleware):
    """
    Test that Cache-Control headers are applied to controlled error responses.

    Note: Unhandled exceptions may bypass middleware as FastAPI creates new Response objects.
    This tests controlled error responses using Response objects.
    """
    from fastapi import Response, HTTPException
    app = app_with_cache_middleware

    @app.get("/api/error")
    async def error_endpoint():
        # Return a controlled error response instead of raising
        raise HTTPException(status_code=500, detail="Test error")

    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/api/error")

    assert response.status_code == 500
    # HTTPException responses should have no-cache headers
    assert response.headers.get("Cache-Control") == "no-store, no-cache, must-revalidate, max-age=0"


def test_middleware_preserves_other_headers(app_with_cache_middleware):
    """
    Test that CacheControlMiddleware doesn't remove other response headers.
    """
    app = app_with_cache_middleware

    @app.get("/api/with-headers")
    async def endpoint_with_headers():
        from fastapi import Response
        return Response(
            content='{"test": "data"}',
            headers={"X-Custom-Header": "custom-value"}
        )

    client = TestClient(app)

    response = client.get("/api/with-headers")

    assert response.status_code == 200
    # Custom header should be preserved
    assert response.headers["X-Custom-Header"] == "custom-value"
    # Cache-Control should be added
    assert response.headers["Cache-Control"] == "no-store, no-cache, must-revalidate, max-age=0"


def test_cache_control_all_http_methods(app_with_cache_middleware):
    """
    Test that Cache-Control headers are applied to all HTTP methods.
    """
    app = app_with_cache_middleware

    @app.put("/api/update")
    async def put_endpoint():
        return {"updated": True}

    @app.delete("/api/delete")
    async def delete_endpoint():
        return {"deleted": True}

    @app.patch("/api/patch")
    async def patch_endpoint():
        return {"patched": True}

    client = TestClient(app)

    # Test PUT
    response = client.put("/api/update", json={})
    assert response.headers["Cache-Control"] == "no-store, no-cache, must-revalidate, max-age=0"

    # Test DELETE
    response = client.delete("/api/delete")
    assert response.headers["Cache-Control"] == "no-store, no-cache, must-revalidate, max-age=0"

    # Test PATCH
    response = client.patch("/api/patch", json={})
    assert response.headers["Cache-Control"] == "no-store, no-cache, must-revalidate, max-age=0"
