#!/usr/bin/env python3
"""
PDF to Markdown Converter using Local OCR Extraction

This script converts PDFs to Markdown using the same extraction method
used in production (pypdf + selective OCR fallback).

Usage:
    python apps/api/tools/pdf_to_markdown.py

Input:  tests/inputs_pdfs/*.pdf
Output: tests/outputs_markdown/*.md
Report: tests/outputs_markdown/CONVERSION_REPORT.md
"""

import asyncio
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

# Add apps/api to path so we can import src modules
# __file__ is apps/api/tools/pdf_to_markdown.py
# parents[0] = tools, parents[1] = apps/api, parents[2] = apps, parents[3] = project_root
api_root = Path(__file__).resolve().parents[1]
project_root = api_root.parent.parent
sys.path.insert(0, str(api_root))

import structlog
from src.services.document_extraction import extract_text_from_file
from src.models.document import PageContent

logger = structlog.get_logger(__name__)

# Configuration
INPUT_DIR = project_root / "tests" / "inputs_pdfs"
OUTPUT_DIR = project_root / "tests" / "outputs_markdown"
REPORT_PATH = OUTPUT_DIR / "CONVERSION_REPORT.md"


def format_markdown_output(pages: List[PageContent], filename: str) -> str:
    """
    Convert PageContent objects to clean Markdown format.

    Args:
        pages: List of PageContent objects with extracted text
        filename: Original PDF filename

    Returns:
        Formatted markdown string
    """
    markdown_lines = [
        f"# {filename}",
        "",
        f"**Fecha de extracción:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Total de páginas:** {len(pages)}",
        f"**Método de extracción:** pypdf + OCR selectivo",
        "",
        "---",
        "",
    ]

    for page in pages:
        markdown_lines.append(f"## Página {page.page}")
        markdown_lines.append("")

        # Add metadata if available
        metadata = []
        if hasattr(page, 'has_table') and page.has_table:
            metadata.append("📊 Contiene tablas")
        if hasattr(page, 'has_images') and page.has_images:
            metadata.append("🖼️ Contiene imágenes")

        if metadata:
            markdown_lines.append(f"*{' | '.join(metadata)}*")
            markdown_lines.append("")

        # Add extracted text
        text = page.text_md.strip()
        if text:
            markdown_lines.append(text)
        else:
            markdown_lines.append("*[Sin texto extraíble]*")

        markdown_lines.append("")
        markdown_lines.append("---")
        markdown_lines.append("")

    return "\n".join(markdown_lines)


def generate_comparison_report(conversions: List[Dict[str, Any]]) -> str:
    """
    Generate a consolidated comparison report in Markdown.

    Args:
        conversions: List of conversion metadata dictionaries

    Returns:
        Formatted markdown report
    """
    report_lines = [
        "# 📄 OCR Extract Comparison (Markdown Outputs)",
        "",
        f"**Generado:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Total de archivos procesados:** {len(conversions)}",
        f"**Método de extracción:** pypdf + OCR selectivo (producción)",
        "",
        "---",
        "",
        "## Resumen de Conversiones",
        "",
        "| Archivo | Páginas | Total Caracteres | Tamaño MD (KB) | Promedio Chars/Página | Estado |",
        "|---------|---------|------------------|----------------|-----------------------|--------|",
    ]

    total_pages = 0
    total_chars = 0
    total_size_kb = 0.0

    for conv in conversions:
        filename = conv['filename']
        pages = conv['pages']
        chars = conv['total_chars']
        size_kb = conv['size_kb']
        status = conv['status']
        avg_chars = chars // pages if pages > 0 else 0

        status_emoji = "✅" if status == "success" else "❌"

        report_lines.append(
            f"| {filename} | {pages} | {chars:,} | {size_kb:.2f} | {avg_chars:,} | {status_emoji} {status} |"
        )

        if status == "success":
            total_pages += pages
            total_chars += chars
            total_size_kb += size_kb

    # Add totals row
    report_lines.append(
        f"| **TOTAL** | **{total_pages}** | **{total_chars:,}** | **{total_size_kb:.2f}** | **{total_chars // total_pages if total_pages > 0 else 0:,}** | - |"
    )

    report_lines.extend([
        "",
        "---",
        "",
        "## Detalles por Archivo",
        "",
    ])

    for conv in conversions:
        report_lines.extend([
            f"### {conv['filename']}",
            "",
            f"- **Estado:** {conv['status']}",
            f"- **Páginas:** {conv['pages']}",
            f"- **Caracteres totales:** {conv['total_chars']:,}",
            f"- **Tamaño del archivo MD:** {conv['size_kb']:.2f} KB",
            f"- **Ruta de salida:** `{conv['output_path']}`",
        ])

        if conv['status'] == 'error':
            report_lines.append(f"- **Error:** {conv.get('error', 'Desconocido')}")

        report_lines.extend(["", ""])

    report_lines.extend([
        "---",
        "",
        "## Notas Técnicas",
        "",
        "### Método de Extracción",
        "",
        "El proceso utiliza el mismo pipeline de producción del sistema Copilot OS:",
        "",
        "1. **Extracción híbrida con pypdf:**",
        "   - Se intenta extraer texto de cada página con pypdf",
        "   - Se analiza la cantidad de caracteres extraídos",
        "",
        "2. **OCR selectivo para páginas con poco texto:**",
        "   - Si una página tiene < 50 caracteres, se aplica OCR",
        "   - Se usa PyMuPDF (fitz) para rasterizar la página",
        "   - Se extrae texto con el extractor configurado (HuggingFace, Saptiva, o Tesseract)",
        "",
        "3. **Combinación de resultados:**",
        "   - Se usa el texto de mejor calidad (pypdf vs OCR)",
        "   - Se preserva la estructura de páginas",
        "",
        "### Configuración del Sistema",
        "",
        "```python",
        f"EXTRACTOR_PROVIDER: {os.getenv('EXTRACTOR_PROVIDER', 'third_party')}",
        f"MIN_CHARS_THRESHOLD: 50",
        f"OCR_RASTER_DPI: {os.getenv('OCR_RASTER_DPI', '180')}",
        f"MAX_OCR_PAGES: {os.getenv('MAX_OCR_PAGES', '30')}",
        "```",
        "",
        "---",
        "",
        f"**Generado por:** Copilot OS PDF to Markdown Converter",
        f"**Versión del pipeline:** Producción (pypdf + OCR selectivo)",
    ])

    return "\n".join(report_lines)


