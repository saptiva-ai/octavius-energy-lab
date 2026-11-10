//! Text quality validation module.
//!
//! Provides fast text quality metrics and validation for extracted text.
//! Uses regex crate for ~10x speedup over Python re module.

use pyo3::prelude::*;
use regex::Regex;
use std::sync::LazyLock;
use unicode_segmentation::UnicodeSegmentation;

/// Regex for matching words (including Spanish characters)
static WORD_REGEX: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"[a-zA-ZáéíóúÁÉÍÓÚñÑüÜ]{2,}").expect("Invalid word regex")
});

/// Regex for matching gibberish patterns (consecutive special chars)
/// Note: backreferences not supported in Rust regex, so we detect special char sequences
static GIBBERISH_REGEX: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"[^\w\s]{5,}").expect("Invalid gibberish regex")
});

/// Quality metrics for extracted text.
#[pyclass(from_py_object)]
#[derive(Clone, Debug)]
pub struct QualityMetrics {
    /// Total character count
    #[pyo3(get)]
    pub char_count: usize,

    /// Alphanumeric character count
    #[pyo3(get)]
    pub alphanumeric_count: usize,

    /// Whitespace character count
    #[pyo3(get)]
    pub whitespace_count: usize,

    /// Special character count
    #[pyo3(get)]
    pub special_count: usize,

    /// Word count (2+ letter sequences)
    #[pyo3(get)]
    pub word_count: usize,

    /// Quality ratio (alphanumeric / total)
    #[pyo3(get)]
    pub quality_ratio: f64,

    /// Special character ratio
    #[pyo3(get)]
    pub special_ratio: f64,

    /// Whether gibberish patterns were detected
    #[pyo3(get)]
    pub has_gibberish: bool,

    /// Overall quality assessment
    #[pyo3(get)]
    pub is_sufficient: bool,
}

#[pymethods]
impl QualityMetrics {
    fn __repr__(&self) -> String {
        format!(
            "QualityMetrics(chars={}, words={}, quality={:.2}, sufficient={})",
            self.char_count, self.word_count, self.quality_ratio, self.is_sufficient
        )
    }

    fn __str__(&self) -> String {
        self.__repr__()
    }
}

/// Calculate the quality ratio (alphanumeric / total characters).
///
/// # Arguments
/// * `text` - Text to analyze
///
/// # Returns
/// Ratio between 0.0 and 1.0
#[pyfunction]
pub fn calculate_char_ratio(text: &str) -> f64 {
    calculate_quality_ratio(text)
}

/// Internal function for quality ratio calculation.
pub fn calculate_quality_ratio(text: &str) -> f64 {
    if text.is_empty() {
        return 0.0;
    }

    let total = text.chars().count();
    let alphanumeric = text.chars().filter(|c| c.is_alphanumeric()).count();

    if total == 0 {
        0.0
    } else {
        alphanumeric as f64 / total as f64
    }
}

/// Count words in text (sequences of 2+ letters).
///
/// # Arguments
/// * `text` - Text to analyze
///
/// # Returns
/// Number of words found
#[pyfunction]
pub fn count_words(text: &str) -> usize {
    WORD_REGEX.find_iter(text).count()
}

/// Check if extracted text has sufficient quality.
///
/// Validates text quality to prevent using corrupted text from
/// scanned PDFs with hidden text layers.
///
/// # Arguments
/// * `text` - Text to validate
/// * `min_chars` - Minimum character count (default: 150)
/// * `min_quality_ratio` - Minimum quality ratio (default: 0.4)
/// * `min_words` - Minimum word count (default: 5)
/// * `max_special_ratio` - Maximum special character ratio (default: 0.8)
///
/// # Returns
/// True if text quality is sufficient
#[pyfunction]
#[pyo3(signature = (text, min_chars=150, min_quality_ratio=0.4, min_words=5, max_special_ratio=0.8))]
pub fn is_quality_sufficient(
    text: &str,
    min_chars: usize,
    min_quality_ratio: f64,
    min_words: usize,
    max_special_ratio: f64,
) -> bool {
    let metrics = compute_metrics(text, min_chars, min_quality_ratio, min_words, max_special_ratio);
    metrics.is_sufficient
}

/// Get comprehensive quality metrics for text.
///
/// # Arguments
/// * `text` - Text to analyze
/// * `min_chars` - Minimum character count threshold
/// * `min_quality_ratio` - Minimum quality ratio threshold
/// * `min_words` - Minimum word count threshold
/// * `max_special_ratio` - Maximum special character ratio threshold
///
/// # Returns
/// QualityMetrics with detailed analysis
#[pyfunction]
#[pyo3(signature = (text, min_chars=150, min_quality_ratio=0.4, min_words=5, max_special_ratio=0.8))]
pub fn get_quality_metrics(
    text: &str,
    min_chars: usize,
    min_quality_ratio: f64,
    min_words: usize,
    max_special_ratio: f64,
) -> QualityMetrics {
    compute_metrics(text, min_chars, min_quality_ratio, min_words, max_special_ratio)
}

