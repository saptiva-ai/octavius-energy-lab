#!/usr/bin/env python3
"""
Simple test for temperature calculation logic without full system dependencies.
Tests the core temperature mapping algorithm.
"""

import asyncio
import re


class SimpleTemperatureConfig:
    """Simplified configuration for temperature testing."""
    base_temperature: float = 0.5
    min_temperature: float = 0.1
    max_temperature: float = 0.7
    simple_threshold: float = 0.3
    complex_threshold: float = 0.7


class SimpleComplexityAnalyzer:
    """Simplified complexity analyzer for testing purposes."""

    def __init__(self):
        # Research indicator patterns (from research_coordinator.py)
        self.research_indicators = [
            r'\b(research findings|research shows|studies indicate|academic research|investigate.*research)\b',
            r'\b(literature review|systematic review|meta-analysis)\b',
            r'\b(what does research show|what do studies say)\b',
            r'\b(detailed comparison|comprehensive analysis|compare.*research|compare.*studies)\b',
            r'\b(pros and cons.*research|advantages and disadvantages.*analysis)\b',
            r'\b(comprehensive research|detailed analysis|thorough investigation)\b',
            r'\b(complete research guide|everything.*research|research overview)\b',
            r'\b(fact check.*sources|verify.*research|need evidence|show citations)\b',
            r'\b(according to research|based on studies|research consensus)\b',
            r'\b(latest research|recent studies|current literature|up-to-date research)\b',
            r'\b(research news|research developments|research trends|research updates)\b',
            r'\b(academic research|scientific study|technical analysis|peer-reviewed research)\b',
            r'\b(research methodology|study framework|research algorithm|research protocol)\b',
        ]

        self.chat_indicators = [
            r'^\s*what is\s+\w+\s*\??\s*$',
            r'^\s*define\s+\w+\s*\??\s*$',
            r'^\s*how to\s+\w+.*\??\s*$',
            r'^\s*how do I\s+\w+.*\??\s*$',
            r'^\s*can you\s+\w+.*\??\s*$',
            r'\b(what do you think|your opinion|do you believe)\b',
            r'\b(I think|I believe|in my opinion)\b',
            r'\b(tell me about|explain|help me understand)\b',
            r'\b(calculate|math|arithmetic|\+|\-|\*|\/|\=)\b',
            r'\b(write|create|make|generate|show me)\b.*\b(code|script|example)\b',
            r'\b(what|why|when|where|which|who)\s+(?!.*research)(?!.*study)(?!.*analysis)',
            r'\b(simple|basic|quick|short)\b.*\b(question|answer|explanation)\b',
            r'^\s*\S+(\s+\S+){0,8}\s*\??\s*$'
        ]

    async def analyze_query_complexity(self, query: str) -> dict:
        """Analyze query complexity (simplified version)."""

        factors = []
        score = 0.0

        # Check for simple greetings first
        simple_greetings = [
            r'^\s*(hola|hello|hi|hey|good morning|good afternoon|good evening|buenas)\s*(como estas|how are you|como estas|como andas)?\s*[?!.]*\s*$',
            r'^\s*(que tal|how\'s it going|what\'s up|sup)\s*[?!.]*\s*$',
            r'^\s*(gracias|thank you|thanks|merci)\s*[?!.]*\s*$',
            r'^\s*(bye|goodbye|adios|hasta luego|see you|chau)\s*[?!.]*\s*$',
            r'^\s*(si|yes|no|ok|okay)\s*[?!.]*\s*$',
            r'^\s*(eres|are you|you are)\s*(un\s*)?(mock|fake|real|bot|ai|artificial|robot)\s*[?!.]*\s*$',
            r'^\s*(que\s+eres|what\s+are\s+you|who\s+are\s+you)\s*[?!.]*\s*$',
            r'^\s*(como\s+te\s+llamas|what\s+is\s+your\s+name|whats\s+your\s+name)\s*[?!.]*\s*$',
            r'^\s*(puedes|can\s+you|are\s+you\s+able\s+to)\s+.*[?!.]*\s*$',
            r'^.{1,20}[?!.]*\s*$'
        ]

        query_lower = query.lower().strip()
        for pattern in simple_greetings:
            if re.match(pattern, query_lower, re.IGNORECASE):
                return {
                    "score": 0.0,
                    "reasoning": "Simple greeting or short response - direct chat appropriate",
                    "factors": ["Simple greeting/response"]
                }

        # Length factor
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
                factors.append(f"Research indicator")

        # Chat indicator patterns (reduce score)
        chat_matches = 0
        for pattern in self.chat_indicators:
            if re.search(pattern, query, re.IGNORECASE):
                chat_matches += 1
                score -= 0.3
                factors.append(f"Simple query indicator")

        # Question complexity
        question_marks = query.count('?')
        if question_marks > 1:
            score += 0.2
            factors.append(f"Multiple questions ({question_marks})")

        # AND/OR logic
        if re.search(r'\b(and|or|but|however|although)\b', query, re.IGNORECASE):
            score += 0.1
            factors.append("Complex logical structure")

        # Normalize score
        score = max(0.0, min(1.0, score))

        reasoning = f"Complexity score: {score:.2f}. "
        if research_matches > 0:
            reasoning += f"Detected {research_matches} research indicators. "
        if chat_matches > 0:
            reasoning += f"Detected {chat_matches} simple query indicators. "

        return {
            "score": score,
            "reasoning": reasoning,
            "factors": factors
        }


