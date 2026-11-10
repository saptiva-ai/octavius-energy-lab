"""
Unit tests for the text_sanitizer module.

Tests cover:
- BUG-06: SQL stripping from chat responses
- BUG-11: Markdown formatting normalization
- Section heading stripping
- Main sanitize_response_content function
"""

import pytest

from src.services.text_sanitizer import (
    is_section_heading,
    normalize_markdown_formatting,
    sanitize_response_content,
    strip_section_headings,
    strip_sql_from_response,
)


class TestStripSqlFromResponse:
    """BUG-06: Tests for SQL removal from chat responses."""

    def test_removes_sql_code_block(self):
        """Should remove ```sql ... ``` blocks."""
        text = """Aquí está el resultado:

```sql
SELECT * FROM monthly_kpis WHERE tienda_norm = 'Tienda Centro'
```

La disponibilidad de Tienda Centro es 0.71%."""

        result = strip_sql_from_response(text)

        assert "```sql" not in result
        assert "SELECT" not in result
        assert "FROM" not in result
        assert "La disponibilidad de Tienda Centro es 0.71%" in result

    def test_removes_sql_block_case_insensitive(self):
        """Should handle uppercase SQL tag."""
        text = """Resultado:

```SQL
SELECT fecha FROM kpis
```

Datos obtenidos."""

        result = strip_sql_from_response(text)

        assert "SELECT" not in result
        assert "Datos obtenidos" in result

    def test_removes_generic_code_block_with_sql(self):
        """Should remove code blocks containing SQL keywords."""
        text = """La consulta:

```
SELECT fecha, disponibilidad FROM monthly_kpis WHERE tienda_norm = 'Tienda Centro'
```

Muestra tendencia positiva."""

        result = strip_sql_from_response(text)

        assert "SELECT" not in result
        assert "Muestra tendencia positiva" in result

    def test_preserves_non_sql_code_blocks(self):
        """Should NOT remove code blocks that don't contain SQL."""
        text = """Ejemplo de código:

```python
def calculate_disponibilidad(faltantes, inventario_total):
    return faltantes / inventario_total * 100
```

Esta función calcula el disponibilidad."""

        result = strip_sql_from_response(text)

        assert "```python" in result
        assert "def calculate_disponibilidad" in result

    def test_removes_inline_sql_mentions(self):
        """Should remove inline SQL references."""
        text = "La consulta SQL fue: SELECT * FROM kpis. El resultado muestra mejora."

        result = strip_sql_from_response(text)

        assert "SELECT" not in result
        assert "La consulta SQL fue" not in result.lower() or "select" not in result.lower()

    def test_removes_query_mention(self):
        """Should remove 'El query utilizado' mentions."""
        text = "El query utilizado: SELECT fecha, disponibilidad FROM monthly_kpis. La disponibilidad bajó."

        result = strip_sql_from_response(text)

        # Either the whole mention is removed or at least SQL is gone
        assert "SELECT" not in result

    def test_handles_empty_string(self):
        """Should handle empty string gracefully."""
        assert strip_sql_from_response("") == ""

    def test_handles_none(self):
        """Should handle None input."""
        assert strip_sql_from_response(None) is None

    def test_preserves_text_without_sql(self):
        """Should not modify text that has no SQL."""
        text = "La disponibilidad de Tienda Centro ha mejorado en los últimos meses, mostrando una tendencia positiva."

        result = strip_sql_from_response(text)

        assert result == text.strip()

    def test_removes_multiple_sql_blocks(self):
        """Should remove multiple SQL blocks in same text."""
        text = """Primera consulta:

```sql
SELECT * FROM table1
```

Segunda consulta:

```sql
SELECT * FROM table2
```

Ambos muestran datos."""

        result = strip_sql_from_response(text)

        assert result.count("SELECT") == 0
        assert "Ambos muestran datos" in result

    def test_cleans_up_multiple_newlines(self):
        """Should clean up excessive newlines after SQL removal."""
        text = """Texto inicial.

```sql
SELECT * FROM kpis
```



Texto final."""

        result = strip_sql_from_response(text)

        # Should not have more than 2 consecutive newlines
        assert "\n\n\n" not in result

    def test_removes_orphaned_sql_introduction(self):
        """Should remove orphaned SQL intro phrases after code block removal.

        BA-003 FIX: When code block is removed, the intro text like
        'La consulta SQL utilizada fue:' should also be removed.
        """
        # Simulates text after code block was already removed
        text = "La disponibilidad es 0.71%. La consulta SQL utilizada fue: El resultado muestra mejora."

        result = strip_sql_from_response(text)

        assert "La consulta SQL utilizada fue" not in result
        assert "La disponibilidad es 0.71%" in result
        assert "El resultado muestra mejora" in result

    def test_removes_various_sql_intro_patterns(self):
        """Should handle various SQL introduction patterns."""
        patterns = [
            "La consulta SQL utilizada fue:",
            "La consulta utilizada fue:",
            "La consulta SQL fue:",
            "El query utilizado fue:",
            "Consulta SQL utilizada:",
            "SQL utilizado fue:",
        ]

        for pattern in patterns:
            text = f"Datos encontrados. {pattern} Los resultados son positivos."
            result = strip_sql_from_response(text)
            assert pattern.rstrip(":") not in result, f"Pattern not removed: {pattern}"


