//! OCR processing module using Tesseract via leptess.
//!
//! This module is optional and requires the `ocr` feature flag.
//! System dependencies: libleptonica-dev, libtesseract-dev
//!
//! Provides ~3x speedup over pytesseract by:
//! - Avoiding subprocess spawning (direct library linking)
//! - Parallel processing with rayon
//! - Bypassing Python's GIL

use pyo3::prelude::*;

#[cfg(feature = "ocr")]
use crate::errors::{ProcessingError, ProcessingResult};
#[cfg(feature = "ocr")]
use leptess::{LepTess, Variable};
#[cfg(feature = "ocr")]
use rayon::prelude::*;

/// Default language for OCR (Spanish + English)
#[cfg(feature = "ocr")]
const DEFAULT_LANG: &str = "spa+eng";

// ============================================================================
// OCR Functions (only available with "ocr" feature)
// ============================================================================

#[cfg(feature = "ocr")]
fn get_tesseract(lang: &str) -> ProcessingResult<LepTess> {
    LepTess::new(None, lang)
        .map_err(|e| ProcessingError::Ocr(format!("Failed to init Tesseract: {}", e)))
}

#[cfg(feature = "ocr")]
fn ocr_image_impl(image_path: &str, lang: &str) -> ProcessingResult<String> {
    let mut tess = get_tesseract(lang)?;
    tess.set_image(image_path)
        .map_err(|e| ProcessingError::Ocr(format!("Failed to set image: {}", e)))?;
    let _ = tess.set_variable(Variable::TesseditPagesegMode, "1");
    let text = tess
        .get_utf8_text()
        .map_err(|e| ProcessingError::Ocr(format!("Failed to get text: {}", e)))?;
    Ok(text.trim().to_string())
}

#[cfg(feature = "ocr")]
fn ocr_bytes_impl(image_bytes: &[u8], lang: &str) -> ProcessingResult<String> {
    let img = image::load_from_memory(image_bytes)
        .map_err(|e| ProcessingError::Image(format!("Failed to decode image: {}", e)))?;
    let width = img.width() as i32;
    let height = img.height() as i32;
    let rgb_img = img.to_rgb8();
    let raw_bytes = rgb_img.as_raw();

    let mut tess = get_tesseract(lang)?;
    tess.set_image_from_mem(raw_bytes, width, height, 3, width * 3)
        .map_err(|e| ProcessingError::Ocr(format!("Failed to set image from memory: {}", e)))?;
    let _ = tess.set_variable(Variable::TesseditPagesegMode, "1");
    let text = tess
        .get_utf8_text()
        .map_err(|e| ProcessingError::Ocr(format!("Failed to get text: {}", e)))?;
    Ok(text.trim().to_string())
}

/// Perform OCR on an image file.
#[cfg(feature = "ocr")]
#[pyfunction]
#[pyo3(signature = (image_path, lang=None))]
pub fn ocr_image(image_path: &str, lang: Option<&str>) -> PyResult<String> {
    let lang = lang.unwrap_or(DEFAULT_LANG);
    ocr_image_impl(image_path, lang).map_err(|e| e.into())
}

/// Perform OCR on image bytes in memory.
#[cfg(feature = "ocr")]
#[pyfunction]
#[pyo3(signature = (image_bytes, lang=None))]
pub fn ocr_image_bytes(image_bytes: &[u8], lang: Option<&str>) -> PyResult<String> {
    let lang = lang.unwrap_or(DEFAULT_LANG);
    ocr_bytes_impl(image_bytes, lang).map_err(|e| e.into())
}

/// Perform OCR on multiple images in parallel.
#[cfg(feature = "ocr")]
#[pyfunction]
#[pyo3(signature = (image_paths, lang=None))]
pub fn ocr_images_parallel(
    image_paths: Vec<String>,
    lang: Option<&str>,
) -> PyResult<Vec<(String, String)>> {
    let lang = lang.unwrap_or(DEFAULT_LANG);
    let results: Vec<_> = image_paths
        .par_iter()
        .filter_map(|path| {
            let text = ocr_image_impl(path, lang).ok()?;
            Some((path.clone(), text))
        })
        .collect();
    Ok(results)
}

/// OCR multiple image byte arrays in parallel.
#[cfg(feature = "ocr")]
#[pyfunction]
#[pyo3(signature = (images, lang=None))]
pub fn ocr_bytes_parallel(
    images: Vec<(String, Vec<u8>)>,
    lang: Option<&str>,
) -> PyResult<Vec<(String, String)>> {
    let lang = lang.unwrap_or(DEFAULT_LANG);
    let results: Vec<_> = images
        .par_iter()
        .filter_map(|(id, bytes)| {
            let text = ocr_bytes_impl(bytes, lang).ok()?;
            Some((id.clone(), text))
        })
        .collect();
    Ok(results)
}

