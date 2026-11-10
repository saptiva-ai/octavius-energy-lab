#!/usr/bin/env python
"""
Manual test runner for text_sanitizer module.
Run with: python tests/unit/run_text_sanitizer_tests.py
"""

import sys

from src.services.text_sanitizer import (
    is_section_heading,
    normalize_markdown_formatting,
    sanitize_response_content,
    strip_section_headings,
    strip_sql_from_response,
)

passed = 0
failed = 0


def test(name, condition, msg=""):
    global passed, failed
    if condition:
        print(f"  ✅ {name}")
        passed += 1
    else:
        print(f"  ❌ {name}: {msg}")
        failed += 1


print("=" * 60)
print("🧪 Testing strip_sql_from_response (BUG-06)")
print("=" * 60)

# Test 1: Removes SQL code block
text1 = """Aquí está el resultado:

```sql
SELECT * FROM monthly_kpis WHERE tienda_norm = 'Tienda Centro'
```

La disponibilidad de Tienda Centro es 0.71%."""
result1 = strip_sql_from_response(text1)
test(
    "Removes ```sql block",
    "SELECT" not in result1 and "disponibilidad de Tienda Centro es 0.71%" in result1,
    result1,
)

# Test 2: Case insensitive
text2 = """Resultado:
```SQL
SELECT fecha FROM kpis
```
Datos obtenidos."""
result2 = strip_sql_from_response(text2)
test(
    "Case insensitive (SQL vs sql)",
    "SELECT" not in result2 and "Datos obtenidos" in result2,
)

# Test 3: Generic code block with SQL
text3 = """La consulta:
```
SELECT fecha, disponibilidad FROM monthly_kpis WHERE tienda_norm = 'Tienda Centro'
```
Muestra tendencia positiva."""
result3 = strip_sql_from_response(text3)
test(
    "Removes generic code block with SQL",
    "SELECT" not in result3 and "tendencia positiva" in result3,
)

# Test 4: Preserves non-SQL code
text4 = """Ejemplo:
```python
def calculate_disponibilidad(faltantes, inventario_total):
    return faltantes / inventario_total * 100
```
Esta función calcula el disponibilidad."""
result4 = strip_sql_from_response(text4)
test("Preserves Python code blocks", "def calculate_disponibilidad" in result4)

# Test 5: Handles empty
test("Handles empty string", strip_sql_from_response("") == "")

# Test 6: Handles None
test("Handles None", strip_sql_from_response(None) is None)

# Test 7: Preserves text without SQL
text7 = "La disponibilidad de Tienda Centro ha mejorado en los últimos meses."
result7 = strip_sql_from_response(text7)
test("Preserves text without SQL", result7 == text7.strip())

# Test 8: Removes multiple SQL blocks
text8 = """Primera:
```sql
SELECT * FROM table1
```
Segunda:
```sql
SELECT * FROM table2
```
Ambos muestran datos."""
result8 = strip_sql_from_response(text8)
test(
    "Removes multiple SQL blocks",
    result8.count("SELECT") == 0 and "Ambos muestran datos" in result8,
)

# Test 9: Removes inline SQL mention
text9 = "La consulta SQL fue: SELECT * FROM kpis. El resultado muestra mejora."
result9 = strip_sql_from_response(text9)
test("Removes inline SQL mentions", "SELECT" not in result9)

print()
print("=" * 60)
print("🧪 Testing normalize_markdown_formatting (BUG-11)")
print("=" * 60)

test(
    "Adds space after comma",
    normalize_markdown_formatting("valor,siguiente") == "valor, siguiente",
)
test(
    "Adds space after semicolon",
    normalize_markdown_formatting("item;otro") == "item; otro",
)
test(
    "Adds space after colon",
    normalize_markdown_formatting("nota:importante") == "nota: importante",
)
test(
    "Reduces **** to **",
    normalize_markdown_formatting("****negrita****") == "**negrita**",
)
test("Handles empty", normalize_markdown_formatting("") == "")
test("Handles None", normalize_markdown_formatting(None) is None)

print()
print("=" * 60)
print("🧪 Testing is_section_heading")
print("=" * 60)

test("Detects **Resumen:**", is_section_heading("**Resumen:**") is True)
test("Detects **Resumen**:", is_section_heading("**Resumen**:") is True)
test("Detects plain Resumen:", is_section_heading("Resumen:") is True)
test("Detects ## Resumen", is_section_heading("## Resumen") is True)
test("Detects **Summary:**", is_section_heading("**Summary:**") is True)
test("Ignores regular text", is_section_heading("Este es un resumen del tema") is False)
test("Ignores empty", is_section_heading("") is False)

print()
print("=" * 60)
print("🧪 Testing sanitize_response_content (Full Pipeline)")
print("=" * 60)

text_full = """**Resumen:**
La disponibilidad de Tienda Centro es 0.71%,valor positivo.

```sql
SELECT * FROM kpis
```

**Fuentes:**
Datos internos."""

result_full = sanitize_response_content(text_full)
test("Removes **Resumen:**", "**Resumen:**" not in result_full)
test("Removes **Fuentes:**", "**Fuentes:**" not in result_full)
test("Removes SQL block", "SELECT" not in result_full)
test(
    "Preserves content",
    "disponibilidad de Tienda Centro" in result_full and "Datos internos" in result_full,
)
test(
    "Fixes comma spacing",
    "0.71%, valor" in result_full or "0.71%,valor" not in result_full,
)

# Test disabled sanitization
test(
    "Disabled returns original",
    sanitize_response_content("**Resumen:**\nTest", enable_sanitization=False)
    == "**Resumen:**\nTest",
)

# Test None handling
test("Handles None", sanitize_response_content(None) is None)

print()
print("=" * 60)
total = passed + failed
print(f"📊 Results: {passed}/{total} passed ({100*passed//total}%)")
if failed > 0:
    print(f"❌ {failed} tests FAILED")
    sys.exit(1)
else:
    print("✅ All tests PASSED!")
print("=" * 60)
