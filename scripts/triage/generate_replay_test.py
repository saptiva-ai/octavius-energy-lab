#!/usr/bin/env python3
"""
Replay Test Generator — Auto-generate E2E regression tests from feedback data.

Given feedback IDs or a date, generates a test file that replays the exact
multi-turn conversations and validates that bugs are fixed.

Usage:
    python scripts/triage/generate_replay_test.py \
      --feedbacks FDBK-0109,FDBK-0111 \
      --backend-url http://localhost:18000

    python scripts/triage/generate_replay_test.py \
      --date 2026-02-10 \
      --backend-url http://localhost:18000 \
      --dry-run
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import textwrap
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import requests
except ImportError:
    print("ERROR: 'requests' package required. Install: pip install requests")
    sys.exit(2)

try:
    from jinja2 import Environment, FileSystemLoader
except ImportError:
    print("ERROR: 'jinja2' package required. Install: pip install jinja2")
    sys.exit(2)


SCRIPT_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = SCRIPT_DIR / "templates"
DEFAULT_OUTPUT_DIR = (
    Path(__file__).resolve().parents[2] / "tests" / "e2e" / "regression"
)


# ══════════════════════════════════════════════════════════════════════════════
# Bug pattern detection
# ══════════════════════════════════════════════════════════════════════════════

# Known bug patterns and their validator types
BUG_PATTERNS = {
    "STALE_CHART": {
        "keywords": [r"\b20(2[4-9]|3\d)\b"],
        "validator_type": "stale_chart",
    },
    "COMPARISON_FORMAT": {
        "keywords": [r"\bvs\.?\b", r"\bversus\b", r"\bcompar\w+\b"],
        "validator_type": "comparison_format",
    },
    "CATALOG_MISS": {
        "keywords": [r"\bclave\b", r"\bcódigo\b", r"\bcatalogo\b"],
        "validator_type": "catalog",
    },
    "STATE_LEAK": {
        "keywords": [],  # Detected from multi-turn context, not keywords
        "validator_type": "state_leak",
    },
}


@dataclass
class ValidatorSpec:
    """Specification for an auto-generated validator function."""

    name: str
    type: str  # stale_chart, comparison_format, catalog, state_leak, generic
    docstring: str
    expected_years: List[str] = field(default_factory=list)
    expected_traces: int = 2
    expected_banks: Optional[str] = None  # Python set literal as string
    leaked_banks: List[str] = field(default_factory=list)
    expected_codes: List[str] = field(default_factory=list)


@dataclass
class StepSpec:
    """Specification for a conversation step in the generated test."""

    step_id: str
    feedback_id: str
    ticket: str
    query: str
    validator_name: str
    description: str


@dataclass
class ConversationSpec:
    """Specification for a conversation in the generated test."""

    name: str
    var_name: str  # Python-safe variable name
    original_conv_id: str
    description: str
    steps: List[StepSpec] = field(default_factory=list)
    step_count: int = 0


class TriageAPIClient:
    """Client for the internal feedback API endpoints."""

    def __init__(self, backend_url: str, api_key: str) -> None:
        self.backend_url = backend_url.rstrip("/")
        self.headers = {
            "Content-Type": "application/json",
            "X-Internal-Key": api_key,
        }

    def query_feedback(self, **kwargs: Any) -> List[Dict[str, Any]]:
        resp = requests.post(
            f"{self.backend_url}/api/internal/feedback/query",
            json=kwargs,
            headers=self.headers,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def get_conversations(
        self, conversation_ids: List[str]
    ) -> Dict[str, Any]:
        resp = requests.post(
            f"{self.backend_url}/api/internal/feedback/conversations",
            json={
                "conversation_ids": conversation_ids,
                "include_artifacts": True,
            },
            headers=self.headers,
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()

    def get_stale_charts(self, **kwargs: Any) -> List[Dict[str, Any]]:
        resp = requests.get(
            f"{self.backend_url}/api/internal/feedback/stale-charts",
            params=kwargs,
            headers=self.headers,
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()


def _safe_var_name(s: str) -> str:
    """Convert a string to a safe Python variable name."""
    return re.sub(r"[^a-zA-Z0-9]", "_", s).strip("_").upper()


def _extract_years(query: str) -> List[str]:
    """Extract year references from a user query."""
    return sorted(set(re.findall(r"\b(20[2-3]\d)\b", query)))


def _detect_bug_pattern(
    query: str,
    feedback: Dict[str, Any],
    stale_verdicts: Dict[str, str],
) -> Tuple[str, str]:
    """
    Detect the most likely bug pattern for a feedback case.

    Returns (pattern_name, validator_type).
    """
    feedback_id = feedback.get("feedback_id", "")

    # Check stale-chart verdicts first (deterministic)
    verdict = stale_verdicts.get(feedback_id, "")
    if verdict == "STALE":
        return "STALE_CHART", "stale_chart"
    if verdict == "COMPARISON_FORMAT":
        return "COMPARISON_FORMAT", "comparison_format"

    # Keyword-based detection
    query_lower = query.lower()
    if re.search(r"\bvs\.?\b|\bversus\b|\bcompar\w+\b", query_lower):
        years = _extract_years(query)
        if len(years) >= 2:
            return "COMPARISON_FORMAT", "comparison_format"

    if re.search(r"\bclave\b|\bcódigo\b|\bcatalog\w*\b", query_lower):
        return "CATALOG_MISS", "catalog"

    if _extract_years(query):
        return "STALE_CHART", "stale_chart"

    return "GENERIC", "generic"


def _build_validator(
    feedback: Dict[str, Any],
    query: str,
    pattern: str,
    validator_type: str,
    step_index: int,
    conv_index: int,
) -> ValidatorSpec:
    """Build a validator specification for a feedback case."""
    feedback_id = feedback.get("feedback_id", "unknown")
    safe_id = re.sub(r"[^a-zA-Z0-9]", "_", feedback_id).lower()
    name = f"_check_{safe_id}_s{step_index}"

    if validator_type == "stale_chart":
        years = _extract_years(query)
        return ValidatorSpec(
            name=name,
            type="stale_chart",
            docstring=f"{feedback_id}: Chart must include {', '.join(years)} data.",
            expected_years=years or ["2025"],
        )

    if validator_type == "comparison_format":
        years = _extract_years(query)
        return ValidatorSpec(
            name=name,
            type="comparison_format",
            docstring=f"{feedback_id}: Comparison query should produce {len(years)} traces.",
            expected_traces=max(len(years), 2),
        )

    if validator_type == "catalog":
        # Try to extract expected bank codes from context
        context = feedback.get("context") or {}
        response = context.get("response_text", "")
        codes = re.findall(r"0{4}04\d{4}", response)
        return ValidatorSpec(
            name=name,
            type="catalog",
            docstring=f"{feedback_id}: Catalog lookup should return correct code.",
            expected_codes=codes if codes else ["040"],
        )

    return ValidatorSpec(
        name=name,
        type="generic",
        docstring=f"{feedback_id}: Response should have content or chart.",
    )


def generate_replay_test(
    date: str,
    backend_url: str,
    api_key: str,
    feedback_ids: Optional[List[str]] = None,
    output_path: Optional[Path] = None,
    dry_run: bool = False,
) -> str:
    """Generate a replay test file from feedback data."""
    client = TriageAPIClient(backend_url, api_key)

    # Gather feedback data
    if feedback_ids:
        print(f"[1/4] Querying {len(feedback_ids)} specific feedbacks...")
        feedbacks = client.query_feedback(feedback_ids=feedback_ids, limit=100)
    else:
        print(f"[1/4] Querying thumbs-down for {date}...")
        date_from = f"{date}T06:00:00"
        next_day = (datetime.fromisoformat(date) + timedelta(days=1)).strftime(
            "%Y-%m-%d"
        )
        date_to = f"{next_day}T06:00:00"
        feedbacks = client.query_feedback(
            date_from=date_from, date_to=date_to, rating="down", limit=100
        )

    if not feedbacks:
        print("No feedback found — nothing to generate.")
        return ""

    print(f"  Found {len(feedbacks)} feedback records")

    # Get stale chart verdicts
    print(f"[2/4] Checking stale chart verdicts...")
    try:
        stale_params: Dict[str, str] = {}
        if not feedback_ids:
            stale_params = {"date_from": date_from, "date_to": date_to}
        stale_charts = client.get_stale_charts(**stale_params)
        stale_verdicts = {
            sc.get("feedback_id", ""): sc.get("verdict", "")
            for sc in stale_charts
            if sc.get("feedback_id")
        }
    except Exception as e:
        print(f"  Warning: Could not get stale charts: {e}")
        stale_verdicts = {}

    # Get conversation threads
    conv_ids = list(set(
        fb.get("conversation_id", "")
        for fb in feedbacks
        if fb.get("conversation_id")
    ))
    print(f"[3/4] Fetching {len(conv_ids)} conversation threads...")
    conversations_data = client.get_conversations(conv_ids) if conv_ids else {}

    # Group feedbacks by conversation
    by_conv: Dict[str, List[Dict[str, Any]]] = {}
    for fb in feedbacks:
        cid = fb.get("conversation_id", "")
        by_conv.setdefault(cid, []).append(fb)

    # Build conversation specs and validators
    print(f"[4/4] Building test specifications...")
    all_validators: List[ValidatorSpec] = []
    all_conversations: List[ConversationSpec] = []

    for conv_idx, (conv_id, conv_feedbacks) in enumerate(by_conv.items()):
        conv_data = conversations_data.get(conv_id, {})
        messages = conv_data.get("messages", [])

        # Build steps from conversation messages
        conv_name = f"replay-{conv_id[:8]}"
        var_name = _safe_var_name(conv_name)

        conv_spec = ConversationSpec(
            name=conv_name,
            var_name=var_name,
            original_conv_id=conv_id,
            description=f"{len(conv_feedbacks)} thumbs-down in {len(messages)}-message conversation",
        )

        # Map feedback to the user query that preceded the rated message
        fb_by_msg = {fb.get("message_id", ""): fb for fb in conv_feedbacks}

        step_idx = 0
        for i, msg in enumerate(messages):
            if msg.get("role") != "user":
                continue

            # Check if the NEXT assistant message has feedback
            next_msg = messages[i + 1] if i + 1 < len(messages) else None
            if not next_msg or next_msg.get("role") != "assistant":
                continue

            fb = fb_by_msg.get(next_msg.get("id", ""))
            if not fb:
                # No feedback on this turn — still include as context step
                # but only if there's a feedback later in the conversation
                has_later_fb = any(
                    fb_by_msg.get(m.get("id", ""))
                    for m in messages[i + 2 :]
                    if m.get("role") == "assistant"
                )
                if has_later_fb:
                    validator = ValidatorSpec(
                        name=f"_check_context_{conv_idx}_s{step_idx}",
                        type="generic",
                        docstring="Context step: baseline query before feedback turn.",
                    )
                    all_validators.append(validator)
                    conv_spec.steps.append(
                        StepSpec(
                            step_id=f"C{conv_idx}-S{step_idx}",
                            feedback_id="CONTEXT",
                            ticket=f"replay-{date}",
                            query=msg.get("content", "").replace('"', '\\"'),
                            validator_name=validator.name,
                            description="Context step (no feedback)",
                        )
                    )
                    step_idx += 1
                continue

            # This turn has feedback — detect pattern and build validator
            query = msg.get("content", "")
            context = fb.get("context") or {}
            original_query = context.get("original_query", query)

            pattern, vtype = _detect_bug_pattern(
                original_query, fb, stale_verdicts
            )

            validator = _build_validator(
                fb, original_query, pattern, vtype, step_idx, conv_idx
            )
            all_validators.append(validator)

            feedback_id = fb.get("feedback_id", f"FB-{step_idx}")
            conv_spec.steps.append(
                StepSpec(
                    step_id=f"C{conv_idx}-S{step_idx}",
                    feedback_id=feedback_id,
                    ticket=f"{pattern.lower().replace('_', '-')}-{date}",
                    query=original_query.replace('"', '\\"'),
                    validator_name=validator.name,
                    description=f"{pattern}: {fb.get('reason', 'no reason')[:60]}",
                )
            )
            step_idx += 1

        conv_spec.step_count = len(conv_spec.steps)
        if conv_spec.steps:
            all_conversations.append(conv_spec)

    if not all_conversations:
        print("No testable conversations found.")
        return ""

    # Determine output path
    if output_path is None:
        safe_date = date.replace("-", "_")
        output_path = DEFAULT_OUTPUT_DIR / f"test_feedback_replay_{safe_date}.py"

    source = f"docs/reports/feedback_triage/{date}.md"

    # Render template
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        keep_trailing_newline=True,
    )
    template = env.get_template("replay_test.py.j2")

    rendered = template.render(
        date=date,
        source=source,
        output_path=str(output_path.relative_to(output_path.parents[2]))
        if len(output_path.parents) > 2
        else str(output_path),
        validators=all_validators,
        conversations=all_conversations,
    )

    if dry_run:
        print(f"\n--- DRY RUN OUTPUT ({len(rendered)} chars) ---\n")
        print(rendered[:3000])
        if len(rendered) > 3000:
            print(f"\n... ({len(rendered) - 3000} more chars)")
        print(f"\n--- END ---")
        return rendered

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered, encoding="utf-8")
    print(f"\nTest file saved: {output_path}")
    print(f"  Conversations: {len(all_conversations)}")
    print(f"  Total steps: {sum(c.step_count for c in all_conversations)}")
    print(f"  Validators: {len(all_validators)}")
    print(f"  Size: {len(rendered)} chars")

    # Verify syntax
    try:
        import ast

        ast.parse(rendered)
        print("  Syntax: OK")
    except SyntaxError as e:
        print(f"  Syntax: ERROR — {e}")
        print("  The generated file may need manual fixes.")

    return rendered


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate replay test from feedback data"
    )
    parser.add_argument(
        "--date",
        help="Date to generate tests for (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--feedbacks",
        help="Comma-separated feedback IDs (e.g., FDBK-0109,FDBK-0111)",
    )
    parser.add_argument(
        "--backend-url",
        default=os.environ.get("BACKEND_URL", "http://localhost:8000"),
        help="Backend API URL",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get(
            "INTERNAL_API_KEY", os.environ.get("BACKEND_INTERNAL_KEY", "")
        ),
        help="Internal API key",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output file path",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print output without writing file",
    )

    args = parser.parse_args()

    if not args.date and not args.feedbacks:
        print("ERROR: Either --date or --feedbacks is required")
        return 2

    if not args.api_key:
        print("ERROR: API key required. Set INTERNAL_API_KEY or use --api-key")
        return 2

    feedback_ids = None
    if args.feedbacks:
        feedback_ids = [fid.strip() for fid in args.feedbacks.split(",")]

    date = args.date or datetime.utcnow().strftime("%Y-%m-%d")

    try:
        generate_replay_test(
            date=date,
            backend_url=args.backend_url,
            api_key=args.api_key,
            feedback_ids=feedback_ids,
            output_path=args.output,
            dry_run=args.dry_run,
        )
        return 0
    except requests.HTTPError as e:
        print(f"ERROR: API request failed: {e}")
        return 1
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
