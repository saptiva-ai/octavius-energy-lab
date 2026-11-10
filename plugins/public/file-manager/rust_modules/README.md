# Document Processing Rust Module

High-performance document processing module for OctaviOS File Manager.

## Performance Targets

| Operation | Python | Rust | Speedup |
|-----------|--------|------|---------|
| PDF text extraction | ~470ms | ~10ms | 47x |
| OCR (per page) | ~3s | ~1s | 3x |
| Thumbnail generation | ~250ms | ~50ms | 5x |
| Text quality validation | ~10ms | ~1ms | 10x |

## Building

### Development

```bash
# Install maturin
pip install maturin

# Build and install in development mode
cd rust_modules
maturin develop --release
```

### Production (Docker)

The Dockerfile includes a multi-stage build that:
1. Compiles Rust code in a rust-builder stage
2. Builds the wheel with maturin
3. Installs the wheel in the final runtime image

## Usage

```python
import document_processing_rs as rs

# PDF extraction (47x faster)
pages = rs.extract_text_from_pdf(pdf_bytes)
for page in pages:
    print(f"Page {page.page}: {len(page.text)} chars, needs_ocr={page.needs_ocr}")

# OCR processing (3x faster)
text = rs.ocr_image("/path/to/image.png", lang="spa+eng")

# Thumbnail generation (5x faster)
result = rs.generate_thumbnail_bytes(image_bytes, width=200, height=200)
print(f"Thumbnail: {result.width}x{result.height}, {len(result.data)} bytes")

# Text quality validation (10x faster)
metrics = rs.get_quality_metrics(text)
print(f"Quality: {metrics.quality_ratio:.2f}, words={metrics.word_count}")
```

## Dependencies

### System Requirements

- Rust 1.75+ (for building)
- Tesseract OCR 4.x+ (for OCR functionality)
- Leptonica (Tesseract dependency)

### Rust Crates

- `pyo3`: Python bindings
- `pdf-extract`: PDF text extraction
- `lopdf`: PDF parsing
- `leptess`: Tesseract bindings
- `image`: Image processing
- `rayon`: Parallel processing
- `regex`: Fast text matching

## Fallback

If the Rust module is not available, the Python code falls back to:
- `pypdf` for PDF extraction
- `pytesseract` for OCR
- `PIL/Pillow` for thumbnails

This ensures the system works even without Rust compilation.
