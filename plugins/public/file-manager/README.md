# OctaviOS File Manager Plugin

Public plugin for file upload, download, and text extraction.

## Features

- **File Upload**: Upload PDFs and images with automatic text extraction
- **File Download**: Download files directly or via presigned URLs
- **Text Extraction**: Extract text from PDFs (native + OCR fallback) and images
- **Caching**: Redis-based caching for extracted text

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/upload` | Upload a file |
| `GET` | `/download/{path}` | Download a file |
| `GET` | `/metadata/{path}` | Get file metadata and text |
| `DELETE` | `/files/{path}` | Delete a file |
| `POST` | `/extract/{path}` | Extract/re-extract text |
| `GET` | `/health` | Health check |

## Configuration

Environment variables:

```bash
# MinIO
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin123
MINIO_BUCKET_DOCUMENTS=documents

# Redis
REDIS_URL=redis://redis:6379/0

# File limits
MAX_FILE_SIZE_MB=50
```

## Docker

```bash
# Build
docker build -t octavios-file-manager .

# Run
docker run -p 8001:8001 octavios-file-manager
```

## Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally
uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload
```

## License

MIT
