"""
Simple fact extractor using regex.

Domain-agnostic. Extracts generic temporal references (quarters/years) from
conversation text so the memory layer can scope context over time. Domain
entity/metric extraction is intentionally NOT performed here — that lives in
the domain plugin, which can enrich memory with its own catalogs.
"""

import re
from typing import Dict, Optional, Tuple

# Domain entity catalogs (banks, tickers, etc.) live in domain plugins.
# The agnostic host keeps these empty by design.
BANKS: set[str] = set()
BANK_ALIASES: Dict[str, str] = {}

# Period patterns: (regex, formatter function)
PERIOD_PATTERNS = [
    # Q3 2025, Q3 de 2025, q3_2025
    (r"q([1-4])\s*(?:de\s*)?(\d{4})", lambda m: f"q{m.group(1)}_{m.group(2)}"),
    # 2025 Q3, 2025-Q3
    (r"(\d{4})\s*[-_]?\s*q([1-4])", lambda m: f"q{m.group(2)}_{m.group(1)}"),
    # T1 2025, 1T 2025 (Spanish trimestre)
    (r"([1-4])t\s*(?:de\s*)?(\d{4})", lambda m: f"q{m.group(1)}_{m.group(2)}"),
    (r"t([1-4])\s*(?:de\s*)?(\d{4})", lambda m: f"q{m.group(1)}_{m.group(2)}"),
    # Multi-year range: "2024 y 2025", "2024 a 2025", "2024-2025"
    (r"\b(\d{4})\s*(?:y|a|al|-)\s*(\d{4})\b", lambda m: f"{m.group(1)}-{m.group(2)}"),
    # Just year: 2024, 2025
    (r"\b(\d{4})\b", lambda m: m.group(1)),
]

# Metric patterns are domain-specific and provided by plugins, not the host.
METRIC_PATTERNS: Dict[str, str] = {}


def extract_topic_metric(text: str) -> Optional[str]:
    """
    Find the primary metric mentioned in text (without requiring a value).

    Agnostic host has no domain metric catalog, so this always returns None.
    Domain plugins override memory enrichment with their own detection.
    """
    return None


def extract_bank(text: str) -> Optional[str]:
    """
    Find an entity name in text.

    Agnostic host has no entity catalog, so this always returns None.
    """
    text_lower = text.lower()
    for bank in sorted(BANKS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(bank)}\b", text_lower):
            return BANK_ALIASES.get(bank, bank)
    return None


def extract_period(text: str) -> Optional[str]:
    """
    Find period (quarter/year) in text.

    Args:
        text: Input text to search

    Returns:
        Period string (e.g., "q3_2025" or "2024") if found, None otherwise
    """
    text_lower = text.lower()
    for pattern, formatter in PERIOD_PATTERNS:
        match = re.search(pattern, text_lower)
        if match:
            return formatter(match)
    return None


def extract_metrics(text: str) -> Dict[str, str]:
    """
    Extract metric name -> value pairs from text.

    Agnostic host has no domain metric catalog, so this returns an empty dict.
    """
    facts: Dict[str, str] = {}
    for metric, pattern in METRIC_PATTERNS.items():
        match = re.search(pattern, text.lower(), re.IGNORECASE)
        if match:
            facts[metric] = match.group(1)
    return facts


def extract_all(
    text: str, current_context: Optional[Dict[str, str]] = None
) -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    Extract facts and update context from message.

    This is the main entry point for fact extraction. On the agnostic host it
    tracks temporal context (period) only; entity/metric enrichment is left to
    domain plugins.

    Args:
        text: User message text
        current_context: Existing context (entity, period, metric) to inherit from

    Returns:
        Tuple of (facts_dict, updated_context)
    """
    current_context = current_context or {}

    # Extract components from text
    bank = extract_bank(text) or current_context.get("bank")
    period = extract_period(text) or current_context.get("period")
    metrics = extract_metrics(text)

    # Build scoped fact keys
    facts = {}
    for metric, value in metrics.items():
        if bank and period:
            key = f"{bank}.{period}.{metric}"
        elif bank:
            key = f"{bank}.{metric}"
        elif period:
            key = f"{period}.{metric}"
        else:
            key = metric
        facts[key] = value

    # Update context with newly detected values
    new_context = current_context.copy()
    if bank:
        new_context["bank"] = bank
    if period:
        new_context["period"] = period
    if metrics:
        new_context["metric"] = list(metrics.keys())[0]

    return facts, new_context
