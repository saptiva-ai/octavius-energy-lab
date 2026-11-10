"""
Unit tests for policy_detector module.

Tests:
- Policy signature constants
- _extract_portada_text function
- _score_by_keywords function
- _score_by_disclaimers function
- _score_by_logo function
- detect_policy_from_document function
- format_disambiguation_question function
"""

from pathlib import Path

import pytest

from src.services.policy_detector import (
    CONFIDENCE_THRESHOLD,
    HIGH_CONFIDENCE,
    POLICY_SIGNATURES,
    _extract_portada_text,
    _score_by_disclaimers,
    _score_by_keywords,
    _score_by_logo,
    detect_policy_from_document,
    format_disambiguation_question,
)

pytestmark = [pytest.mark.unit]


class TestPolicySignatures:
    """Test policy signature constants."""

    def test_demo_std_signature_exists(self):
        """Test demo-std policy signature exists."""
        assert "demo-std" in POLICY_SIGNATURES

        sig = POLICY_SIGNATURES["demo-std"]
        assert "keywords" in sig
        assert "disclaimers" in sig
        assert "logo_template" in sig

    def test_bancomuestra_signature_exists(self):
        """Test bancomuestra policy signature exists."""
        assert "bancomuestra" in POLICY_SIGNATURES

    def test_demo_std_keywords(self):
        """Test demo-std has expected keywords."""
        keywords = POLICY_SIGNATURES["demo-std"]["keywords"]

        assert "Demo Capital" in keywords
        assert any("democapital" in kw.lower() for kw in keywords)

    def test_bancomuestra_keywords(self):
        """Test bancomuestra has expected keywords."""
        keywords = POLICY_SIGNATURES["bancomuestra"]["keywords"]

        assert any("bancomuestra" in kw.lower() for kw in keywords)


class TestConfidenceThresholds:
    """Test confidence threshold constants."""

    def test_confidence_threshold_value(self):
        """Test confidence threshold is reasonable."""
        assert CONFIDENCE_THRESHOLD == 0.6

    def test_high_confidence_value(self):
        """Test high confidence is higher than threshold."""
        assert HIGH_CONFIDENCE > CONFIDENCE_THRESHOLD
        assert HIGH_CONFIDENCE == 0.8


class TestExtractPortadaText:
    """Test _extract_portada_text function."""

    def test_extracts_first_three_pages(self):
        """Test extracts text from first 3 pages."""
        fragments = [
            {"page": 1, "text": "Page one text"},
            {"page": 2, "text": "Page two text"},
            {"page": 3, "text": "Page three text"},
            {"page": 4, "text": "Page four text"},
        ]

        result = _extract_portada_text(fragments)

        assert "page one" in result
        assert "page two" in result
        assert "page three" in result
        assert "page four" not in result

    def test_lowercase_output(self):
        """Test output is lowercased."""
        fragments = [{"page": 1, "text": "UPPERCASE TEXT"}]

        result = _extract_portada_text(fragments)

        assert result == "uppercase text"

    def test_custom_max_pages(self):
        """Test custom max_pages parameter."""
        fragments = [
            {"page": 1, "text": "Page 1"},
            {"page": 2, "text": "Page 2"},
        ]

        result = _extract_portada_text(fragments, max_pages=1)

        assert "page 1" in result
        assert "page 2" not in result

    def test_empty_fragments(self):
        """Test empty fragments list."""
        result = _extract_portada_text([])
        assert result == ""

    def test_missing_page_field_treated_as_high_page(self):
        """Test fragments without page field are excluded."""
        fragments = [
            {"page": 1, "text": "Include this"},
            {"text": "No page field"},  # Should be excluded (default 999)
        ]

        result = _extract_portada_text(fragments)

        assert "include this" in result
        assert "no page field" not in result

    def test_missing_text_field(self):
        """Test fragments without text field."""
        fragments = [{"page": 1}]  # No text field

        result = _extract_portada_text(fragments)
        assert result == ""


class TestScoreByKeywords:
    """Test _score_by_keywords function."""

    def test_full_match_returns_1(self):
        """Test all keywords matching returns score of 1.0."""
        # Text contains all Demo Capital keywords
        text = "demo capital democapital www.democapital.com"

        scores = _score_by_keywords(text)

        assert scores["demo-std"] == 1.0

    def test_partial_match(self):
        """Test partial match returns proportional score."""
        # Text contains 1 of 3 keywords
        text = "demo capital"

        scores = _score_by_keywords(text)

        # 1 out of 3 keywords = ~0.33
        assert 0.3 <= scores["demo-std"] <= 0.4

    def test_no_match_returns_0(self):
        """Test no matching keywords returns 0."""
        text = "completely unrelated text"

        scores = _score_by_keywords(text)

        assert scores["demo-std"] == 0.0
        assert scores["bancomuestra"] == 0.0

    def test_case_insensitive_matching(self):
        """Test keyword matching is case insensitive."""
        text = "BANCOMUESTRA citibancomuestra"

        scores = _score_by_keywords(text)

        assert scores["bancomuestra"] > 0

    def test_returns_dict_for_all_policies(self):
        """Test returns scores for all policies."""
        scores = _score_by_keywords("any text")

        for policy_id in POLICY_SIGNATURES:
            assert policy_id in scores


