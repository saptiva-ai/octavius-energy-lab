//! Error types for document processing.
//!
//! Provides consistent error handling across all Rust modules
//! with automatic conversion to Python exceptions.

use pyo3::exceptions::{PyIOError, PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use thiserror::Error;

/// Document processing errors
#[derive(Error, Debug)]
pub enum ProcessingError {
    #[error("PDF parsing error: {0}")]
    PdfParse(String),

    #[error("OCR error: {0}")]
    Ocr(String),

    #[error("Image processing error: {0}")]
    Image(String),

    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),

    #[error("Invalid input: {0}")]
    InvalidInput(String),

    #[error("Unsupported format: {0}")]
    UnsupportedFormat(String),
}

impl From<ProcessingError> for PyErr {
    fn from(err: ProcessingError) -> PyErr {
        match err {
            ProcessingError::PdfParse(msg) => PyValueError::new_err(msg),
            ProcessingError::Ocr(msg) => PyRuntimeError::new_err(msg),
            ProcessingError::Image(msg) => PyRuntimeError::new_err(msg),
            ProcessingError::Io(e) => PyIOError::new_err(e.to_string()),
            ProcessingError::InvalidInput(msg) => PyValueError::new_err(msg),
            ProcessingError::UnsupportedFormat(msg) => PyValueError::new_err(msg),
        }
    }
}

/// Result type alias for document processing operations
pub type ProcessingResult<T> = Result<T, ProcessingError>;
