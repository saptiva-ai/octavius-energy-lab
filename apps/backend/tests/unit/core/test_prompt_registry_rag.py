"""El bloque RAG del system prompt solo entra con documentos adjuntos.

Card 2026-09-03__FEAT__follow-up-explicame-sobre-resultado-previo: con el
bloque siempre presente, "explícame" tras una consulta retail producía
`get_relevant_segments(...)` escrito como texto.
"""

import pytest

from src.core.prompt_registry import ModelParams, PromptEntry, PromptRegistry


@pytest.mark.unit
def test_rag_solo_con_documentos():
    registry = PromptRegistry()
    registry.models["default"] = PromptEntry(
        system_base=(
            "Eres {CopilotOS} de {Saptiva}.\n\n      {RAG}Herramientas disponibles\n"
            "{TOOLS}\n      * Llama herramientas cuando:"
        ),
        params=ModelParams(),
    )
    sin_docs, _ = registry.resolve(model="default", tools_markdown="* tool")
    con_docs, _ = registry.resolve(
        model="default", tools_markdown="* tool", has_documents=True
    )
    assert "get_relevant_segments" not in sin_docs
    assert "{RAG}" not in sin_docs
    assert "get_relevant_segments" in con_docs
    assert "Documentos Adjuntos" in con_docs
    # El resto del prompt (herramientas) se conserva en ambos casos.
    assert "Herramientas disponibles" in sin_docs and "* tool" in sin_docs