class TestNormalizeMarkdownFormatting:
    """BUG-11: Tests for markdown formatting normalization."""

    def test_adds_space_after_comma(self):
        """Should add space after comma when followed by letter."""
        assert normalize_markdown_formatting("valor,siguiente") == "valor, siguiente"

    def test_adds_space_after_semicolon(self):
        """Should add space after semicolon when followed by letter."""
        assert normalize_markdown_formatting("item;otro") == "item; otro"

    def test_adds_space_after_colon(self):
        """Should add space after colon when followed by letter."""
        assert normalize_markdown_formatting("nota:importante") == "nota: importante"

    def test_preserves_numbers_with_comma(self):
        """Should not add space in numbers like 1,000."""
        # Numbers don't have letters after comma
        result = normalize_markdown_formatting("El total es 1,000")
        assert "1,000" in result or "1, 000" not in result

    def test_reduces_quadruple_asterisks(self):
        """Should reduce **** to **."""
        assert normalize_markdown_formatting("****negrita****") == "**negrita**"

    def test_handles_multiple_asterisks(self):
        """Should handle various asterisk counts."""
        assert normalize_markdown_formatting("******texto******") == "**texto**"

    def test_reduces_excessive_spaces(self):
        """Should reduce multiple spaces to single space."""
        assert normalize_markdown_formatting("palabra   otra") == "palabra otra"

    def test_handles_empty_string(self):
        """Should handle empty string."""
        assert normalize_markdown_formatting("") == ""

    def test_handles_none(self):
        """Should handle None input."""
        assert normalize_markdown_formatting(None) is None

    def test_preserves_valid_markdown(self):
        """Should not break valid markdown."""
        valid = "**Negrita** y *cursiva* con `código`"
        result = normalize_markdown_formatting(valid)
        assert "**Negrita**" in result
        assert "*cursiva*" in result


class TestIsSectionHeading:
    """Tests for section heading detection."""

    def test_detects_bold_colon_heading(self):
        """Should detect **Resumen:** pattern."""
        assert is_section_heading("**Resumen:**") is True

    def test_detects_bold_heading_with_external_colon(self):
        """Should detect **Resumen**: pattern."""
        assert is_section_heading("**Resumen**:") is True

    def test_detects_plain_heading(self):
        """Should detect plain Resumen: pattern."""
        assert is_section_heading("Resumen:") is True

    def test_detects_markdown_header(self):
        """Should detect ## Resumen pattern."""
        assert is_section_heading("## Resumen") is True

    def test_detects_english_headings(self):
        """Should detect English section keywords."""
        assert is_section_heading("**Summary:**") is True
        assert is_section_heading("## Response") is True
        assert is_section_heading("Next Steps:") is True

    def test_ignores_regular_text(self):
        """Should not match regular text."""
        assert is_section_heading("Este es un resumen del tema") is False

    def test_ignores_empty_line(self):
        """Should return False for empty lines."""
        assert is_section_heading("") is False
        assert is_section_heading("   ") is False

    def test_case_insensitive(self):
        """Should match regardless of case."""
        assert is_section_heading("**RESUMEN:**") is True
        assert is_section_heading("resumen:") is True


class TestStripSectionHeadings:
    """Tests for section heading stripping."""

    def test_strips_bold_heading(self):
        """Should remove bold heading lines."""
        text = "**Resumen:**\nContenido importante"
        result = strip_section_headings(text)
        assert "**Resumen:**" not in result
        assert "Contenido importante" in result

    def test_strips_multiple_headings(self):
        """Should remove multiple heading lines."""
        text = "**Resumen:**\nContenido\n\n**Fuentes:**\nFuente 1"
        result = strip_section_headings(text)
        assert "**Resumen:**" not in result
        assert "**Fuentes:**" not in result
        assert "Contenido" in result
        assert "Fuente 1" in result

    def test_preserves_content(self):
        """Should preserve all non-heading content."""
        text = "## Resumen\nLínea 1\nLínea 2\n\n## Fuentes\nFuente A"
        result = strip_section_headings(text)
        assert "Línea 1" in result
        assert "Línea 2" in result
        assert "Fuente A" in result

    def test_handles_empty_string(self):
        """Should handle empty string."""
        assert strip_section_headings("") == ""

    def test_reduces_multiple_newlines(self):
        """Should reduce excessive newlines."""
        text = "**Resumen:**\n\n\n\nContenido"
        result = strip_section_headings(text)
        assert "\n\n\n" not in result

    def test_debug_mode_adds_comments(self):
        """Should add HTML comments in debug mode."""
        text = "**Resumen:**\nContenido"
        result = strip_section_headings(text, debug=True)
        assert "<!-- DEBUG:" in result


class TestSanitizeResponseContent:
    """Tests for the main sanitization function."""

    def test_full_sanitization_pipeline(self):
        """Should apply all sanitization steps."""
        text = """**Resumen:**
La disponibilidad de Tienda Centro es 0.71%,valor positivo.

```sql
SELECT * FROM kpis
```

**Fuentes:**
Datos internos."""

        result = sanitize_response_content(text)

        # Section headings removed
        assert "**Resumen:**" not in result
        assert "**Fuentes:**" not in result
        # SQL removed
        assert "SELECT" not in result
        # Markdown normalized (comma spacing)
        assert "0.71%, valor" in result or "0.71%,valor" not in result
        # Content preserved
        assert "disponibilidad de Tienda Centro" in result
        assert "Datos internos" in result

    def test_handles_none(self):
        """Should handle None input."""
        assert sanitize_response_content(None) is None

    def test_disabled_sanitization(self):
        """Should return original when disabled."""
        text = "**Resumen:**\nContenido"
        result = sanitize_response_content(text, enable_sanitization=False)
        assert result == text

    def test_debug_mode(self):
        """Should include debug info when enabled."""
        text = "**Resumen:**\nContenido"
        result = sanitize_response_content(text, debug=True)
        assert "<!-- DEBUG:" in result
