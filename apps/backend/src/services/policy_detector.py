"""
Policy Auto-Detection Service

Heurística para detectar la política de validación sin pedir client_name.
Analiza:
- Logos en portada (template matching)
- Texto de portada (nombres de empresas, dominios)
- Disclaimers característicos
- Patrones de formato

Returns:
    (policy_id, confidence_score)

Si confidence < 0.6 → Fallback a pregunta de desambiguación en chat (1 turno)
"""

from pathlib import Path
from typing import Dict, List, Tuple

import structlog

logger = structlog.get_logger(__name__)

# Confidence thresholds
CONFIDENCE_THRESHOLD = 0.6
HIGH_CONFIDENCE = 0.8

# Policy signatures
POLICY_SIGNATURES = {
    "demo-std": {
        "keywords": ["Demo Capital", "democapital", "www.democapital.com"],
        "disclaimers": [
            "Este documento es confidencial",
            "prohibida su distribución",
            "uso exclusivo",
        ],
        "logo_template": "assets/logo_template_414.png",
    },
    "bancomuestra": {
        "keywords": ["BancoMuestra", "Citibancomuestra", "bancomuestra.com"],
        "disclaimers": ["BancoMuestra", "Citigroup"],
        "logo_template": None,  # No template yet
    },
    # Add more policies as needed
}


async def detect_policy_from_document(
    pdf_path: Path, fragments: List[Dict]
) -> Tuple[str, float]:
    """
    Detect validation policy from document content using heuristics.

    Args:
        pdf_path: Path to PDF file
        fragments: List of extracted fragments with text and bbox

    Returns:
        (policy_id, confidence_score)

    Example:
        >>> fragments = await extract_fragments_with_bbox(pdf_path)
        >>> policy_id, score = await detect_policy_from_document(pdf_path, fragments)
        >>> if score >= 0.6:
        >>>     # Use detected policy
        >>> else:
        >>>     # Ask for clarification in chat
    """
    logger.info(
        "Starting policy detection",
        pdf_path=str(pdf_path),
        fragment_count=len(fragments),
    )

    # Scores for each policy
    scores: Dict[str, float] = {
        policy_id: 0.0 for policy_id in POLICY_SIGNATURES.keys()
    }

    # 1. Analyze portada (first 3 pages)
    portada_text = _extract_portada_text(fragments)
    keyword_scores = _score_by_keywords(portada_text)

    # 2. Analyze disclaimers across all pages
    disclaimer_scores = _score_by_disclaimers(fragments)

    # 3. Logo detection (if template available)
    logo_scores = await _score_by_logo(pdf_path)

    # 4. Combine signals
    for policy_id in POLICY_SIGNATURES.keys():
        weights = {"keywords": 0.3, "disclaimers": 0.4, "logo": 0.3}

        scores[policy_id] = (
            keyword_scores.get(policy_id, 0.0) * weights["keywords"]
            + disclaimer_scores.get(policy_id, 0.0) * weights["disclaimers"]
            + logo_scores.get(policy_id, 0.0) * weights["logo"]
        )

    # 5. Select best match
    best_policy = max(scores.items(), key=lambda x: x[1])
    policy_id, confidence = best_policy

    logger.info(
        "Policy detection complete",
        policy_id=policy_id,
        confidence=confidence,
        all_scores=scores,
    )

    # If confidence too low, return 'auto' to trigger disambiguation
    if confidence < CONFIDENCE_THRESHOLD:
        logger.warning(
            "Low confidence in policy detection, will ask user",
            confidence=confidence,
            threshold=CONFIDENCE_THRESHOLD,
        )
        return ("auto", 0.0)

    return (policy_id, confidence)


def _extract_portada_text(fragments: List[Dict], max_pages: int = 3) -> str:
    """Extract text from first N pages (portada)"""
    portada_fragments = [f for f in fragments if f.get("page", 999) <= max_pages]

    text = " ".join(f.get("text", "") for f in portada_fragments)
    return text.lower()


def _score_by_keywords(text: str) -> Dict[str, float]:
    """Score policies based on keyword presence in text"""
    scores = {}

    for policy_id, config in POLICY_SIGNATURES.items():
        keywords = config["keywords"]
        matches = sum(1 for kw in keywords if kw.lower() in text)

        # Normalize by number of keywords
        score = matches / len(keywords) if keywords else 0.0
        scores[policy_id] = score

        logger.debug(
            "Keyword scoring",
            policy_id=policy_id,
            matches=matches,
            total_keywords=len(keywords),
            score=score,
        )

    return scores


def _score_by_disclaimers(fragments: List[Dict]) -> Dict[str, float]:
    """Score policies based on disclaimer patterns"""
    scores = {}

    # Collect all footer text (likely location for disclaimers)
    footer_texts = []
    for frag in fragments:
        # Heuristic: fragments in bottom 20% of page are footers
        bbox = frag.get("bbox")
        if bbox:
            y0, y1 = bbox[1], bbox[3]
            page_height = 842  # A4 height in points (approximate)
            if y1 > page_height * 0.8:  # Bottom 20%
                footer_texts.append(frag.get("text", "").lower())

    combined_footer = " ".join(footer_texts)

    for policy_id, config in POLICY_SIGNATURES.items():
        disclaimers = config["disclaimers"]
        matches = sum(1 for disc in disclaimers if disc.lower() in combined_footer)

        # Normalize
        score = matches / len(disclaimers) if disclaimers else 0.0
        scores[policy_id] = score

        logger.debug(
            "Disclaimer scoring",
            policy_id=policy_id,
            matches=matches,
            total_disclaimers=len(disclaimers),
            score=score,
        )

    return scores


async def _score_by_logo(pdf_path: Path) -> Dict[str, float]:
    """
    Score policies based on logo detection using template matching.

    TODO: Implement OpenCV template matching when templates are available.
    For now, returns 0.0 for all policies.
    """
    scores = {}

    for policy_id, config in POLICY_SIGNATURES.items():
        template_path = config.get("logo_template")

        if not template_path:
            scores[policy_id] = 0.0
            continue

        # TODO: Implement logo detection
        # 1. Load template from assets/
        # 2. Rasterize first page of PDF
        # 3. Run cv2.matchTemplate()
        # 4. Return confidence score

        logger.debug(
            "Logo detection skipped (not implemented)",
            policy_id=policy_id,
            template_path=template_path,
        )
        scores[policy_id] = 0.0

    return scores


def format_disambiguation_question(scores: Dict[str, float]) -> str:
    """
    Format a natural language question to ask user for policy clarification.

    Returns a question like:
    "¿Este documento es de Demo Capital o BancoMuestra? Por favor especifica el cliente."
    """
    # Get top 2 candidates
    sorted_policies = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:2]

    if len(sorted_policies) < 2:
        return "Por favor especifica el cliente para este documento."

    policy1, score1 = sorted_policies[0]
    policy2, score2 = sorted_policies[1]

    # Format policy names for display
    name_map = {"demo-std": "Demo Capital", "bancomuestra": "BancoMuestra"}

    name1 = name_map.get(policy1, policy1)
    name2 = name_map.get(policy2, policy2)

    question = (
        f"No pude detectar el cliente con certeza. "
        f"¿Este documento es de {name1} o {name2}? "
        f"Por favor responde con el nombre del cliente."
    )

    return question
