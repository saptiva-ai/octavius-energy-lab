"""
Simple Memory Service - JSON-based fact recall.

Extracts domain metrics (metric, period, entity) from conversation via regex
and stores them as JSON for context injection into LLM prompts.
"""

from .fact_extractor import extract_all, extract_bank, extract_metrics, extract_period
from .memory_service import MemoryService, get_memory_service

__all__ = [
    "MemoryService",
    "get_memory_service",
    "extract_all",
    "extract_bank",
    "extract_period",
    "extract_metrics",
]
