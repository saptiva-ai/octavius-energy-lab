"""
Unit tests for text_sanitizer module.

Tests text sanitization functions:
- Section heading detection and removal
- Markdown normalization
- SQL block stripping
- Full response sanitization
"""

import pytest

from src.services.text_sanitizer import (
    ALL_SECTION_KEYWORDS,
    SECTION_KEYWORDS_EN,
    SECTION_KEYWORDS_ES,
    is_section_heading,
    normalize_markdown_formatting,
    sanitize_response_content,
    strip_section_headings,
    strip_sql_from_response,
)

pytestmark = [pytest.mark.unit]


class TestSectionKeywords:
    """Test section keyword constants."""

    def test_spanish_keywords_not_empty(self):
        """Test Spanish section keywords are defined."""
        assert len(SECTION_KEYWORDS_ES) > 0

    def test_english_keywords_not_empty(self):
        """Test English section keywords are defined."""
        assert len(SECTION_KEYWORDS_EN) > 0

    def test_all_keywords_combined(self):
        """Test all keywords is combination of ES and EN."""
        assert set(ALL_SECTION_KEYWORDS) == set(SECTION_KEYWORDS_ES + SECTION_KEYWORDS_EN)


class TestIsSectionHeading:
    """Test is_section_heading function."""

    @pytest.mark.parametrize(
        "heading",
        [
            "**Resumen:**",
            "**Resumen**:",
            "Resumen:",
            "## Resumen",
            "## Resumen:",
            "**Summary:**",
            "Summary:",
            "  **Resumen:**  ",  # With spaces
            "### Fuentes",
            "**Referencias**",
            "Siguientes pasos:",
        ],
    )
    def test_recognizes_section_headings(self, heading):
        """Test various heading formats are recognized."""
        assert is_section_heading(heading) is True

    @pytest.mark.parametrize(
        "text",
        [
            "El resumen es interesante",  # Word in context
            "Aquí hay un summary completo",
            "Este es contenido normal",
            "123 números",
            "La respuesta fue correcta",  # Contains keyword but not a heading
        ],
    )
    def test_does_not_match_content(self, text):
        """Test regular content is not matched as heading."""
        assert is_section_heading(text) is False

    def test_empty_line(self):
        """Test empty line is not a heading."""
        assert is_section_heading("") is False
        assert is_section_heading("   ") is False

    def test_case_insensitive(self):
        """Test matching is case insensitive."""
        assert is_section_heading("RESUMEN:") is True
        assert is_section_heading("resumen:") is True
        assert is_section_heading("Resumen:") is True


class TestStripSectionHeadings:
    """Test strip_section_headings function."""

    def test_removes_simple_heading(self):
        """Test removal of simple heading."""
        text = "**Resumen:**\nContenido importante"
        result = strip_section_headings(text)

        assert "**Resumen:**" not in result
        assert "Contenido importante" in result

    def test_removes_multiple_headings(self):
        """Test removal of multiple headings."""
        text = "**Resumen:**\nContenido 1\n\n**Fuentes:**\nFuente 1"
        result = strip_section_headings(text)

        assert "**Resumen:**" not in result
        assert "**Fuentes:**" not in result
        assert "Contenido 1" in result
        assert "Fuente 1" in result

    def test_preserves_content(self):
        """Test content is preserved."""
        text = "## Resumen\nEste es un texto importante.\n\nMás contenido aquí."
        result = strip_section_headings(text)

        assert "## Resumen" not in result
        assert "Este es un texto importante." in result
        assert "Más contenido aquí." in result

    def test_empty_input(self):
        """Test empty input returns empty."""
        assert strip_section_headings("") == ""
        assert strip_section_headings(None) is None

    def test_no_headings(self):
        """Test text without headings is unchanged."""
        text = "Este es un texto normal sin encabezados."
        result = strip_section_headings(text)

        assert result == text

    def test_collapses_multiple_newlines(self):
        """Test multiple newlines are collapsed."""
        text = "**Resumen:**\n\n\n\nContenido"
        result = strip_section_headings(text)

        # Should not have more than 2 consecutive newlines
        assert "\n\n\n" not in result

    def test_debug_mode(self):
        """Test debug mode adds HTML comments."""
        text = "**Resumen:**\nContenido"
        result = strip_section_headings(text, debug=True)

        assert "<!-- DEBUG:" in result
        assert "Removed headings" in result


