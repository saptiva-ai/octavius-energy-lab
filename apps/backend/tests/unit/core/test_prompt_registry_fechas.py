"""El prompt no ancla el año del modelo (TASK fechas-lenguaje-natural).

El simulador de usuario (2026-10-11) mostró al decide escribir "septiembre 2025
contra 2024" con datos al 2026-09-30. El prompt traía el ejemplo literal
"2025-10-03"; un ejemplo de formato no debe llevar un año concreto.
"""

import re
from pathlib import Path

import pytest

REGISTRO = Path(__file__).resolve().parents[3] / "prompts" / "registry.yaml"


@pytest.mark.unit
def test_prompt_sin_fechas_literales_de_ejemplo():
    texto = REGISTRO.read_text(encoding="utf-8")
    assert not re.search(r"\b20\d{2}-\d{2}-\d{2}\b", texto)
    assert "{CURRENT_DATE}" in texto
