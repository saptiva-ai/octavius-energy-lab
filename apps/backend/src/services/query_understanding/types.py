"""
Type definitions for Query Understanding module.

Defines enums, dataclasses, and types used across the module.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class QueryIntent(Enum):
    """
    Intent classification for user queries.

    Determines what the user wants to achieve with their query.
    """

    OVERVIEW = "overview"  # "¿Qué es esto?" - General document overview
    SPECIFIC_FACT = "specific_fact"  # "¿Cuál es el precio?" - Specific factual question
    COMPARISON = "comparison"  # "¿Diferencia entre X y Y?" - Compare entities
    PROCEDURAL = "procedural"  # "¿Cómo funciona X?" - Process/procedure questions
    ANALYTICAL = "analytical"  # "¿Por qué X?" - Causal/analytical questions
    DEFINITIONAL = "definitional"  # "¿Qué significa X?" - Definition requests
    QUANTITATIVE = "quantitative"  # "¿Cuánto/Cuántos?" - Numerical questions


class QueryComplexity(Enum):
    """
    Complexity level of a query.

    Determines how specific and well-formed the query is.
    """

    VAGUE = "vague"  # Very generic, lacks context ("¿Qué es esto?")
    SIMPLE = "simple"  # Simple, single-entity question ("¿Cuál es el precio?")
    COMPLEX = "complex"  # Multi-entity or multi-part question


@dataclass
class QueryContext:
    """
    Contextual information about the current conversation state.

    Used to inform query understanding decisions.
    """

    conversation_id: str
    has_recent_entities: bool = False
    recent_entities: List[str] = field(default_factory=list)
    documents_count: int = 0
    previous_query: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class QueryAnalysis:
    """
    Result of query understanding analysis.

    Contains all information needed to select retrieval strategy.
    """

    original_query: str
    intent: QueryIntent
    complexity: QueryComplexity
    expanded_query: str
    entities: List[str] = field(default_factory=list)
    confidence: float = 0.0
    reasoning: str = ""  # Explanation of why this classification was chosen
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        return (
            f"QueryAnalysis("
            f"intent={self.intent.value}, "
            f"complexity={self.complexity.value}, "
            f"confidence={self.confidence:.2f}, "
            f"entities={self.entities})"
        )