class TestNormalizeMarkdownFormatting:
    """Test normalize_markdown_formatting function."""

    def test_adds_space_after_comma(self):
        """Test space is added after comma before letter."""
        assert normalize_markdown_formatting("valor,siguiente") == "valor, siguiente"

    def test_adds_space_after_semicolon(self):
        """Test space is added after semicolon before letter."""
        assert normalize_markdown_formatting("item;otro") == "item; otro"

    def test_adds_space_after_colon(self):
        """Test space is added after colon before letter."""
        assert normalize_markdown_formatting("etiqueta:valor") == "etiqueta: valor"

    def test_preserves_numbers_with_commas(self):
        """Test numbers like 1,000 are preserved."""
        text = "El valor es 1,000"
        result = normalize_markdown_formatting(text)
        # Should not add space in 1,000 since 0 is not a letter
        assert "1,000" in result

    def test_reduces_excessive_asterisks(self):
        """Test ****text**** becomes **text**."""
        assert normalize_markdown_formatting("****duplicado****") == "**duplicado**"

    def test_reduces_many_asterisks(self):
        """Test more than 4 asterisks are reduced."""
        assert normalize_markdown_formatting("********") == "**"

    def test_reduces_excessive_spaces(self):
        """Test multiple spaces are reduced to one."""
        assert normalize_markdown_formatting("texto    con    espacios") == "texto con espacios"

    def test_empty_input(self):
        """Test empty input returns empty."""
        assert normalize_markdown_formatting("") == ""
        assert normalize_markdown_formatting(None) is None

    def test_handles_spanish_characters(self):
        """Test Spanish characters are handled correctly."""
        result = normalize_markdown_formatting("fecha,día")
        assert result == "fecha, día"


class TestStripSqlFromResponse:
    """Test strip_sql_from_response function."""

    def test_removes_sql_code_block(self):
        """Test SQL code blocks are removed."""
        text = "Resultado:\n```sql\nSELECT * FROM tabla\n```\nFin."
        result = strip_sql_from_response(text)

        assert "SELECT" not in result
        assert "Resultado:" in result
        assert "Fin." in result

    def test_removes_generic_sql_block(self):
        """Test generic code blocks with SQL are removed."""
        text = "Aquí:\n```\nSELECT id FROM users WHERE active = 1\n```\nListo."
        result = strip_sql_from_response(text)

        assert "SELECT" not in result
        assert "Listo." in result

    def test_preserves_non_sql_code_blocks(self):
        """Test non-SQL code blocks are preserved."""
        text = "Código:\n```python\nprint('hello')\n```\nFin."
        result = strip_sql_from_response(text)

        assert "print('hello')" in result

    def test_removes_inline_sql_mentions(self):
        """Test inline SQL mentions are removed."""
        text = "La consulta SQL fue: SELECT * FROM tabla. El resultado fue bueno."
        result = strip_sql_from_response(text)

        assert "SELECT" not in result

    def test_empty_input(self):
        """Test empty input returns empty."""
        assert strip_sql_from_response("") == ""
        assert strip_sql_from_response(None) is None

    def test_no_sql(self):
        """Test text without SQL is unchanged."""
        text = "Este es un texto normal sin consultas."
        result = strip_sql_from_response(text)

        assert result == text


class TestSanitizeResponseContent:
    """Test sanitize_response_content main function."""

    def test_full_sanitization(self):
        """Test full sanitization pipeline."""
        content = "**Resumen:**\nHola mundo"
        result = sanitize_response_content(content)

        assert "**Resumen:**" not in result
        assert "Hola mundo" in result

    def test_none_input(self):
        """Test None input returns None."""
        assert sanitize_response_content(None) is None

    def test_disabled_sanitization(self):
        """Test sanitization can be disabled."""
        content = "**Resumen:**\nTexto"
        result = sanitize_response_content(content, enable_sanitization=False)

        assert result == content  # Unchanged

    def test_debug_mode(self):
        """Test debug mode is passed through."""
        content = "**Resumen:**\nTexto"
        result = sanitize_response_content(content, debug=True)

        assert "<!-- DEBUG:" in result

    def test_combines_all_sanitization(self):
        """Test all sanitization steps are combined."""
        content = "**Resumen:**\nvalor,sin espacio\n```sql\nSELECT 1\n```\nFin"
        result = sanitize_response_content(content)

        # Heading removed
        assert "**Resumen:**" not in result
        # Space added after comma
        assert "valor, sin" in result
        # SQL removed
        assert "SELECT" not in result
        # Content preserved
        assert "Fin" in result

    def test_normalizes_markdown_first(self):
        """Test markdown normalization happens before other steps."""
        content = "****bold****"
        result = sanitize_response_content(content)

        assert "****" not in result
        assert "**bold**" in result