/// Compute all quality metrics for text.
fn compute_metrics(
    text: &str,
    min_chars: usize,
    min_quality_ratio: f64,
    min_words: usize,
    max_special_ratio: f64,
) -> QualityMetrics {
    let text_clean = text.trim();

    // Basic counts
    let char_count = text_clean.chars().count();
    let alphanumeric_count = text_clean.chars().filter(|c| c.is_alphanumeric()).count();
    let whitespace_count = text_clean.chars().filter(|c| c.is_whitespace()).count();
    let special_count = char_count.saturating_sub(alphanumeric_count + whitespace_count);

    // Ratios
    let quality_ratio = if char_count > 0 {
        alphanumeric_count as f64 / char_count as f64
    } else {
        0.0
    };

    let special_ratio = if char_count > 0 {
        special_count as f64 / char_count as f64
    } else {
        0.0
    };

    // Word count using regex
    let word_count = WORD_REGEX.find_iter(text_clean).count();

    // Gibberish detection
    let has_gibberish = GIBBERISH_REGEX.is_match(text_clean);

    // Quality assessment
    let is_sufficient = !text_clean.is_empty()
        && char_count >= min_chars
        && quality_ratio >= min_quality_ratio
        && word_count >= min_words
        && special_ratio <= max_special_ratio
        && !has_gibberish;

    QualityMetrics {
        char_count,
        alphanumeric_count,
        whitespace_count,
        special_count,
        word_count,
        quality_ratio,
        special_ratio,
        has_gibberish,
        is_sufficient,
    }
}

/// Detect the primary language of text (simple heuristic).
///
/// # Arguments
/// * `text` - Text to analyze
///
/// # Returns
/// Language code: "es" for Spanish, "en" for English, "unknown" otherwise
#[pyfunction]
pub fn detect_language(text: &str) -> &'static str {
    let lower = text.to_lowercase();

    // Spanish indicators
    let spanish_words = ["el", "la", "de", "que", "en", "los", "las", "por", "con", "para"];
    let spanish_count: usize = spanish_words
        .iter()
        .map(|w| lower.matches(&format!(" {} ", w)).count())
        .sum();

    // English indicators
    let english_words = ["the", "of", "and", "to", "in", "is", "for", "on", "with", "that"];
    let english_count: usize = english_words
        .iter()
        .map(|w| lower.matches(&format!(" {} ", w)).count())
        .sum();

    // Spanish-specific characters
    let spanish_chars = lower.chars().filter(|c| "áéíóúñü¿¡".contains(*c)).count();

    if spanish_count > english_count || spanish_chars > 5 {
        "es"
    } else if english_count > spanish_count {
        "en"
    } else {
        "unknown"
    }
}

/// Count grapheme clusters (user-perceived characters).
///
/// This handles multi-codepoint characters like emojis correctly.
///
/// # Arguments
/// * `text` - Text to analyze
///
/// # Returns
/// Number of grapheme clusters
#[pyfunction]
pub fn count_graphemes(text: &str) -> usize {
    text.graphemes(true).count()
}

/// Clean text by removing excessive whitespace and control characters.
///
/// # Arguments
/// * `text` - Text to clean
///
/// # Returns
/// Cleaned text
#[pyfunction]
pub fn clean_text(text: &str) -> String {
    let mut result = String::with_capacity(text.len());
    let mut prev_whitespace = false;

    for c in text.chars() {
        if c.is_whitespace() {
            if !prev_whitespace {
                result.push(' ');
                prev_whitespace = true;
            }
        } else if c.is_control() {
            // Skip control characters except newlines
            if c == '\n' && !prev_whitespace {
                result.push('\n');
                prev_whitespace = true;
            }
        } else {
            result.push(c);
            prev_whitespace = false;
        }
    }

    result.trim().to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_quality_ratio() {
        assert_eq!(calculate_quality_ratio(""), 0.0);
        assert!(calculate_quality_ratio("abc123") > 0.9);
        assert!(calculate_quality_ratio("!!!!!") < 0.1);
    }

    #[test]
    fn test_word_count() {
        assert_eq!(count_words("hello world"), 2);
        assert_eq!(count_words("a b c"), 0); // Single letters don't count
        assert_eq!(count_words("hello, world!"), 2);
    }

    #[test]
    fn test_is_quality_sufficient() {
        let good_text = "This is a sample text with enough alphanumeric characters \
                         to pass the quality check. It contains multiple words and \
                         sentences that should be considered valid extracted text.";
        assert!(is_quality_sufficient(good_text, 50, 0.4, 5, 0.8));

        assert!(!is_quality_sufficient("", 10, 0.4, 5, 0.8));
        assert!(!is_quality_sufficient("short", 50, 0.4, 5, 0.8));
    }

    #[test]
    fn test_detect_language() {
        assert_eq!(detect_language("the quick brown fox"), "en");
        assert_eq!(detect_language("el rápido zorro marrón"), "es");
    }

    #[test]
    fn test_clean_text() {
        assert_eq!(clean_text("hello   world"), "hello world");
        assert_eq!(clean_text("  trim  me  "), "trim me");
    }
}