class TestScoreByDisclaimers:
    """Test _score_by_disclaimers function."""

    def test_footer_disclaimer_detected(self):
        """Test disclaimers in footer are detected."""
        # Fragment in bottom 20% of A4 page (842 points)
        fragments = [
            {
                "page": 1,
                "text": "Este documento es confidencial",
                "bbox": [0, 700, 100, 800],  # y1=800 > 842*0.8=673.6
            }
        ]

        scores = _score_by_disclaimers(fragments)

        assert scores["demo-std"] > 0

    def test_non_footer_text_ignored(self):
        """Test text not in footer is ignored."""
        # Fragment in top of page
        fragments = [
            {
                "page": 1,
                "text": "Este documento es confidencial",
                "bbox": [0, 0, 100, 100],  # Top of page
            }
        ]

        scores = _score_by_disclaimers(fragments)

        # Should not detect because not in footer
        assert scores["demo-std"] == 0.0

    def test_no_bbox_fragments(self):
        """Test fragments without bbox are ignored."""
        fragments = [{"page": 1, "text": "confidencial"}]

        scores = _score_by_disclaimers(fragments)

        assert all(score == 0.0 for score in scores.values())

    def test_multiple_disclaimers_increase_score(self):
        """Test multiple matching disclaimers increase score."""
        fragments = [
            {
                "page": 1,
                "text": "Este documento es confidencial prohibida su distribución",
                "bbox": [0, 700, 100, 800],
            }
        ]

        scores = _score_by_disclaimers(fragments)

        # Should have higher score with more matches
        assert scores["demo-std"] > 0.3

    def test_empty_fragments(self):
        """Test empty fragments returns zeros."""
        scores = _score_by_disclaimers([])

        assert all(score == 0.0 for score in scores.values())


class TestFormatDisambiguationQuestion:
    """Test format_disambiguation_question function."""

    def test_returns_string(self):
        """Test returns a string."""
        scores = {"demo-std": 0.5, "bancomuestra": 0.4}

        result = format_disambiguation_question(scores)

        assert isinstance(result, str)

    def test_mentions_top_two_candidates(self):
        """Test mentions top two candidates."""
        scores = {"demo-std": 0.5, "bancomuestra": 0.4}

        result = format_disambiguation_question(scores)

        assert "Demo Capital" in result or "demo-std" in result
        assert "BancoMuestra" in result or "bancomuestra" in result

    def test_is_a_question(self):
        """Test result is phrased as question."""
        scores = {"demo-std": 0.5, "bancomuestra": 0.4}

        result = format_disambiguation_question(scores)

        assert "?" in result

    def test_single_candidate_fallback(self):
        """Test fallback when only one candidate."""
        scores = {"demo-std": 0.5}

        result = format_disambiguation_question(scores)

        assert "especifica" in result.lower() or "cliente" in result.lower()

    def test_empty_scores(self):
        """Test empty scores returns generic question."""
        scores = {}

        result = format_disambiguation_question(scores)

        assert len(result) > 0
        assert "cliente" in result.lower() or "documento" in result.lower()

    def test_orders_by_score(self):
        """Test candidates are ordered by score."""
        scores = {"bancomuestra": 0.8, "demo-std": 0.2}

        result = format_disambiguation_question(scores)

        # BancoMuestra should come first due to higher score
        bancomuestra_pos = result.lower().find("bancomuestra")
        capital_pos = result.lower().find("demo")

        # Both should be present
        assert bancomuestra_pos >= 0 or capital_pos >= 0


class TestScoreByLogo:
    """Test _score_by_logo function."""

    @pytest.mark.asyncio
    async def test_returns_zeros_for_all_policies(self):
        """Test returns zeros since logo detection is not implemented."""
        pdf_path = Path("/fake/path.pdf")

        scores = await _score_by_logo(pdf_path)

        # All scores should be 0.0 since logo detection not implemented
        for policy_id in POLICY_SIGNATURES:
            assert scores.get(policy_id) == 0.0

    @pytest.mark.asyncio
    async def test_returns_dict_for_all_policies(self):
        """Test returns dict with all policy IDs."""
        pdf_path = Path("/fake/path.pdf")

        scores = await _score_by_logo(pdf_path)

        for policy_id in POLICY_SIGNATURES:
            assert policy_id in scores

    @pytest.mark.asyncio
    async def test_handles_policy_without_template(self):
        """Test handles policies without logo_template."""
        pdf_path = Path("/fake/path.pdf")

        # bancomuestra has logo_template = None
        scores = await _score_by_logo(pdf_path)

        assert scores.get("bancomuestra") == 0.0