/// OCR a single PDF page from image bytes.
#[cfg(feature = "ocr")]
#[pyfunction]
#[pyo3(signature = (page_image_bytes, page_number, lang=None))]
pub fn ocr_pdf_page(
    page_image_bytes: &[u8],
    page_number: i32,
    lang: Option<&str>,
) -> PyResult<(i32, String)> {
    let lang = lang.unwrap_or(DEFAULT_LANG);
    let text = ocr_bytes_impl(page_image_bytes, lang)?;
    Ok((page_number, text))
}

/// OCR multiple PDF pages in parallel.
#[cfg(feature = "ocr")]
#[pyfunction]
#[pyo3(signature = (page_images, lang=None))]
pub fn ocr_pdf_pages_parallel(
    page_images: Vec<(i32, Vec<u8>)>,
    lang: Option<&str>,
) -> PyResult<Vec<(i32, String)>> {
    let lang = lang.unwrap_or(DEFAULT_LANG);
    let mut results: Vec<_> = page_images
        .par_iter()
        .filter_map(|(page_num, bytes)| {
            let text = ocr_bytes_impl(bytes, lang).ok()?;
            Some((*page_num, text))
        })
        .collect();
    results.sort_by_key(|(page, _)| *page);
    Ok(results)
}

// ============================================================================
// Stub functions when OCR feature is disabled
// ============================================================================

/// Stub: OCR not available without 'ocr' feature
#[cfg(not(feature = "ocr"))]
#[pyfunction]
#[pyo3(signature = (_image_path, _lang=None))]
pub fn ocr_image(_image_path: &str, _lang: Option<&str>) -> PyResult<String> {
    Err(pyo3::exceptions::PyRuntimeError::new_err(
        "OCR not available: compile with 'ocr' feature (requires libleptonica-dev, libtesseract-dev)"
    ))
}

/// Stub: OCR not available without 'ocr' feature
#[cfg(not(feature = "ocr"))]
#[pyfunction]
#[pyo3(signature = (_image_bytes, _lang=None))]
pub fn ocr_image_bytes(_image_bytes: &[u8], _lang: Option<&str>) -> PyResult<String> {
    Err(pyo3::exceptions::PyRuntimeError::new_err(
        "OCR not available: compile with 'ocr' feature"
    ))
}

/// Stub: OCR not available without 'ocr' feature
#[cfg(not(feature = "ocr"))]
#[pyfunction]
#[pyo3(signature = (_image_paths, _lang=None))]
pub fn ocr_images_parallel(
    _image_paths: Vec<String>,
    _lang: Option<&str>,
) -> PyResult<Vec<(String, String)>> {
    Err(pyo3::exceptions::PyRuntimeError::new_err(
        "OCR not available: compile with 'ocr' feature"
    ))
}

/// Stub: OCR not available without 'ocr' feature
#[cfg(not(feature = "ocr"))]
#[pyfunction]
#[pyo3(signature = (_images, _lang=None))]
pub fn ocr_bytes_parallel(
    _images: Vec<(String, Vec<u8>)>,
    _lang: Option<&str>,
) -> PyResult<Vec<(String, String)>> {
    Err(pyo3::exceptions::PyRuntimeError::new_err(
        "OCR not available: compile with 'ocr' feature"
    ))
}

/// Stub: OCR not available without 'ocr' feature
#[cfg(not(feature = "ocr"))]
#[pyfunction]
#[pyo3(signature = (_page_image_bytes, _page_number, _lang=None))]
pub fn ocr_pdf_page(
    _page_image_bytes: &[u8],
    _page_number: i32,
    _lang: Option<&str>,
) -> PyResult<(i32, String)> {
    Err(pyo3::exceptions::PyRuntimeError::new_err(
        "OCR not available: compile with 'ocr' feature"
    ))
}

/// Stub: OCR not available without 'ocr' feature
#[cfg(not(feature = "ocr"))]
#[pyfunction]
#[pyo3(signature = (_page_images, _lang=None))]
pub fn ocr_pdf_pages_parallel(
    _page_images: Vec<(i32, Vec<u8>)>,
    _lang: Option<&str>,
) -> PyResult<Vec<(i32, String)>> {
    Err(pyo3::exceptions::PyRuntimeError::new_err(
        "OCR not available: compile with 'ocr' feature"
    ))
}

// ============================================================================
// Feature detection function (always available)
// ============================================================================

/// Check if OCR feature is available.
#[pyfunction]
pub fn is_ocr_available() -> bool {
    cfg!(feature = "ocr")
}
