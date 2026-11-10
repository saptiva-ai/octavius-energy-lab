"""
Complexity Analyzer - Determines query specificity and complexity.

Analyzes multiple factors to classify query complexity:
1. Query length (short queries tend to be vaguer)
2. Presence of vague words (esto, eso, cosa, etc.)
3. Pronoun usage without clear antecedents
4. Lexical specificity (how specific are the words used)
5. Entity density (how many specific entities mentioned)

Design Principles:
- Multi-factor scoring: Combines multiple signals
- Threshold-based classification: Clear boundaries between levels
- Observable: Logs reasoning for each classification
"""

import re
from typing import Set, Tuple

import structlog

from .types import QueryComplexity, QueryContext

logger = structlog.get_logger(__name__)


class ComplexityAnalyzer:
    """
    Analyze query complexity to determine how specific/vague it is.

    Complexity levels:
    - VAGUE: Generic question with little context ("¿Qué es esto?")
    - SIMPLE: Clear single-entity question ("¿Cuál es el precio?")
    - COMPLEX: Multi-entity or multi-part question
    """

    def __init__(self):
        """Initialize analyzer with word lists."""

        # Vague words that indicate lack of specificity
        self.vague_words: Set[str] = {
            "esto",
            "eso",
            "aquello",
            "aquí",
            "ahí",
            "allí",
            "cosa",
            "cosas",
            "documento",
            "archivo",
            "texto",
            "información",
            "datos",
            "algo",
            "nada",
        }

        # Deictic pronouns (pointing words without clear reference)
        self.deictic_pronouns: Set[str] = {
            "este",
            "ese",
            "aquel",
            "esta",
            "esa",
            "aquella",
            "estos",
            "esos",
            "aquellos",
            "estas",
            "esas",
            "aquellas",
        }

        # Common stopwords that don't add specificity
        self.stopwords: Set[str] = {
            "el",
            "la",
            "los",
            "las",
            "un",
            "una",
            "unos",
            "unas",
            "de",
            "del",
            "a",
            "al",
            "en",
            "con",
            "por",
            "para",
            "que",
            "qué",
            "cual",
            "cuál",
            "es",
            "son",
            "está",
            "están",
            "hay",
            "tiene",
            "tienen",
        }

    def analyze(
        self, query: str, context: QueryContext
    ) -> Tuple[QueryComplexity, float, str]:
        """
        Analyze query complexity.

        Args:
            query: User query string
            context: Conversation context

        Returns:
            (complexity, confidence, reasoning)
        """
        query_lower = query.lower().strip()
        # Remove punctuation from query for tokenization
        query_clean = re.sub(r"[¿?¡!.,;:]", "", query_lower)
        tokens = query_clean.split()

        # Calculate complexity score (higher = more complex/specific)
        score = 0
        factors = []

        # Factor 1: Query length
        # Very short queries (< 4 tokens) tend to be vague
        if len(tokens) < 4:
            score -= 2
            factors.append(f"short query ({len(tokens)} tokens)")
        elif len(tokens) > 10:
            score += 1
            factors.append(f"long query ({len(tokens)} tokens)")

        # Factor 2: Vague words
        # "esto" and similar deictic words get extra weight (3 instead of 2)
        critical_vague_words = {"esto", "eso", "aquello", "cosa", "cosas"}
        vague_count = sum(1 for token in tokens if token in self.vague_words)
        critical_vague_count = sum(
            1 for token in tokens if token in critical_vague_words
        )

        if vague_count > 0:
            # Critical vague words (esto, eso) get -3 penalty, others get -2
            penalty = (critical_vague_count * 3) + (
                (vague_count - critical_vague_count) * 2
            )
            score -= penalty
            factors.append(
                f"{vague_count} vague word(s), {critical_vague_count} critical"
            )

        # Factor 3: Deictic pronouns without clear antecedent
        deictic_count = sum(1 for token in tokens if token in self.deictic_pronouns)
        if deictic_count > 0 and not context.has_recent_entities:
            score -= deictic_count
            factors.append(f"{deictic_count} deictic pronoun(s) without context")

        # Factor 4: Lexical specificity (ratio of content words to stopwords)
        # BUT: Don't count vague words as "content" for specificity calculation
        content_words = [
            t for t in tokens if t not in self.stopwords and t not in self.vague_words
        ]
        if len(tokens) > 0:
            specificity_ratio = len(content_words) / len(tokens)
            if specificity_ratio < 0.3:
                score -= 1
                factors.append(f"low specificity ratio ({specificity_ratio:.2f})")
            elif specificity_ratio > 0.6:
                score += 1
                factors.append(f"high specificity ratio ({specificity_ratio:.2f})")

        # Factor 5: Multiple entities (indicates complex question)
        # Simple heuristic: look for named entities (capitalized words)
        capitalized_count = sum(
            1 for token in query.split() if token and token[0].isupper()
        )
        if capitalized_count > 2:
            score += 1
            factors.append(f"{capitalized_count} potential entities")

        # Factor 6: Conjunctions (indicate multi-part questions)
        conjunctions = {"y", "o", "pero", "además", "también"}
        conjunction_count = sum(1 for token in tokens if token in conjunctions)
        if conjunction_count > 0:
            score += conjunction_count
            factors.append(f"{conjunction_count} conjunction(s)")

        # Classify based on final score
        if score <= -3:
            complexity = QueryComplexity.VAGUE
            confidence = 0.90
            reasoning = f"Vague query (score={score}): {', '.join(factors)}"
        elif score <= 1:
            complexity = QueryComplexity.SIMPLE
            confidence = 0.80
            reasoning = f"Simple query (score={score}): {', '.join(factors)}"
        else:
            complexity = QueryComplexity.COMPLEX
            confidence = 0.80
            reasoning = f"Complex query (score={score}): {', '.join(factors)}"

        logger.info(
            "Complexity analyzed",
            complexity=complexity.value,
            score=score,
            confidence=confidence,
            factors=factors,
            query_preview=query[:50],
        )

        return complexity, confidence, reasoning