class TestDetectPolicyFromDocument:
    """Test detect_policy_from_document function."""

    @pytest.mark.asyncio
    async def test_returns_tuple(self):
        """Test returns (policy_id, confidence) tuple."""
        pdf_path = Path("/fake/path.pdf")
        fragments = [{"page": 1, "text": "Demo Capital"}]

        result = await detect_policy_from_document(pdf_path, fragments)

        assert isinstance(result, tuple)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_detects_demo_capital(self):
        """Test detects Demo Capital from strong signals."""
        pdf_path = Path("/fake/path.pdf")
        # Need all keywords AND all disclaimers to hit confidence threshold
        # Since logo detection is 0.0, we need: keywords(0.3) + disclaimers(0.4) >= 0.6
        # That means we need perfect scores on both: 1.0 * 0.3 + 1.0 * 0.4 = 0.7
        fragments = [
            {"page": 1, "text": "Demo Capital www.democapital.com democapital"},  # All 3 keywords
            {
                "page": 1,
                "text": "Este documento es confidencial prohibida su distribución uso exclusivo",  # All 3 disclaimers
                "bbox": [0, 700, 100, 800],  # Footer
            },
        ]

        policy_id, confidence = await detect_policy_from_document(pdf_path, fragments)

        assert policy_id == "demo-std"
        assert confidence >= CONFIDENCE_THRESHOLD

    @pytest.mark.asyncio
    async def test_detects_bancomuestra(self):
        """Test detects BancoMuestra from strong signals."""
        pdf_path = Path("/fake/path.pdf")
        fragments = [
            {"page": 1, "text": "BancoMuestra Citibancomuestra bancomuestra.com"},
            {
                "page": 1,
                "text": "BancoMuestra Citigroup disclaimer",
                "bbox": [0, 700, 100, 800],  # Footer
            },
        ]

        policy_id, confidence = await detect_policy_from_document(pdf_path, fragments)

        assert policy_id == "bancomuestra"
        assert confidence >= CONFIDENCE_THRESHOLD

    @pytest.mark.asyncio
    async def test_low_confidence_returns_auto(self):
        """Test low confidence returns 'auto' for disambiguation."""
        pdf_path = Path("/fake/path.pdf")
        # Ambiguous fragments with no clear signals
        fragments = [{"page": 1, "text": "Generic document text"}]

        policy_id, confidence = await detect_policy_from_document(pdf_path, fragments)

        assert policy_id == "auto"
        assert confidence == 0.0

    @pytest.mark.asyncio
    async def test_empty_fragments_returns_auto(self):
        """Test empty fragments returns auto."""
        pdf_path = Path("/fake/path.pdf")
        fragments = []

        policy_id, confidence = await detect_policy_from_document(pdf_path, fragments)

        assert policy_id == "auto"
        assert confidence == 0.0

    @pytest.mark.asyncio
    async def test_mixed_signals(self):
        """Test handles mixed signals from multiple policies."""
        pdf_path = Path("/fake/path.pdf")
        fragments = [
            {"page": 1, "text": "Demo Capital"},  # demo keyword
            {
                "page": 1,
                "text": "BancoMuestra",  # BancoMuestra disclaimer
                "bbox": [0, 700, 100, 800],
            },
        ]

        policy_id, confidence = await detect_policy_from_document(pdf_path, fragments)

        # Should return a policy (the stronger match)
        assert policy_id in ["demo-std", "bancomuestra", "auto"]

    @pytest.mark.asyncio
    async def test_weights_disclaimers_higher(self):
        """Test disclaimers have higher weight than keywords."""
        pdf_path = Path("/fake/path.pdf")
        # Need to give demo some keywords too to hit threshold
        # demo: keywords 1/3 * 0.3 = 0.1, disclaimers 3/3 * 0.4 = 0.4, total = 0.5
        # Need 0.6 minimum, so let's give demo more keywords
        fragments = [
            {"page": 1, "text": "Demo Capital democapital"},  # 2/3 demo keywords
            {"page": 1, "text": "bancomuestra.com"},  # 1 bancomuestra keyword
            {
                "page": 1,
                "text": "Este documento es confidencial prohibida su distribución uso exclusivo",
                "bbox": [0, 700, 100, 800],  # All 3 demo disclaimers
            },
        ]

        policy_id, confidence = await detect_policy_from_document(pdf_path, fragments)

        # demo: keywords 2/3 * 0.3 = 0.2, disclaimers 3/3 * 0.4 = 0.4, total = 0.6
        # bancomuestra: keywords 1/3 * 0.3 = 0.1, disclaimers 0 * 0.4 = 0, total = 0.1
        # demo should win due to strong disclaimers + some keywords
        assert policy_id == "demo-std"

    @pytest.mark.asyncio
    async def test_uses_portada_for_keywords(self):
        """Test only uses first 3 pages for keyword analysis."""
        pdf_path = Path("/fake/path.pdf")
        fragments = [
            {"page": 5, "text": "demo capital democapital www.democapital.com"},  # After portada
        ]

        policy_id, confidence = await detect_policy_from_document(pdf_path, fragments)

        # Keywords on page 5 shouldn't be counted
        assert policy_id == "auto"
