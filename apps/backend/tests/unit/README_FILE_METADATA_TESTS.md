# FileMetadata Unit Tests

## Overview

Tests for the new typed metadata system that replaces `Dict[str, Any]` with explicit Pydantic models (`FileMetadata`) for type safety and BSON compatibility.

## Test Coverage

### 1. FileMetadata Model Validation (`TestFileMetadataModel`)
- ✅ Valid PDF metadata with all fields
- ✅ Valid image metadata without optional `pages` field
- ✅ Missing required field (`filename`) → ValidationError
- ✅ Missing required field (`bytes`) → ValidationError
- ✅ Invalid type for `bytes` (string instead of int) → ValidationError
- ✅ Optional fields can be None (`pages`, `mimetype`)
- ✅ Serialization to dict for MongoDB
- ✅ Validation from dictionary (API input)

### 2. ChatMessage with Files Field (`TestChatMessageWithFiles`)
- ✅ Create message with explicit files list
- ✅ Default values (empty lists for `files` and `file_ids`)
- ✅ Backwards compatibility with legacy `metadata` field
- ✅ Support both new `files` field and legacy `metadata`

### 3. add_user_message with Typed Metadata (`TestAddUserMessageWithTypedMetadata`)
- ✅ Add user message with valid files
- ✅ Add user message with invalid files (falls back to `file_ids` only)
- ✅ Add user message without metadata
- ✅ BSON serialization check with `jsonable_encoder()`
- ✅ Updates session stats (`message_count`, timestamps)

### 4. Integration Tests (`TestFileMetadataIntegration`)
- ✅ JSON serialization roundtrip
- ✅ Multiple files in a single message
- ✅ Schema version tracking

## Running the Tests

### Option 1: Inside Docker Container (Recommended)

If you have the tests mounted in the container:

```bash
# From project root
docker exec copilotos-api python -m pytest tests/unit/test_file_metadata.py -v
```

### Option 2: Local Environment

Install dependencies first:

```bash
cd apps/api
pip install -r requirements.txt
pip install pytest pytest-asyncio pytest-cov

# Run tests
python -m pytest tests/unit/test_file_metadata.py -v
```

### Option 3: Run Specific Test Classes

```bash
# Test only FileMetadata model validation
pytest tests/unit/test_file_metadata.py::TestFileMetadataModel -v

# Test only add_user_message integration
pytest tests/unit/test_file_metadata.py::TestAddUserMessageWithTypedMetadata -v
```

## Test Structure

```
test_file_metadata.py
├── TestFileMetadataModel             # Pydantic model validation
│   ├── test_valid_file_metadata_pdf
│   ├── test_valid_file_metadata_image
│   ├── test_missing_required_field_filename
│   ├── test_invalid_type_for_bytes
│   └── ...
├── TestChatMessageWithFiles          # ChatMessage model with files
│   ├── test_create_message_with_files_field
│   ├── test_backwards_compatible_with_legacy_metadata
│   └── ...
├── TestAddUserMessageWithTypedMetadata  # Service layer integration
│   ├── test_add_user_message_with_valid_files
│   ├── test_add_user_message_with_invalid_files_falls_back
│   └── ...
└── TestFileMetadataIntegration       # End-to-end scenarios
    ├── test_json_serialization_roundtrip
    └── ...
```

## What's Being Tested

### Type Safety Layers

1. **Pydantic Validation**: Catches invalid structure before MongoDB
2. **BSON Encoding Test**: Catches non-serializable types (datetime without encoder, etc.)
3. **MongoDB Insert**: Only fails on infrastructure errors, not data issues

### Graceful Degradation

- If `FileMetadata` validation fails → saves only `file_ids`
- Chat continues working, just without rich file indicators
- Detailed error logging for debugging

### Backwards Compatibility

- `schema_version = 2` for new messages
- Legacy `metadata: Dict[str, Any]` field still supported
- Old messages (without `files` field) continue to work

## Expected Test Output

```
============================= test session starts ==============================
collected 23 items

tests/unit/test_file_metadata.py::TestFileMetadataModel::test_valid_file_metadata_pdf PASSED
tests/unit/test_file_metadata.py::TestFileMetadataModel::test_valid_file_metadata_image PASSED
tests/unit/test_file_metadata.py::TestFileMetadataModel::test_missing_required_field_filename PASSED
...
tests/unit/test_file_metadata.py::TestFileMetadataIntegration::test_schema_version_tracking PASSED

======================= 23 passed in 0.45s =======================
```

## Troubleshooting

### ModuleNotFoundError: No module named 'beanie'

Install dependencies:
```bash
pip install beanie pydantic fastapi
```

### Tests not found in Docker container

The tests directory might not be mounted. Check `docker-compose.yml`:
```yaml
volumes:
  - ./apps/api/tests:/app/tests  # Add this if missing
```

### Permission denied when copying to container

The volume might be read-only. Run tests locally instead:
```bash
cd apps/api
python -m pytest tests/unit/test_file_metadata.py -v
```

## Related Files

- Model: `apps/api/src/models/chat.py` (FileMetadata, ChatMessage)
- Service: `apps/api/src/services/chat_service.py` (add_user_message)
- Router: `apps/api/src/routers/chat.py` (chat endpoint)

## Next Steps

After tests pass:
1. Test with real file upload in UI
2. Verify metadata persists after page refresh
3. Check MongoDB documents have correct schema
4. Monitor logs for validation errors

```bash
# Check logs for validation
docker logs copilotos-api -f | grep -E "(Validated file metadata|validation failed)"
```
