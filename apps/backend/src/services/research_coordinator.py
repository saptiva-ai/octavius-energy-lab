"""
Research Coordinator Service - Bridge between SAPTIVA chat and Aletheia deep research.

This service provides intelligent routing between simple chat and deep research
based on query complexity and user preferences.
"""

import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

import structlog
from pydantic import BaseModel

from ..core.config import get_settings
from ..models.chat import ChatMessage, ChatSession
from ..models.task import Task as TaskModel
from ..models.task import TaskStatus
from ..schemas.research import DeepResearchParams, DeepResearchRequest, ResearchType
from ..services.aletheia_client import get_aletheia_client
from ..services.history_service import HistoryService
from ..services.saptiva_client import get_saptiva_client

logger = structlog.get_logger(__name__)


class QueryComplexity(BaseModel):
    """Analysis of query complexity for routing decisions."""

    score: float  # 0.0 to 1.0
    reasoning: str
    requires_research: bool
    estimated_sources: int
    estimated_time_minutes: int
    complexity_factors: List[str]


class ResearchDecision(BaseModel):
    """Decision on whether to use chat or deep research."""

    use_deep_research: bool
    reasoning: str
    complexity: QueryComplexity
    recommended_params: Optional[DeepResearchParams] = None
    fallback_to_chat: bool = True


