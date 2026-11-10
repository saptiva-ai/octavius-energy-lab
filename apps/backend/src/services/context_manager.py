"""
Unified Context Manager for MCP tool results and document context.

This service aggregates all context sources (documents, tool results, metadata)
and formats them for LLM injection with consistent size limits.
"""

from datetime import datetime
from typing import Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger(__name__)

# Context size limits (configurable via env)
MAX_DOCUMENT_CONTEXT_CHARS = 16000
MAX_TOOL_CONTEXT_CHARS = 8000
MAX_TOTAL_CONTEXT_CHARS = 24000


class ContextSource:
    """Represents a single source of context."""

    def __init__(
        self,
        source_type: str,  # "document", "tool_result", "metadata"
        source_id: str,
        content: str,
        metadata: Optional[Dict] = None,
    ):
        self.source_type = source_type
        self.source_id = source_id
        self.content = content
        self.metadata = metadata or {}
        self.timestamp = datetime.utcnow()
        self.char_count = len(content)


class ContextManager:
    """
    Unified manager for all context sources that get injected into LLM prompts.

    Responsibilities:
    1. Aggregate context from documents, tool results, and metadata
    2. Apply size limits consistently across all sources
    3. Format context for LLM injection
    4. Track context sources for debugging
    """

    def __init__(
        self,
        max_document_chars: int = MAX_DOCUMENT_CONTEXT_CHARS,
        max_tool_chars: int = MAX_TOOL_CONTEXT_CHARS,
        max_total_chars: int = MAX_TOTAL_CONTEXT_CHARS,
    ):
        self.max_document_chars = max_document_chars
        self.max_tool_chars = max_tool_chars
        self.max_total_chars = max_total_chars

        self.sources: List[ContextSource] = []
        self._document_context = ""
        self._tool_context = ""
        self._metadata_context = ""

    def add_document_context(
        self, doc_id: str, text: str, filename: Optional[str] = None
    ) -> None:
        """Add document text to context pool."""
        content = text
        if filename:
            content = f"{filename}\n{text}"

        source = ContextSource(
            source_type="document",
            source_id=doc_id,
            content=content,
            metadata={"filename": filename},
        )
        self.sources.append(source)
        logger.debug(
            "Added document context",
            doc_id=doc_id,
            char_count=len(text),
            filename=filename,
        )

    def add_tool_result(
        self, tool_name: str, result: Dict, summary: Optional[str] = None
    ) -> None:
        """
        Add MCP tool result to context pool.

        Args:
            tool_name: Name of the MCP tool
            result: Full tool result (will be summarized if needed)
            summary: Optional pre-computed summary
        """
        # Generate summary from result if not provided
        if summary is None:
            summary = self._summarize_tool_result(tool_name, result)

        source = ContextSource(
            source_type="tool_result",
            source_id=tool_name,
            content=summary,
            metadata={"full_result": result},
        )
        self.sources.append(source)
        logger.debug(
            "Added tool result context", tool_name=tool_name, summary_chars=len(summary)
        )

    def _summarize_tool_result(self, tool_name: str, result: Dict) -> str:
        """Generate LLM-friendly summary of tool result."""
        summaries = {
            "audit_file": self._summarize_audit_result,
            "excel_analyzer": self._summarize_excel_result,
            "deep_research": self._summarize_research_result,
        }

        summarizer = summaries.get(tool_name, self._default_summary)
        return summarizer(result)

    def _summarize_audit_result(self, result: Dict) -> str:
        """Format audit findings for LLM."""
        findings = result.get("findings", [])
        if not findings:
            return "✅ Document audit passed with no issues."

        summary_parts = ["📋 Document Audit Findings:\n"]

        for finding in findings[:5]:  # Limit to top 5 findings
            severity = finding.get("severity", "info")
            message = finding.get("message", "")
            emoji = (
                "🔴" if severity == "error" else "🟡" if severity == "warning" else "ℹ️"
            )
            summary_parts.append(f"{emoji} {message}")

        if len(findings) > 5:
            summary_parts.append(f"... and {len(findings) - 5} more findings")

        return "\n".join(summary_parts)

    def _summarize_excel_result(self, result: Dict) -> str:
        """Format Excel analysis for LLM."""
        operations = result.get("operations", {})

        summary_parts = ["📊 Excel Analysis:\n"]

        if "stats" in operations:
            stats = operations["stats"]
            summary_parts.append(
                f"- Rows: {stats.get('row_count', 0)}, "
                f"Columns: {stats.get('column_count', 0)}"
            )

        if "aggregate" in operations:
            agg = operations["aggregate"]
            for col, values in agg.items():
                mean_val = values.get("mean")
                sum_val = values.get("sum")

                mean_str = (
                    f"{mean_val:.2f}" if isinstance(mean_val, (int, float)) else "N/A"
                )
                sum_str = (
                    f"{sum_val:.2f}" if isinstance(sum_val, (int, float)) else "N/A"
                )

                summary_parts.append(f"- {col}: mean={mean_str}, sum={sum_str}")

        return "\n".join(summary_parts)

    def _summarize_research_result(self, result: Dict) -> str:
        """Format research findings for LLM."""
        summary = result.get("summary", "")
        sources_count = len(result.get("sources", []))

        return (
            f"🔍 Research Findings:\n"
            f"{summary}\n\n"
            f"Based on {sources_count} verified sources."
        )

    def _default_summary(self, result: Dict) -> str:
        """Default summarizer for unknown tool types."""
        return f"Tool result: {str(result)[:500]}..."

    def build_context_string(self) -> Tuple[str, Dict]:
        """
        Build final context string for LLM with size limits applied.

        Returns:
            Tuple of (context_string, metadata)
        """
        # Separate sources by type
        doc_sources = [s for s in self.sources if s.source_type == "document"]
        tool_sources = [s for s in self.sources if s.source_type == "tool_result"]

        # Build document context (with size limit)
        doc_parts = []
        doc_chars = 0
        for source in doc_sources:
            if doc_chars + source.char_count <= self.max_document_chars:
                doc_parts.append(source.content)
                doc_chars += source.char_count
            else:
                remaining = self.max_document_chars - doc_chars
                if (
                    remaining >= 50
                ):  # Only add if meaningful space left (at least 50 chars)
                    doc_parts.append(source.content[:remaining] + "...")
                    doc_chars += remaining
                break

        # Build tool context (with size limit)
        tool_parts = []
        tool_chars = 0
        for source in tool_sources:
            if tool_chars + source.char_count <= self.max_tool_chars:
                tool_parts.append(source.content)
                tool_chars += source.char_count
            else:
                remaining = self.max_tool_chars - tool_chars
                if (
                    remaining >= 50
                ):  # Only add if meaningful space left (at least 50 chars)
                    tool_parts.append(source.content[:remaining] + "...")
                    tool_chars += remaining
                break

        # Combine contexts with clear separators
        context_parts = []

        if doc_parts:
            context_parts.append("📄 Document Content:\n" + "\n\n".join(doc_parts))

        if tool_parts:
            context_parts.append("🔧 Analysis Results:\n" + "\n\n".join(tool_parts))

        full_context = "\n\n---\n\n".join(context_parts)

        # Track original size before truncation
        original_size = len(full_context)
        was_truncated = original_size > self.max_total_chars

        # Apply total size limit
        if was_truncated:
            truncation_msg = "\n\n[Context truncated]"
            max_content = self.max_total_chars - len(truncation_msg)
            full_context = full_context[:max_content] + truncation_msg

        # Build metadata
        metadata = {
            "total_sources": len(self.sources),
            "document_sources": len(doc_sources),
            "tool_sources": len(tool_sources),
            "document_chars": doc_chars,
            "tool_chars": tool_chars,
            "total_chars": len(full_context),
            "truncated": was_truncated,
        }

        logger.info("Built unified context for LLM", **metadata)

        return full_context, metadata

    def clear(self) -> None:
        """Clear all context sources."""
        self.sources = []
        logger.debug("Cleared all context sources")
