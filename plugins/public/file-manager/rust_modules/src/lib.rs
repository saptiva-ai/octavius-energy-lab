//! OctaviOS Document Processing - Rust Native Module
//!
//! High-performance document processing with PyO3 bindings.
//! Provides 10-50x speedup over pure Python implementations.
//!
//! # Performance Targets
//! - PDF extraction: 47x faster (pdf-extract vs PyMuPDF)
//! - OCR processing: 3x faster (parallel with rayon)
//! - Thumbnail generation: 5x faster (image crate)
//! - Text quality validation: 10x faster (regex crate)

use pyo3::prelude::*;

mod errors;
mod ocr_processor;
mod pdf_extractor;
mod text_quality;
mod thumbnail_gen;

/// Document Processing Rust Module for OctaviOS File Manager
///
/// This module exposes high-performance document processing functions
/// to Python via PyO3 bindings.
#[pymodule]
fn document_processing_rs(m: &Bound<'_, PyModule>) -> PyResult<()> {
    // Register version
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;

    // PDF extraction functions (47x faster)
    m.add_function(wrap_pyfunction!(pdf_extractor::extract_text_from_pdf, m)?)?;
    m.add_function(wrap_pyfunction!(pdf_extractor::extract_text_parallel, m)?)?;
    m.add_function(wrap_pyfunction!(pdf_extractor::get_pdf_page_count, m)?)?;

    // OCR processing functions (3x faster with rayon, optional feature)
    m.add_function(wrap_pyfunction!(ocr_processor::ocr_image, m)?)?;
    m.add_function(wrap_pyfunction!(ocr_processor::ocr_image_bytes, m)?)?;
    m.add_function(wrap_pyfunction!(ocr_processor::ocr_images_parallel, m)?)?;
    m.add_function(wrap_pyfunction!(ocr_processor::is_ocr_available, m)?)?;

    // Thumbnail generation functions (5x faster)
    m.add_function(wrap_pyfunction!(thumbnail_gen::generate_thumbnail, m)?)?;
    m.add_function(wrap_pyfunction!(thumbnail_gen::generate_thumbnail_bytes, m)?)?;
    m.add_function(wrap_pyfunction!(
        thumbnail_gen::generate_thumbnails_parallel,
        m
    )?)?;

    // Text quality validation functions (10x faster)
    m.add_function(wrap_pyfunction!(text_quality::is_quality_sufficient, m)?)?;
    m.add_function(wrap_pyfunction!(text_quality::calculate_char_ratio, m)?)?;
    m.add_function(wrap_pyfunction!(text_quality::count_words, m)?)?;
    m.add_function(wrap_pyfunction!(text_quality::get_quality_metrics, m)?)?;

    // Register classes
    m.add_class::<pdf_extractor::PageResult>()?;
    m.add_class::<text_quality::QualityMetrics>()?;
    m.add_class::<thumbnail_gen::ThumbnailResult>()?;

    Ok(())
}