class ResearchCoordinator:
    """
    Coordinates between SAPTIVA chat and Aletheia deep research.

    Provides intelligent routing based on query complexity and automatic
    escalation from chat to research when needed.
    """

    def __init__(self):
        self.settings = get_settings()

        # Complexity analysis patterns
        self.research_indicators = [
            # Explicit academic/research queries
            r"\b(research findings|research shows|studies indicate|academic research|investigate.*research)\b",
            r"\b(literature review|systematic review|meta-analysis)\b",
            r"\b(what does research show|what do studies say)\b",
            # Complex comparative queries (require specific research context)
            r"\b(detailed comparison|comprehensive analysis|compare.*research|compare.*studies)\b",
            r"\b(pros and cons.*research|advantages and disadvantages.*analysis)\b",
            # Multi-faceted research questions
            r"\b(comprehensive research|detailed analysis|thorough investigation)\b",
            r"\b(complete research guide|everything.*research|research overview)\b",
            # Explicit factual verification requests
            r"\b(fact check.*sources|verify.*research|need evidence|show citations)\b",
            r"\b(according to research|based on studies|research consensus)\b",
            # Current research information requests
            r"\b(latest research|recent studies|current literature|up-to-date research)\b",
            r"\b(research news|research developments|research trends|research updates)\b",
            # Academic/technical domains with research context
            r"\b(academic research|scientific study|technical analysis|peer-reviewed research)\b",
            r"\b(research methodology|study framework|research algorithm|research protocol)\b",
        ]

        self.chat_indicators = [
            # Simple definitions
            r"^\s*what is\s+\w+\s*\??\s*$",
            r"^\s*define\s+\w+\s*\??\s*$",
            # Simple how-to and questions
            r"^\s*how to\s+\w+.*\??\s*$",
            r"^\s*how do I\s+\w+.*\??\s*$",
            r"^\s*can you\s+\w+.*\??\s*$",
            # Personal/conversational questions
            r"\b(what do you think|your opinion|do you believe)\b",
            r"\b(I think|I believe|in my opinion)\b",
            r"\b(tell me about|explain|help me understand)\b",
            # Simple calculations and tasks
            r"\b(calculate|math|arithmetic|\+|\-|\*|\/|\=)\b",
            r"\b(write|create|make|generate|show me)\b.*\b(code|script|example)\b",
            # Common conversational patterns
            r"\b(what|why|when|where|which|who)\s+(?!.*research)(?!.*study)(?!.*analysis)",
            r"\b(simple|basic|quick|short)\b.*\b(question|answer|explanation)\b",
            # Short questions (less than 10 words often simple)
            r"^\s*\S+(\s+\S+){0,8}\s*\??\s*$",
        ]

    async def analyze_query_complexity(
        self, query: str, context: Optional[Dict[str, Any]] = None
    ) -> QueryComplexity:
        """
        Analyze query complexity to determine if deep research is needed.

        Args:
            query: User query to analyze
            context: Additional context (chat history, user preferences, etc.)

        Returns:
            QueryComplexity analysis
        """

        factors = []
        score = 0.0

        # Immediate bypass for simple greetings, short queries and basic questions
        simple_greetings = [
            r"^\s*(hola|hello|hi|hey|good morning|good afternoon|good evening|buenas)\s*(como estas|how are you|como estas|como andas)?\s*[?!.]*\s*$",
            r"^\s*(que tal|how\'s it going|what\'s up|sup)\s*[?!.]*\s*$",
            r"^\s*(gracias|thank you|thanks|merci)\s*[?!.]*\s*$",
            r"^\s*(bye|goodbye|adios|hasta luego|see you|chau)\s*[?!.]*\s*$",
            r"^\s*(si|yes|no|ok|okay)\s*[?!.]*\s*$",
            # Simple questions about the system/AI
            r"^\s*(eres|are you|you are)\s*(un\s*)?(mock|fake|real|bot|ai|artificial|robot)\s*[?!.]*\s*$",
            r"^\s*(que\s+eres|what\s+are\s+you|who\s+are\s+you)\s*[?!.]*\s*$",
            r"^\s*(como\s+te\s+llamas|what\s+is\s+your\s+name|whats\s+your\s+name)\s*[?!.]*\s*$",
            r"^\s*(puedes|can\s+you|are\s+you\s+able\s+to)\s+.*[?!.]*\s*$",
            # Short direct questions (less than 20 chars typically)
            r"^.{1,20}[?!.]*\s*$",
        ]

        # Check for simple greetings first
        query_lower = query.lower().strip()
        for pattern in simple_greetings:
            if re.match(pattern, query_lower, re.IGNORECASE):
                return QueryComplexity(
                    score=0.0,
                    reasoning="Simple greeting or short response - direct chat appropriate",
                    requires_research=False,
                    estimated_sources=0,
                    estimated_time_minutes=0,
                    complexity_factors=["Simple greeting/response"],
                )

        # Length factor (longer queries often more complex)
        word_count = len(query.split())
        if word_count > 20:
            score += 0.3
            factors.append(f"Long query ({word_count} words)")
        elif word_count > 10:
            score += 0.1
            factors.append(f"Medium query ({word_count} words)")

        # Research indicator patterns
        research_matches = 0
        for pattern in self.research_indicators:
            if re.search(pattern, query, re.IGNORECASE):
                research_matches += 1
                score += 0.2
                factors.append(f"Research indicator: {pattern}")

        # Chat indicator patterns (reduce score)
        chat_matches = 0
        for pattern in self.chat_indicators:
            if re.search(pattern, query, re.IGNORECASE):
                chat_matches += 1
                score -= 0.3
                factors.append(f"Simple query indicator: {pattern}")

        # Question complexity
        question_marks = query.count("?")
        if question_marks > 1:
            score += 0.2
            factors.append(f"Multiple questions ({question_marks})")

        # AND/OR logic
        if re.search(r"\b(and|or|but|however|although)\b", query, re.IGNORECASE):
            score += 0.1
            factors.append("Complex logical structure")

        # Context factors
        if context:
            # Previous research in conversation
            if context.get("has_previous_research"):
                score += 0.2
                factors.append("Previous research in conversation")

            # User explicitly requests research
            if context.get("user_prefers_research"):
                score += 0.5
                factors.append("User preference for research")

        # Normalize score to 0-1 range
        score = max(0.0, min(1.0, score))

        # Determine if research is needed (more conservative thresholds)
        requires_research = score > 0.7 or research_matches >= 3

        # Estimate complexity
        if score > 0.7:
            estimated_sources = 15 + research_matches * 5
            estimated_time = 4 + research_matches * 2
        elif score > 0.4:
            estimated_sources = 8 + research_matches * 3
            estimated_time = 2 + research_matches
        else:
            estimated_sources = 3
            estimated_time = 1

        reasoning = f"Complexity score: {score:.2f}. "
        if requires_research:
            reasoning += f"Detected {research_matches} research indicators. "
        if chat_matches > 0:
            reasoning += f"Detected {chat_matches} simple query indicators. "

        return QueryComplexity(
            score=score,
            reasoning=reasoning,
            requires_research=requires_research,
            estimated_sources=estimated_sources,
            estimated_time_minutes=estimated_time,
            complexity_factors=factors,
        )

    async def make_research_decision(
        self,
        query: str,
        chat_id: Optional[str] = None,
        user_preferences: Optional[Dict[str, Any]] = None,
        force_research: bool = False,
    ) -> ResearchDecision:
        """
        Make an intelligent decision about whether to use chat or deep research.

        Args:
            query: User query
            chat_id: Chat session ID for context
            user_preferences: User preferences
            force_research: Force deep research regardless of complexity

        Returns:
            ResearchDecision with routing recommendation
        """

        try:
            # Gather context
            context = {}

            if chat_id:
                # Check if there's previous research in this conversation
                session = await ChatSession.get(chat_id)
                if session:
                    messages = (
                        await ChatMessage.find(ChatMessage.chat_id == chat_id)
                        .sort(-ChatMessage.created_at)
                        .limit(10)
                        .to_list()
                    )

                    # Look for research tasks in recent messages
                    for message in messages:
                        if message.metadata and message.metadata.get("task_id"):
                            context["has_previous_research"] = True
                            break

            # User preferences
            if user_preferences:
                context.update(user_preferences)

            # Analyze complexity
            complexity = await self.analyze_query_complexity(query, context)

            # Force research if requested
            if force_research:
                complexity.requires_research = True
                complexity.score = max(complexity.score, 0.8)
                complexity.reasoning += " (Forced by user request)"

            # P0-DR-001 & P0-DR-002: Check feature flags before making decision
            deep_research_enabled = self.settings.deep_research_enabled
            deep_research_auto = self.settings.deep_research_auto

            # Make decision based on feature flags and user intent
            # Deep Research is ONLY triggered when:
            # 1. Deep Research is enabled globally (deep_research_enabled=True)
            # 2. Either auto-trigger is enabled OR user explicitly requested it
            use_research = deep_research_enabled and (
                force_research or (deep_research_auto and complexity.requires_research)
            )

            # Generate reasoning
            if not deep_research_enabled:
                reasoning = "Deep research is disabled (DEEP_RESEARCH_ENABLED=false)"
                use_research = False
            elif force_research:
                reasoning = "Deep research explicitly requested by user"
            elif not deep_research_auto:
                reasoning = "Deep research auto-trigger disabled (DEEP_RESEARCH_AUTO=false) - chat fallback"
                use_research = False
            elif complexity.score > 0.7:
                reasoning = f"High complexity query (score: {complexity.score:.2f}) - deep research auto-triggered"
            elif complexity.score > 0.4:
                reasoning = f"Medium complexity query (score: {complexity.score:.2f}) - deep research beneficial but not triggered"
            else:
                reasoning = (
                    f"Simple query (score: {complexity.score:.2f}) - chat sufficient"
                )

            # Recommended research parameters
            recommended_params = None
            if use_research:
                recommended_params = DeepResearchParams(
                    max_iterations=3 if complexity.score > 0.7 else 2,
                    sources_limit=complexity.estimated_sources,
                    include_citations=True,
                    focus_areas=self._extract_focus_areas(query),
                    depth_level="deep" if complexity.score > 0.7 else "medium",
                )

            logger.info(
                "Research decision made",
                query_length=len(query),
                complexity_score=complexity.score,
                use_research=use_research,
                estimated_time=complexity.estimated_time_minutes,
            )

            return ResearchDecision(
                use_deep_research=use_research,
                reasoning=reasoning,
                complexity=complexity,
                recommended_params=recommended_params,
                fallback_to_chat=True,
            )

        except Exception as e:
            logger.error("Error making research decision", error=str(e))
            # Safe fallback to chat
            return ResearchDecision(
                use_deep_research=False,
                reasoning=f"Error in decision making: {str(e)}",
                complexity=QueryComplexity(
                    score=0.0,
                    reasoning="Error occurred",
                    requires_research=False,
                    estimated_sources=0,
                    estimated_time_minutes=0,
                    complexity_factors=[],
                ),
                fallback_to_chat=True,
            )

    def _extract_focus_areas(self, query: str) -> List[str]:
        """Extract focus areas from the query for targeted research."""

        focus_areas = []

        # Domain-specific patterns
        domain_patterns = {
            "technology": r"\b(AI|artificial intelligence|machine learning|blockchain|cloud|software|programming)\b",
            "healthcare": r"\b(health|medical|medicine|treatment|diagnosis|patient|clinical)\b",
            "business": r"\b(business|marketing|finance|strategy|management|economy|market)\b",
            "science": r"\b(research|study|scientific|biology|chemistry|physics|environmental)\b",
            "education": r"\b(education|learning|teaching|university|academic|school)\b",
            "legal": r"\b(law|legal|regulation|compliance|policy|court|legislation)\b",
        }

        for domain, pattern in domain_patterns.items():
            if re.search(pattern, query, re.IGNORECASE):
                focus_areas.append(domain)

        # If no specific domain, add general focus
        if not focus_areas:
            focus_areas = ["general"]

        return focus_areas

    async def execute_coordinated_research(
        self,
        query: str,
        user_id: str,
        chat_id: Optional[str] = None,
        force_research: bool = False,
        stream: bool = True,
        allow_deep_research: bool = True,
    ) -> Dict[str, Any]:
        """
        Execute coordinated research - either chat or deep research based on complexity.

        Args:
            query: User query
            user_id: User ID
            chat_id: Chat session ID
            force_research: Force deep research
            stream: Enable streaming

        Returns:
            Coordinated response with routing information
        """

        start_time = time.time()

        try:
            # Make routing decision
            decision = await self.make_research_decision(
                query=query, chat_id=chat_id, force_research=force_research
            )

            if not allow_deep_research and decision.use_deep_research:
                decision.use_deep_research = False
                decision.reasoning = "Deep research disabled by user selection"

            if decision.use_deep_research:
                # Execute deep research
                task_id = str(uuid4())

                # Create research request
                research_request = DeepResearchRequest(
                    query=query,
                    research_type=ResearchType.DEEP_RESEARCH,
                    params=decision.recommended_params,
                    stream=stream,
                    chat_id=chat_id,
                    context={
                        "routing_decision": decision.dict(),
                        "coordinated_research": True,
                    },
                )

                # Start deep research task
                task = TaskModel(
                    id=task_id,
                    user_id=user_id,
                    task_type="deep_research",
                    status=TaskStatus.PENDING,
                    input_data={
                        "query": query,
                        "research_type": research_request.research_type.value,
                        "params": research_request.params.model_dump(),
                        "stream": stream,
                        "context": research_request.context,
                    },
                    chat_id=chat_id,
                    created_at=datetime.utcnow(),
                )
                await task.insert()

                # Persist research start in unified history when linked to a chat
                if chat_id:
                    try:
                        await HistoryService.record_research_started(
                            chat_id=chat_id,
                            user_id=user_id,
                            task=task,
                            query=query,
                            params=(
                                research_request.params.model_dump()
                                if research_request.params
                                else None
                            ),
                        )
                    except Exception as history_error:
                        logger.warning(
                            "Failed to persist coordinated research start",
                            error=str(history_error),
                            chat_id=chat_id,
                            task_id=task_id,
                        )

                # Submit to Aletheia
                try:
                    aletheia_client = await get_aletheia_client()
                    aletheia_response = await aletheia_client.start_deep_research(
                        query=query,
                        task_id=task_id,
                        user_id=user_id,
                        params=research_request.params.model_dump(),
                        context=research_request.context,
                    )

                    if aletheia_response.status != "error":
                        task.status = TaskStatus.RUNNING
                        task.started_at = datetime.utcnow()
                        await task.save()

                except Exception as aletheia_error:
                    logger.warning(
                        "Aletheia unavailable for research", error=str(aletheia_error)
                    )
                    task.status = TaskStatus.RUNNING
                    await task.save()

                return {
                    "type": "deep_research",
                    "task_id": task_id,
                    "stream_url": f"/api/stream/{task_id}" if stream else None,
                    "status": "started",
                    "decision": decision.dict(),
                    "estimated_time_minutes": decision.complexity.estimated_time_minutes,
                    "processing_time_ms": round((time.time() - start_time) * 1000, 2),
                }

            else:
                # Execute simple chat (fixed temperature, temperature_service removed)
                saptiva_client = await get_saptiva_client()

                # Use fixed temperature (temperature_service was removed as it's not used with kill switch)
                fixed_temperature = 0.7

                # Build message history for context
                messages = [{"role": "user", "content": query}]

                if chat_id:
                    # Get recent chat history
                    chat_messages = (
                        await ChatMessage.find(ChatMessage.chat_id == chat_id)
                        .sort(ChatMessage.created_at)
                        .limit(10)
                        .to_list()
                    )

                    history = []
                    for msg in chat_messages[:-1]:  # Exclude the current query
                        history.append({"role": msg.role.value, "content": msg.content})

                    messages = history + messages

                # Get chat response with fixed temperature
                saptiva_response = await saptiva_client.chat_completion(
                    messages=messages,
                    model="Saptiva Turbo",
                    temperature=fixed_temperature,
                    max_tokens=1024,
                    stream=False,
                )

                logger.info(
                    "SAPTIVA response (legacy path, kill switch OFF)",
                    temperature=fixed_temperature,
                )

                return {
                    "type": "chat",
                    "response": saptiva_response,
                    "decision": decision.dict(),
                    "fallback_available": True,
                    "escalation_available": True,
                    "processing_time_ms": round((time.time() - start_time) * 1000, 2),
                }

        except Exception as e:
            logger.error("Error in coordinated research", error=str(e))

            # Fallback to simple response
            return {
                "type": "error",
                "error": str(e),
                "fallback_to_chat": True,
                "processing_time_ms": round((time.time() - start_time) * 1000, 2),
            }


# Singleton instance
_research_coordinator: Optional[ResearchCoordinator] = None


def get_research_coordinator() -> ResearchCoordinator:
    """Get singleton research coordinator instance."""
    global _research_coordinator
    if _research_coordinator is None:
        _research_coordinator = ResearchCoordinator()
    return _research_coordinator
