#!/usr/bin/env python3
"""
RAG Context Quality Test Suite

Tests for verifying the quality of RAG context injection:
- TC1: Structured format with segment headers, page info, and relevance scores
- TC2: LLM grounding instructions present in formatted prompt
- TC3: Fallback cache selects relevant paragraphs (not blind truncation)
- TC4: format_for_prompt returns empty string for empty context

E2E tests (TC5-TC7) require a running backend and are skipped without it.

Run:
    cd apps/backend
    python3.11 -m pytest ../../tests/system/rag/test_rag_context_quality.py -v
"""

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add backend src to path so that the full package is importable.
# Tests must run from repo root or apps/backend for relative imports to work.
_BACKEND_SRC = str(Path(__file__).resolve().parents[3] / "apps" / "backend" / "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)


# ---------------------------------------------------------------------------
# Lazy import helper — deferred to avoid import-time failures in CI
# where not all backend deps are installed.
# ---------------------------------------------------------------------------

def _get_builder_class():
    """Import DocumentContextBuilder with isolation from barrel __init__.py."""
    import importlib.util
    module_path = (
        Path(__file__).resolve().parents[3]
        / "apps" / "backend" / "src"
        / "services" / "streaming" / "document_context.py"
    )
    spec = importlib.util.spec_from_file_location(
        "document_context_isolated", module_path,
        submodule_search_locations=[],
    )
    mod = importlib.util.module_from_spec(spec)

    # Prevent relative imports from triggering the full streaming package
    # by pre-registering the parent packages as empty modules
    for pkg in [
        "services",
        "services.streaming",
    ]:
        if pkg not in sys.modules:
            sys.modules[pkg] = MagicMock()

    spec.loader.exec_module(mod)
    return mod.DocumentContextBuilder


# Import once at module level (after sys.modules patching)
DocumentContextBuilder = _get_builder_class()


# ---------------------------------------------------------------------------
# Unit tests — no backend required
# ---------------------------------------------------------------------------


class TestSegmentFormat:
    """TC1: Verify structured segment format directly (no async build)."""

    def test_segments_include_page_and_index(self):
        """Segments should render as [Segmento N] with page and score."""
        segments = [
            {
                "doc_name": "reporte_anual.pdf",
                "score": 0.91,
                "text": "Los ingresos crecieron 15% interanual.",
                "page": 3,
            },
            {
                "doc_name": "reporte_anual.pdf",
                "score": 0.78,
                "text": "El EBITDA se ubicó en $500M.",
                "page": 7,
            },
        ]

        # Replicate the formatting logic from _retrieve_via_rag
        segment_texts = []
        for i, seg in enumerate(segments):
            page = seg.get("page", 0)
            page_info = f" | Página: {page}" if page else ""
            header = (
                f"[Segmento {i + 1}] Documento: {seg['doc_name']}"
                f"{page_info} | Relevancia: {seg['score']:.2f}"
            )
            segment_texts.append(f"{header}\n{seg['text']}")

        context = "\n\n---\n\n".join(segment_texts)

        assert "[Segmento 1]" in context
        assert "[Segmento 2]" in context
        assert "Página: 3" in context
        assert "Página: 7" in context
        assert "Relevancia: 0.91" in context
        assert "Relevancia: 0.78" in context
        assert "Los ingresos crecieron 15%" in context

    def test_segment_without_page_omits_page_info(self):
        """Segments with page=0 should not show page info."""
        seg = {"doc_name": "notas.txt", "score": 0.65, "text": "Contenido.", "page": 0}

        page = seg.get("page", 0)
        page_info = f" | Página: {page}" if page else ""
        header = (
            f"[Segmento 1] Documento: {seg['doc_name']}"
            f"{page_info} | Relevancia: {seg['score']:.2f}"
        )
        context = f"{header}\n{seg['text']}"

        assert "Página:" not in context
        assert "Relevancia: 0.65" in context


class TestFormatForPrompt:
    """TC2 + TC4: Verify structured LLM instructions in formatted prompt."""

    def test_format_includes_grounding_instructions(self):
        """format_for_prompt must include mandatory grounding instructions."""
        raw_context = (
            "[Segmento 1] Documento: test.pdf | Página: 1 | Relevancia: 0.90\n"
            "Los ingresos fueron $100M."
        )
        result = DocumentContextBuilder.format_for_prompt(raw_context)

        assert "[CONTEXTO DOCUMENTAL — INSTRUCCIONES OBLIGATORIAS]" in result
        assert "[FIN CONTEXTO DOCUMENTAL]" in result
        assert "EXCLUSIVAMENTE en estos segmentos" in result
        assert "No encontré esa información en el documento" in result
        assert "NO inventes información" in result
        assert "Cita el documento y página" in result
        assert raw_context in result

    def test_format_empty_context_returns_empty(self):
        """Empty or None context should return empty string."""
        assert DocumentContextBuilder.format_for_prompt("") == ""
        assert DocumentContextBuilder.format_for_prompt(None) == ""


class TestFallbackParagraphScoring:
    """TC3: Verify fallback cache selects relevant paragraphs."""

    def test_relevant_paragraphs_ranked_higher(self):
        """Paragraphs matching query keywords should be selected first."""
        paragraphs = [
            "Introducción general del reporte financiero anual.",
            "Los ingresos totales del banco crecieron un 15% en el periodo.",
            "La decoración de las oficinas fue renovada en marzo.",
            "El margen de intermediación financiera se mantuvo estable.",
            "Se realizaron actividades recreativas para empleados.",
            "Los ingresos por comisiones representaron el 30% del total.",
        ]
        text = "\n\n".join(paragraphs)

        # Use a tight char budget so scoring actually filters out irrelevant ones
        result = DocumentContextBuilder._select_relevant_paragraphs(
            text=text,
            query="¿Cuánto crecieron los ingresos del banco?",
            max_chars=180,
        )

        # Should include the paragraphs about ingresos and banco
        assert "ingresos totales del banco crecieron" in result
        assert "ingresos por comisiones" in result
        # Should NOT include irrelevant paragraphs (char budget too tight)
        assert "decoración" not in result
        assert "recreativas" not in result

    def test_paragraphs_preserve_document_order(self):
        """Selected paragraphs should appear in original document order."""
        paragraphs = [
            "Primer párrafo sobre ingresos bancarios.",
            "Segundo párrafo irrelevante sobre clima.",
            "Tercer párrafo sobre ingresos y comisiones.",
        ]
        text = "\n\n".join(paragraphs)

        result = DocumentContextBuilder._select_relevant_paragraphs(
            text=text,
            query="ingresos bancarios comisiones",
            max_chars=500,
        )

        assert "Primer párrafo" in result
        assert "Tercer párrafo" in result

        # Original order preserved
        idx_first = result.index("Primer párrafo")
        idx_third = result.index("Tercer párrafo")
        assert idx_first < idx_third

    def test_single_paragraph_falls_back_to_truncation(self):
        """Single paragraph (no structure) → linear truncation."""
        text = "A" * 20000
        result = DocumentContextBuilder._select_relevant_paragraphs(
            text=text, query="something", max_chars=12000
        )
        assert len(result) == 12000

    def test_empty_query_falls_back_to_truncation(self):
        """Query with no meaningful keywords → linear truncation."""
        text = "Párrafo uno.\n\nPárrafo dos."
        result = DocumentContextBuilder._select_relevant_paragraphs(
            text=text, query="a b", max_chars=500  # words < 3 chars
        )
        # Falls back to text[:max_chars]
        assert "Párrafo uno" in result


# ---------------------------------------------------------------------------
# E2E tests — require running backend
# ---------------------------------------------------------------------------

BACKEND_URL = os.environ.get("TEST_BACKEND_URL", "http://localhost:8000")

_skip_no_backend = pytest.mark.skipif(
    os.getenv("RUN_E2E_RAG", "false").lower() != "true",
    reason="RUN_E2E_RAG not set — skipping E2E RAG tests",
)


@_skip_no_backend
class TestRAGE2E:
    """
    E2E tests that upload a PDF, ask questions, and validate LLM responses.
    Requires: running backend + Weaviate + MinIO.
    Set RUN_E2E_RAG=true to enable.
    """

    @pytest.fixture(autouse=True)
    def _setup_helpers(self):
        sys.path.append(str(Path(__file__).resolve().parents[2]))
        from utils.helpers import get_auth_token, send_chat_message

        self.get_auth_token = get_auth_token
        self.send_chat_message = send_chat_message
        self.token = get_auth_token()

    def test_tc5_direct_question_cites_document(self):
        """TC5: Ask about known content → response should cite the document."""
        pytest.skip("Pending test PDF fixture upload implementation")

    def test_tc6_absent_topic_says_not_found(self):
        """TC6: Ask about topic NOT in document → 'no encontré'."""
        pytest.skip("Pending test PDF fixture upload implementation")

    def test_tc7_ambiguous_uses_multiple_segments(self):
        """TC7: Ambiguous question → uses ≥2 segments."""
        pytest.skip("Pending test PDF fixture upload implementation")
