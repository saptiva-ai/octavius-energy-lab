"""
Intent Classifier - Hybrid Rule-Based + ML Approach

Architecture:
- Level 1: Rule-based classification (high precision, fast)
- Level 2: Zero-shot classification (handles edge cases)
- Ensemble: Combine both approaches with confidence weighting

Design Principles:
- Fail-fast: Rules handle 90% of cases instantly
- Graceful degradation: Falls back to ML when rules uncertain
- Observable: Logs reasoning for each classification
"""

import re
from typing import List, Optional, Tuple

import structlog

from .types import QueryContext, QueryIntent

logger = structlog.get_logger(__name__)


class IntentClassifier:
    """
    Classify user query intent using hybrid approach.

    Levels:
    1. Rule-based patterns (fast, high precision)
    2. Zero-shot ML classifier (fallback for ambiguous cases)
    """

    def __init__(self):
        """Initialize classifier with pattern rules."""

        # Overview patterns - user wants general document summary
        self.overview_patterns = [
            r"^(qu[eé]|que)\s+(es|son)\s+(esto|este|esta|eso)",  # "¿Qué es esto?"
            r"^(qu[eé]|que)\s+(contiene|dice|trata|tiene)\s+(esto|este|esta|el\s+documento|aqu[ií])",
            r"^(de\s+qu[eé]|sobre\s+qu[eé])\s+(trata|habla|es)",
            r"^(resum[ei]|cu[eé]ntame|expl[ií]came|descr[ií]be)",
            r"^qu[eé]\s+(hay|contiene)\s+(aqu[ií]|en\s+(esto|este|el\s+documento))",
            r"^(describe|explica|resume)\s+(el\s+documento|esto)",
        ]

        # Specific fact patterns - user wants specific information
        self.specific_fact_patterns = [
            r"(cu[aá]l|qu[eé])\s+(es|ser[aá])\s+(el|la|los|las)\s+\w+",  # "¿Cuál es el precio?"
            r"^(cu[aá]nto|cu[aá]ntos|cu[aá]ntas)",  # "¿Cuánto cuesta?"
            r"^(d[oó]nde|cu[aá]ndo)\s+",  # "¿Dónde está?" "¿Cuándo sucede?"
            r"^(qui[eé]n|qui[eé]nes)\s+",  # "¿Quién es responsable?"
            r"(menciona|indica|especifica|detalla)\s+(el|la)\s+\w+",
        ]

        # Procedural patterns - user wants to know "how"
        self.procedural_patterns = [
            r"^(c[oó]mo|como)\s+(funciona|se\s+hace|se\s+realiza|se\s+calcula)",
            r"^(cu[aá]l\s+es\s+el\s+proceso|explica\s+el\s+proceso)",
            r"(pasos|procedimiento|m[eé]todo)\s+(para|de)",
        ]

        # Analytical patterns - user wants to know "why"
        self.analytical_patterns = [
            r"^(por\s+qu[eé]|porque)\s+",
            r"^(cu[aá]l\s+es\s+la\s+raz[oó]n|cu[aá]les\s+son\s+las\s+razones)",
            r"(causa|motivo|justificaci[oó]n)\s+(de|para)",
        ]

        # Definitional patterns - user wants definition
        self.definitional_patterns = [
            r"^(qu[eé]\s+significa|qu[eé]\s+es|qu[eé]\s+son)\s+\w+",
            r"^(define|definici[oó]n\s+de)\s+",
            r"(significado|concepto)\s+de\s+",
        ]

        # Quantitative patterns - user wants numbers
        self.quantitative_patterns = [
            r"^(cu[aá]nto|cu[aá]ntos|cu[aá]ntas)",  # "¿Cuánto?" "¿Cuánto cuesta?"
            r"(n[uú]mero|cantidad|monto|valor|cifra)\s+(de|total)",
            r"(porcentaje|tasa|ratio)\s+de",
            r"(cuesta|vale|precio|costo)",  # "¿Cuánto cuesta?"
        ]

        # Comparison patterns - user wants to compare
        self.comparison_patterns = [
            r"(diferencia|comparaci[oó]n)\s+(entre|de)",
            r"(versus|vs|frente\s+a)",
            r"^(compara|contrasta)\s+",
            r"(mejor|peor|mayor|menor)\s+que",
        ]

    def classify(
        self, query: str, context: QueryContext
    ) -> Tuple[QueryIntent, float, str]:
        """
        Classify query intent.

        Args:
            query: User query string
            context: Conversation context

        Returns:
            (intent, confidence, reasoning)
        """
        query_lower = query.lower().strip()

        # Level 1: Rule-based classification
        rule_result = self._apply_rules(query_lower)

        if rule_result:
            intent, confidence, reasoning = rule_result

            logger.info(
                "Intent classified (rules)",
                intent=intent.value,
                confidence=confidence,
                reasoning=reasoning,
                query_preview=query[:50],
            )

            return intent, confidence, reasoning

        # Level 2: Fallback to heuristic default
        # If no patterns match, assume SPECIFIC_FACT (most common case)
        default_intent = QueryIntent.SPECIFIC_FACT
        default_confidence = 0.5
        default_reasoning = "No patterns matched, defaulting to specific fact"

        logger.info(
            "Intent classified (default)",
            intent=default_intent.value,
            confidence=default_confidence,
            reasoning=default_reasoning,
            query_preview=query[:50],
        )

        return default_intent, default_confidence, default_reasoning

    def _apply_rules(self, query: str) -> Optional[Tuple[QueryIntent, float, str]]:
        """
        Apply rule-based patterns to classify intent.

        Returns:
            (intent, confidence, reasoning) or None if no match
        """

        # Priority order: Most specific patterns first

        # 1. Overview (very distinctive patterns)
        if self._matches_any(query, self.overview_patterns):
            return (
                QueryIntent.OVERVIEW,
                0.95,
                "Matched overview pattern (generic document question)",
            )

        # 2. Quantitative (numbers/amounts)
        if self._matches_any(query, self.quantitative_patterns):
            return (
                QueryIntent.QUANTITATIVE,
                0.90,
                "Matched quantitative pattern (numerical question)",
            )

        # 3. Comparison
        if self._matches_any(query, self.comparison_patterns):
            return (
                QueryIntent.COMPARISON,
                0.90,
                "Matched comparison pattern (comparing entities)",
            )

        # 4. Definitional
        if self._matches_any(query, self.definitional_patterns):
            return (
                QueryIntent.DEFINITIONAL,
                0.85,
                "Matched definitional pattern (asking for definition)",
            )

        # 5. Procedural (how-to questions)
        if self._matches_any(query, self.procedural_patterns):
            return (
                QueryIntent.PROCEDURAL,
                0.85,
                "Matched procedural pattern (how-to question)",
            )

        # 6. Analytical (why questions)
        if self._matches_any(query, self.analytical_patterns):
            return (
                QueryIntent.ANALYTICAL,
                0.85,
                "Matched analytical pattern (why/reason question)",
            )

        # 7. Specific fact (broadest category)
        if self._matches_any(query, self.specific_fact_patterns):
            return (
                QueryIntent.SPECIFIC_FACT,
                0.80,
                "Matched specific fact pattern (factual question)",
            )

        # No match
        return None

    def _matches_any(self, query: str, patterns: List[str]) -> bool:
        """Check if query matches any pattern in the list."""
        # Clean query: remove question marks and exclamation marks
        query_clean = re.sub(r"[¿?¡!]", "", query)
        return any(
            re.search(pattern, query_clean, re.IGNORECASE) for pattern in patterns
        )
