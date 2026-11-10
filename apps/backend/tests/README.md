# API Testing Guide

## Quick Start

### Run all tests
```bash
make test-api
```

### Run specific test file
```bash
docker compose exec api pytest tests/test_health.py -v
```

### Run with coverage report
```bash
docker compose exec api pytest tests/ -v --cov=src --cov-report=html
# Open htmlcov/index.html in browser
```

### Run tests in parallel
```bash
docker compose exec api pytest tests/ -n auto
```

## Test Structure

```
tests/
├── conftest.py           # Pytest configuration and fixtures
├── test_health.py        # Health endpoint tests
├── test_intent.py        # Intent detection tests
├── test_prompt_registry.py  # Prompt registry tests
├── test_text_sanitizer.py   # Text sanitizer tests
├── unit/                 # Unit tests
│   └── test_chat_service.py
├── integration/          # Integration tests
│   └── test_database.py
├── e2e/                  # End-to-end tests
│   ├── test_chat_models.py
│   ├── test_documents.py
│   └── test_registry_configuration.py
└── debug/                # Debug and development tests
    ├── test_aletheia_client.py
    └── test_aletheia_standalone.py
```

## Development Setup

### 1. Rebuild containers with testing dependencies
```bash
make rebuild-api
```

This will:
- Use the `development` stage from Dockerfile
- Install pytest and all testing dependencies from `requirements-dev.txt`
- Enable hot reload for faster development

### 2. Verify pytest is installed
```bash
docker compose exec api pytest --version
```

Should output: `pytest 8.4.2`

## Writing Tests

### Import Pattern
With the new `conftest.py`, use imports relative to `src/`:

```python
# Correct
from main import app
from core.config import get_settings
from services.chat_service import ChatService

# Wrong (old pattern)
from apps.api.src.main import app
```

### Example Test
```python
import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
```

### Async Tests
```python
import pytest
from httpx import AsyncClient
from main import app

@pytest.mark.asyncio
async def test_async_endpoint():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/health")
        assert response.status_code == 200
```

## Test Categories

### Health Tests (test_health.py)
- Basic health endpoint validation
- Error handling (404, 405)
- Performance benchmarks

### Intent Tests (test_intent.py)
- Intent detection and classification
- Greeting detection
- Research intent identification

### Integration Tests
- Database connection and operations
- Redis caching
- External service integration

### E2E Tests
- Complete user flows
- Multi-service interactions
- Real API calls

## Coverage

### Generate HTML coverage report
```bash
docker compose exec api pytest tests/ --cov=src --cov-report=html
```

### View coverage in terminal
```bash
docker compose exec api pytest tests/ --cov=src --cov-report=term-missing
```

### Coverage goals
- Overall: > 80%
- Critical paths (auth, chat): > 90%
- Utils and helpers: > 70%

## Debugging

### Run specific test with verbose output
```bash
docker compose exec api pytest tests/test_health.py::test_health_endpoint -vv
```

### Run with pdb debugger
```bash
docker compose exec api pytest tests/ --pdb
```

### Print detailed logs
```bash
docker compose exec api pytest tests/ -v --log-cli-level=DEBUG
```

## Common Issues

### Import Errors
**Problem**: `ModuleNotFoundError: No module named 'apps'`

**Solution**: Tests should import from `src/` directly, not `apps/api/src/`
- Make sure `conftest.py` exists in `tests/` directory
- Use imports like `from main import app` (not `from apps.api.src.main import app`)

### Pytest Not Found
**Problem**: `pytest: command not found`

**Solution**: Rebuild API container with development target
```bash
make rebuild-api
# or
docker compose up -d --build api
```

### Database Connection Errors
**Problem**: Tests fail connecting to MongoDB

**Solution**: Ensure MongoDB is running and healthy
```bash
docker compose ps mongodb
make health
```

## Dependencies

All testing dependencies are in `requirements-dev.txt`:
- pytest: Test framework
- pytest-cov: Coverage reporting
- pytest-asyncio: Async test support
- pytest-mock: Mocking utilities
- httpx: Async HTTP client
- factory-boy: Test data factories
- faker: Fake data generation
- freezegun: Time mocking

## Best Practices

1. **Arrange-Act-Assert**: Structure tests clearly
2. **One assertion per test**: Focus on single behaviors
3. **Use fixtures**: Avoid test code duplication
4. **Mock external services**: Keep tests fast and isolated
5. **Test edge cases**: Not just happy paths
6. **Descriptive names**: `test_user_creation_fails_with_invalid_email`
7. **Clean up**: Use fixtures with teardown or `autouse`

## Related Documentation

- [Pytest Documentation](https://docs.pytest.org/)
- [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