class SimpleTemperatureService:
    """Simplified temperature service for testing."""

    def __init__(self):
        self.config = SimpleTemperatureConfig()
        self.complexity_analyzer = SimpleComplexityAnalyzer()

    def _map_complexity_to_temperature(self, complexity_score: float) -> float:
        """Map complexity score to temperature."""
        score = max(0.0, min(1.0, complexity_score))

        if score <= self.config.simple_threshold:
            ratio = score / self.config.simple_threshold
            temperature = self.config.min_temperature + ratio * (self.config.base_temperature - self.config.min_temperature)
        elif score <= self.config.complex_threshold:
            temperature = self.config.base_temperature
        else:
            ratio = (score - self.config.complex_threshold) / (1.0 - self.config.complex_threshold)
            temperature = self.config.base_temperature + ratio * (self.config.max_temperature - self.config.base_temperature)

        return max(self.config.min_temperature, min(self.config.max_temperature, temperature))

    async def calculate_dynamic_temperature(self, query: str) -> dict:
        """Calculate temperature based on query complexity."""
        try:
            # Analyze complexity
            complexity = await self.complexity_analyzer.analyze_query_complexity(query)

            # Calculate temperature
            temperature = self._map_complexity_to_temperature(complexity["score"])

            # Generate reasoning
            if complexity["score"] <= self.config.simple_threshold:
                reasoning = f"Simple query (score: {complexity['score']:.2f}) - using low temperature ({temperature:.2f}) for focused, precise responses"
            elif complexity["score"] <= self.config.complex_threshold:
                reasoning = f"Medium complexity query (score: {complexity['score']:.2f}) - using moderate temperature ({temperature:.2f}) for balanced responses"
            else:
                reasoning = f"Complex query (score: {complexity['score']:.2f}) - using high temperature ({temperature:.2f}) for creative, exploratory responses"

            return {
                "temperature": temperature,
                "complexity_score": complexity["score"],
                "reasoning": reasoning,
                "complexity_factors": complexity["factors"]
            }

        except Exception as e:
            return {
                "temperature": self.config.base_temperature,
                "complexity_score": 0.5,
                "reasoning": f"Error occurred, using base temperature: {str(e)}",
                "complexity_factors": []
            }


async def test_temperature_service():
    """Test the dynamic temperature service."""
    print("🌡️  Testing Dynamic Temperature Service")
    print("=" * 50)

    service = SimpleTemperatureService()

    test_queries = [
        ("Hola", "Simple greeting"),
        ("¿Qué tal?", "Short casual question"),
        ("¿Cómo estás?", "Simple personal question"),
        ("Explica qué es Python", "Basic explanation request"),
        ("¿Cuáles son las mejores prácticas para el desarrollo de APIs REST?", "Medium complexity question"),
        ("Necesito un análisis exhaustivo de las últimas investigaciones sobre inteligencia artificial, sus aplicaciones en medicina, los desafíos éticos actuales y las tendencias futuras del sector", "Complex research request"),
        ("Compara los últimos estudios científicos sobre cambio climático y proporciona un análisis detallado de las metodologías de investigación utilizadas", "Research-heavy query"),
        ("research findings on machine learning applications in healthcare", "Explicit research query"),
        ("comprehensive analysis of recent studies in quantum computing", "Complex analytical request")
    ]

    print(f"Testing {len(test_queries)} different query types...\n")

    for query, description in test_queries:
        print(f"📝 Query: \"{query[:60]}{'...' if len(query) > 60 else ''}\"")
        print(f"   Type: {description}")

        result = await service.calculate_dynamic_temperature(query)

        print(f"   🌡️  Temperature: {result['temperature']:.2f}")
        print(f"   📊 Complexity Score: {result['complexity_score']:.2f}")
        print(f"   💭 Reasoning: {result['reasoning']}")
        if result['complexity_factors']:
            print(f"   🔍 Factors: {', '.join(result['complexity_factors'][:2])}{'...' if len(result['complexity_factors']) > 2 else ''}")

        print("-" * 50)

    print("\n✅ Temperature service test completed!")
    print("\n📊 Expected Temperature Ranges:")
    print("   • Simple greetings & short questions: 0.1 - 0.4")
    print("   • Medium complexity queries: 0.4 - 0.6")
    print("   • Complex research queries: 0.6 - 0.7")


if __name__ == "__main__":
    asyncio.run(test_temperature_service())