async def convert_pdf_to_markdown(pdf_path: Path) -> Dict[str, Any]:
    """
    Convert a single PDF to Markdown using production extraction pipeline.

    Args:
        pdf_path: Path to input PDF file

    Returns:
        Dictionary with conversion metadata
    """
    filename = pdf_path.name
    output_path = OUTPUT_DIR / filename.replace('.pdf', '.md')

    logger.info(
        "Starting PDF conversion",
        filename=filename,
        input_path=str(pdf_path),
        output_path=str(output_path),
    )

    try:
        # Extract text using production pipeline
        pages = await extract_text_from_file(
            file_path=pdf_path,
            content_type="application/pdf"
        )

        # Format as Markdown
        markdown_content = format_markdown_output(pages, filename)

        # Write to output file
        output_path.write_text(markdown_content, encoding='utf-8')

        # Calculate statistics
        total_chars = sum(len(page.text_md) for page in pages)
        size_kb = len(markdown_content.encode('utf-8')) / 1024

        logger.info(
            "PDF conversion successful",
            filename=filename,
            pages=len(pages),
            total_chars=total_chars,
            size_kb=f"{size_kb:.2f}",
        )

        return {
            'filename': filename,
            'status': 'success',
            'pages': len(pages),
            'total_chars': total_chars,
            'size_kb': size_kb,
            'output_path': str(output_path.relative_to(project_root)),
        }

    except Exception as exc:
        logger.error(
            "PDF conversion failed",
            filename=filename,
            error=str(exc),
            exc_info=True,
        )

        return {
            'filename': filename,
            'status': 'error',
            'pages': 0,
            'total_chars': 0,
            'size_kb': 0.0,
            'output_path': '',
            'error': str(exc),
        }


async def process_all_pdfs() -> None:
    """
    Process all PDFs in the input directory and generate conversion report.
    """
    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Find all PDF files
    pdf_files = list(INPUT_DIR.glob('*.pdf'))

    if not pdf_files:
        logger.warning(
            "No PDF files found in input directory",
            input_dir=str(INPUT_DIR),
        )
        print(f"\n⚠️  No se encontraron archivos PDF en {INPUT_DIR}")
        print(f"Por favor, coloca los PDFs a convertir en: {INPUT_DIR}")
        return

    logger.info(
        "Starting batch PDF conversion",
        total_files=len(pdf_files),
        input_dir=str(INPUT_DIR),
        output_dir=str(OUTPUT_DIR),
    )

    print(f"\n🚀 Iniciando conversión de {len(pdf_files)} archivos PDF...\n")

    # Process each PDF
    conversions = []
    for pdf_path in pdf_files:
        print(f"📄 Procesando: {pdf_path.name}...", end=' ')
        conv_result = await convert_pdf_to_markdown(pdf_path)
        conversions.append(conv_result)

        if conv_result['status'] == 'success':
            print(f"✅ Completado ({conv_result['pages']} páginas, {conv_result['size_kb']:.1f} KB)")
        else:
            print(f"❌ Error: {conv_result.get('error', 'Desconocido')}")

    # Generate comparison report
    print("\n📊 Generando reporte de comparación...")
    report_content = generate_comparison_report(conversions)
    REPORT_PATH.write_text(report_content, encoding='utf-8')

    # Print summary
    success_count = sum(1 for c in conversions if c['status'] == 'success')
    error_count = len(conversions) - success_count

    print(f"\n{'=' * 60}")
    print(f"✅ Conversión completada:")
    print(f"   - Exitosas: {success_count}")
    print(f"   - Errores: {error_count}")
    print(f"   - Total: {len(conversions)}")
    print(f"\n📁 Archivos generados:")
    print(f"   - Markdown: {OUTPUT_DIR}")
    print(f"   - Reporte: {REPORT_PATH}")
    print(f"{'=' * 60}\n")

    logger.info(
        "Batch PDF conversion completed",
        total_files=len(conversions),
        success_count=success_count,
        error_count=error_count,
        report_path=str(REPORT_PATH),
    )


def main():
    """Main entry point for the PDF to Markdown converter."""
    print("=" * 60)
    print("  PDF to Markdown Converter")
    print("  Using Production OCR Pipeline (pypdf + selective OCR)")
    print("=" * 60)

    # Run async conversion
    asyncio.run(process_all_pdfs())


if __name__ == '__main__':
    main()
