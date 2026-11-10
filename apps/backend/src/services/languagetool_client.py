"""
LanguageTool client for grammar and spelling checks.
"""

import os
from typing import Any, Dict, List

import httpx
import structlog

logger = structlog.get_logger(__name__)


class LanguageToolClient:
    """Client for LanguageTool API"""

    def __init__(self):
        self.base_url = os.getenv("LANGUAGETOOL_URL", "http://localhost:8010")
        self.default_language = "es"
        self.timeout = 30.0

        # Rules to disable (too noisy)
        self.disabled_rules = [
            "WHITESPACE_RULE",
            "DOUBLE_PUNCTUATION",
            "UNPAIRED_BRACKETS",
        ]

    async def check_text(
        self,
        text: str,
        language: str = "es",
        enabled_only: bool = False,
    ) -> Dict[str, Any]:
        """
        Check text for grammar and spelling errors.

        Args:
            text: Text to check
            language: Language code (es, en, etc.)
            enabled_only: Only use enabled rules

        Returns:
            LanguageTool response with matches
        """
        url = f"{self.base_url}/v2/check"

        data = {
            "text": text,
            "language": language or self.default_language,
            "enabledOnly": str(enabled_only).lower(),
            "disabledRules": ",".join(self.disabled_rules),
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, data=data)
                response.raise_for_status()
                result = response.json()

                logger.info(
                    "LanguageTool check completed",
                    text_length=len(text),
                    matches=len(result.get("matches", [])),
                    language=language,
                )

                return result

        except httpx.TimeoutException:
            logger.error("LanguageTool request timeout", url=url)
            raise Exception("LanguageTool timeout")
        except httpx.HTTPStatusError as e:
            logger.error(
                "LanguageTool HTTP error", status=e.response.status_code, url=url
            )
            raise Exception(f"LanguageTool error: {e.response.status_code}")
        except Exception as e:
            logger.error("LanguageTool request failed", error=str(e), url=url)
            raise

    def parse_matches(
        self, lt_response: Dict[str, Any]
    ) -> tuple[List[Dict], List[Dict]]:
        """
        Parse LanguageTool response into spelling and grammar findings.

        Args:
            lt_response: LanguageTool API response

        Returns:
            Tuple of (spelling_findings, grammar_findings)
        """
        matches = lt_response.get("matches", [])

        spelling_findings = []
        grammar_findings = []

        for match in matches:
            rule_id = match.get("rule", {}).get("id", "")
            issue_type = match.get("rule", {}).get("issueType", "")

            offset = match.get("offset", 0)
            length = match.get("length", 0)
            message = match.get("message", "")
            replacements = match.get("replacements", [])

            # Extract span from context
            context = match.get("context", {})
            context_text = context.get("text", "")
            context_offset = context.get("offset", 0)
            context_length = context.get("length", 0)

            span = context_text[context_offset : context_offset + context_length]
            suggestions = [r.get("value") for r in replacements[:5]]  # Top 5

            # Classify as spelling or grammar
            if (
                issue_type == "misspelling"
                or "SPELLING" in rule_id
                or "MORFOLOGIK" in rule_id
            ):
                spelling_findings.append(
                    {
                        "span": span,
                        "suggestions": suggestions,
                        "offset": offset,
                        "length": length,
                        "rule": rule_id,
                    }
                )
            else:
                grammar_findings.append(
                    {
                        "span": span,
                        "rule": rule_id,
                        "explain": message,
                        "suggestions": suggestions,
                        "offset": offset,
                        "length": length,
                    }
                )

        logger.info(
            "Parsed LanguageTool matches",
            spelling=len(spelling_findings),
            grammar=len(grammar_findings),
        )

        return spelling_findings, grammar_findings

    async def health_check(self) -> bool:
        """Check if LanguageTool service is available"""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/v2/languages")
                return response.status_code == 200
        except Exception as e:
            logger.error("LanguageTool health check failed", error=str(e))
            return False


# Singleton instance
languagetool_client = LanguageToolClient()
