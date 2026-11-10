"""
Document Context Builder Service.

Extracted from streaming_handler.py for better testability.
Handles RAG document retrieval and context building for LLM prompts.

REFACTOR-001: Phase 2 extraction.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import structlog

logger = structlog.get_logger(__name__)


class DocumentContextBuilder:
    """
    Service for building document context via RAG retrieval.

    Responsibilities:
        - Retrieve relevant segments via GetRelevantSegmentsTool
        - Fallback to full document text from cache
        - Track document processing status
        - Build formatted context string for LLM
    """

    def __init__(
        self,
        max_segments: int = 5,
        max_text_chars: int = 12000,
    ):
        """
        Initialize DocumentContextBuilder.

        Args:
            max_segments: Maximum number of segments to retrieve from RAG
            max_text_chars: Maximum characters per document in fallback mode
        """
        self.max_segments = max_segments
        self.max_text_chars = max_text_chars

    async def build(
        self,
        document_ids: List[str],
        session_id: str,
        user_id: str,
        question: str,
    ) -> Tuple[Optional[str], List[str]]:
        """
        Build document context from attached documents.

        Uses semantic retrieval (GetRelevantSegmentsTool) with fallback
        to full document text from Redis/MongoDB cache.

        Args:
            document_ids: List of document IDs to retrieve context from
            session_id: Session/conversation ID for RAG retrieval
            user_id: User ID for cache access
            question: User's question for semantic matching

        Returns:
            Tuple of (context_string, warnings_list)
            - context_string: Formatted document context or None if no documents
            - warnings_list: List of warning messages (e.g., "Documents processing")
        """
        if not document_ids:
            return None, []

        logger.info(
            "📚 [DOC CONTEXT] Starting document context retrieval",
            session_id=session_id,
            document_count=len(document_ids),
            question_preview=question[:100] if question else "",
        )

        warnings: List[str] = []

        try:
            # Try semantic retrieval first
            context = await self._retrieve_via_rag(
                session_id=session_id,
                question=question,
                warnings=warnings,
            )

            if context:
                return context, warnings

            # Fallback to cache if RAG returns no segments
            context = await self._retrieve_from_cache(
                document_ids=document_ids,
                user_id=user_id,
                session_id=session_id,
                question=question,
                warnings=warnings,
            )

            return context, warnings

        except Exception as exc:
            logger.error(
                "❌ [DOC CONTEXT] Document retrieval failed",
                error=str(exc),
                exc_type=type(exc).__name__,
                document_ids=document_ids,
            )
            warnings.append(
                f"No se pudieron cargar los documentos adjuntos: {str(exc)[:100]}"
            )
            return None, warnings

    async def _retrieve_via_rag(
        self,
        session_id: str,
        question: str,
        warnings: List[str],
    ) -> Optional[str]:
        """Retrieve document segments via GetRelevantSegmentsTool."""
        try:
            # Import here to avoid circular imports
            from ...mcp_integration.tools.get_segments import GetRelevantSegmentsTool

            logger.info(
                "[RAG] Starting GetRelevantSegmentsTool",
                conversation_id=session_id,
            )

            get_segments_tool = GetRelevantSegmentsTool()
            segments_result = await get_segments_tool.execute(
                payload={
                    "conversation_id": session_id,
                    "question": question,
                    "max_segments": self.max_segments,
                }
            )

            segments = segments_result.get("segments", [])

            if segments:
                # Build context from retrieved segments with structured format
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

                logger.info(
                    "✅ [RAG] Segments retrieved successfully",
                    session_id=session_id,
                    segments_count=len(segments),
                    ready_docs=segments_result.get("ready_docs", 0),
                    total_docs=segments_result.get("total_docs", 0),
                )

                return context

            # No segments - check if documents are still processing
            message = segments_result.get("message", "")
            if "procesando" in message.lower() or "processing" in message.lower():
                warning_msg = "⏳ Los documentos se están procesando. Estarán disponibles en breve."
                warnings.append(warning_msg)
                logger.warning(
                    "⚠️ [RAG] Documents still processing",
                    session_id=session_id,
                    total_docs=segments_result.get("total_docs", 0),
                    ready_docs=segments_result.get("ready_docs", 0),
                )

            logger.info(
                "🔄 [RAG] No segments from Weaviate, will try fallback",
                session_id=session_id,
            )
            return None

        except Exception as rag_exc:
            logger.error(
                "❌ [RAG] Segment retrieval failed",
                error=str(rag_exc),
                exc_type=type(rag_exc).__name__,
            )
            # Don't add warning here - will try fallback
            return None

    async def _retrieve_from_cache(
        self,
        document_ids: List[str],
        user_id: str,
        session_id: str,
        question: str,
        warnings: List[str],
    ) -> Optional[str]:
        """Fallback: retrieve document text from Redis/MongoDB cache.

        Instead of truncating linearly, scores paragraphs by keyword overlap
        with the user query and selects the most relevant ones.
        """
        try:
            # Import here to avoid circular imports
            from ...services.document_service import DocumentService

            logger.info(
                "🔄 [CACHE FALLBACK] Loading document text from cache",
                session_id=session_id,
                document_ids=document_ids,
            )

            doc_texts = await DocumentService.get_document_text_from_cache(
                document_ids=document_ids,
                user_id=user_id,
            )

            if not doc_texts:
                logger.warning(
                    "⚠️ [CACHE FALLBACK] No documents found in cache",
                    session_id=session_id,
                )
                return None

            segment_texts = []
            for doc_id, doc_data in doc_texts.items():
                text = doc_data.get("text", "")
                filename = doc_data.get("filename", doc_id)
                if not text:
                    continue

                # Score paragraphs by relevance instead of blind truncation
                selected_text = self._select_relevant_paragraphs(
                    text, question, self.max_text_chars
                )
                segment_texts.append(
                    f"[Fallback] Documento: {filename}\n{selected_text}"
                )

            if not segment_texts:
                logger.warning(
                    "⚠️ [CACHE FALLBACK] Documents in cache but no extractable text",
                    session_id=session_id,
                )
                return None

            context = "\n\n---\n\n".join(segment_texts)

            logger.info(
                "✅ [CACHE FALLBACK] Successfully loaded document text",
                session_id=session_id,
                docs_loaded=len(segment_texts),
                total_chars=len(context),
            )

            return context

        except Exception as cache_exc:
            logger.error(
                "❌ [CACHE FALLBACK] Failed to load documents from cache",
                error=str(cache_exc),
                exc_type=type(cache_exc).__name__,
                session_id=session_id,
            )
            return None

    @staticmethod
    def _select_relevant_paragraphs(
        text: str, query: str, max_chars: int, max_paragraphs: int = 50
    ) -> str:
        """Select the most query-relevant paragraphs within a char budget.

        Splits text into paragraphs, scores each by keyword overlap with the
        query, then picks the top-scoring ones up to *max_chars*. Paragraphs
        are returned in their original document order so the context reads
        naturally.

        Args:
            text: Full document text.
            query: User question for relevance scoring.
            max_chars: Character budget for the output.
            max_paragraphs: Cap on paragraphs to evaluate (keeps O(n) fast).

        Returns:
            Concatenated relevant paragraphs (or linear truncation as fallback).
        """
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

        # Not enough structure to score — fall back to linear truncation
        if len(paragraphs) <= 1:
            return text[:max_chars]

        # Cap evaluation to keep scoring lightweight
        paragraphs = paragraphs[:max_paragraphs]

        # Build query keyword set (lowercase, words ≥ 3 chars)
        query_words = {w for w in query.lower().split() if len(w) >= 3}

        if not query_words:
            # No meaningful keywords — linear truncation
            return text[:max_chars]

        # Score each paragraph by keyword overlap ratio
        scored: List[Tuple[int, float, str]] = []
        for idx, para in enumerate(paragraphs):
            para_lower = para.lower()
            hits = sum(1 for w in query_words if w in para_lower)
            score = hits / len(query_words)
            scored.append((idx, score, para))

        # Sort by score descending, then restore original order for top picks
        scored.sort(key=lambda x: -x[1])

        selected: List[Tuple[int, str]] = []
        char_count = 0
        for idx, _score, para in scored:
            if char_count + len(para) > max_chars:
                break
            selected.append((idx, para))
            char_count += len(para)

        # Restore document order
        selected.sort(key=lambda x: x[0])

        return "\n\n".join(para for _, para in selected)

    @staticmethod
    def format_for_prompt(document_context: str) -> str:
        """
        Format document context for inclusion in system prompt.

        Uses a structured template with mandatory instructions so the LLM
        grounds its answers in the retrieved segments and avoids fabrication.

        Args:
            document_context: Raw document context string

        Returns:
            Formatted string with instructions and segments for LLM prompt
        """
        if not document_context:
            return ""
        return (
            "\n\n[CONTEXTO DOCUMENTAL — INSTRUCCIONES OBLIGATORIAS]\n"
            "El usuario tiene documentos adjuntos. Los siguientes segmentos "
            "fueron recuperados por relevancia semántica.\n"
            "- Responde la pregunta del usuario basándote EXCLUSIVAMENTE en estos segmentos.\n"
            "- Si la respuesta no está en los segmentos, dilo: "
            '"No encontré esa información en el documento."\n'
            '- Cita el documento y página cuando sea posible: "Según [nombre], página X..."\n'
            "- NO inventes información que no esté en los segmentos.\n\n"
            f"{document_context}\n\n"
            "[FIN CONTEXTO DOCUMENTAL]"
        )
