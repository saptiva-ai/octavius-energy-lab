# Saptiva Integration Tests

Integration tests for the Saptiva text extraction API. These tests make real API calls and require valid credentials.

## Prerequisites

1. **Saptiva API Credentials**
   ```bash
   export SAPTIVA_BASE_URL=https://api.saptiva.com
   export SAPTIVA_API_KEY=your-real-api-key-here
   ```

2. **Redis Instance** (for caching tests)
   ```bash
   export REDIS_URL=redis://localhost:6379/0
   ```

3. **Python Dependencies**
   ```bash
   pip install pytest pytest-asyncio redis zstandard httpx
   ```

## Running Tests

### Run All Integration Tests

```bash
# From project root
pytest apps/api/tests/integration/test_saptiva_integration.py -v -m integration
```

### Run Specific Test Classes

```bash
# PDF extraction tests only
pytest apps/api/tests/integration/test_saptiva_integration.py::TestSaptivaAPIIntegration -v

# OCR tests only
pytest apps/api/tests/integration/test_saptiva_integration.py::TestSaptivaOCRIntegration -v

# Cache tests only
pytest apps/api/tests/integration/test_saptiva_integration.py::TestCacheIntegration -v

# End-to-end tests
pytest apps/api/tests/integration/test_saptiva_integration.py::TestEndToEndWorkflow -v
```

### Run with Verbose Output

```bash
pytest apps/api/tests/integration/test_saptiva_integration.py -v -s -m integration
```

The `-s` flag shows print statements for additional debugging information.

## Test Coverage

### TestSaptivaAPIIntegration
Tests core PDF extraction functionality:
- ✅ Health check with real credentials
- ✅ PDF text extraction via API
- ✅ Caching integration
- ✅ Circuit breaker behavior
- ✅ Cost optimization (searchable PDF detection)

### TestSaptivaOCRIntegration
Tests image OCR functionality:
- ⏳ Image text extraction (pending final OCR API spec)

### TestCacheIntegration
Tests Redis caching layer:
- ✅ Cache set and get operations
- ✅ Text compression with zstd
- ⏳ Cache expiration (manual test)

### TestEndToEndWorkflow
Tests complete user workflows:
- ✅ Full extraction pipeline from upload to output

## Cost Considerations

⚠️ **WARNING**: These tests make real API calls to Saptiva which may incur costs.

Estimated costs per test run:
- PDF extraction: ~$0.01-0.05 per call
- OCR extraction: ~$0.05-0.10 per call
- Total test suite: ~$0.20-0.50

**Recommendations:**
1. Run integration tests sparingly (not in CI)
2. Use staging API if available
3. Monitor API usage in Saptiva dashboard
4. Set up billing alerts

## Sample Test Files

To use your own test files, create a `test_files/` directory:

```bash
mkdir -p apps/api/tests/integration/test_files
```

Add sample files:
- `sample.pdf` - PDF document for extraction tests
- `sample_ocr.png` - Image with text for OCR tests

The tests will automatically use these files if present.

## Debugging Failed Tests

### Authentication Errors

```
Error: Saptiva API client error (401): Unauthorized
```

**Solution**: Verify `SAPTIVA_API_KEY` is set correctly:
```bash
echo $SAPTIVA_API_KEY  # Should output your key
```

### Connection Errors

```
Error: Failed to connect to Redis
```

**Solution**: Ensure Redis is running:
```bash
redis-cli ping  # Should return "PONG"
```

### Rate Limit Errors

```
Error: Saptiva API client error (429): Too Many Requests
```

**Solution**: Wait a few minutes and retry. Consider adding delays between tests.

### Circuit Breaker Errors

```
Error: Saptiva API circuit breaker is OPEN
```

**Solution**: Circuit breaker opened due to repeated failures. Wait 60 seconds for it to transition to half-open state, then retry.

## CI/CD Integration

These tests are **not** run automatically in CI because they:
1. Require real API credentials (security risk)
2. Incur API costs
3. Depend on external service availability

**Recommended Strategy:**
- Run manually before production deployments
- Run weekly on a schedule to verify API health
- Use staging environment if available

## Test Markers

Tests use pytest markers for selective execution:

```python
@pytest.mark.integration  # Integration tests (requires real API)
@pytest.mark.skip         # Skipped tests (pending implementation)
```

## Extending Tests

To add new integration tests:

1. **Create test class** in `test_saptiva_integration.py`
2. **Add fixtures** for test data
3. **Mark with `@pytest.mark.integration`**
4. **Document cost implications**
5. **Update this README**

Example:

```python
@pytest.mark.integration
class TestNewFeature:
    @pytest.fixture
    def extractor(self):
        # Setup
        pass

    @pytest.mark.asyncio
    async def test_new_functionality(self, extractor):
        # Test implementation
        pass
```

## Troubleshooting

### Test Collection Errors

If pytest doesn't find tests:
```bash
# Verify test discovery
pytest apps/api/tests/integration/test_saptiva_integration.py --collect-only
```

### Async Test Errors

If you see "RuntimeError: no running event loop":
```bash
# Ensure pytest-asyncio is installed
pip install pytest-asyncio

# Verify pytest.ini has asyncio_mode configured
```

### Import Errors

If you see "ModuleNotFoundError: No module named 'src'":
```bash
# Run from project root with PYTHONPATH set
cd apps/api
PYTHONPATH=. pytest tests/integration/test_saptiva_integration.py -v
```

## Additional Resources

- [Saptiva API Documentation](https://docs.saptiva.com)
- [pytest Documentation](https://docs.pytest.org/)
- [pytest-asyncio Documentation](https://pytest-asyncio.readthedocs.io/)
- [Redis Documentation](https://redis.io/documentation)

## Support

For issues with:
- **Tests**: Check this README and test file comments
- **Saptiva API**: Contact Saptiva support
- **Redis**: Check Redis logs and connection settings
