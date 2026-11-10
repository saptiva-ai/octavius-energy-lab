#!/usr/bin/env python3
"""
Triage Report Generator — Deterministic feedback analysis.

Replaces the manual SSH+mongo+copy-paste workflow with API-driven report
generation. 6 of 7 sections are 100% deterministic; only sections 1 and 5
require LLM analysis (marked with <!-- LLM_REQUIRED -->).

Usage:
    python scripts/triage/generate_report.py --date 2026-02-10
    python scripts/triage/generate_report.py --date 2026-02-10 --dry-run
    python scripts/triage/generate_report.py --date 2026-02-10 --backend-url http://localhost:18000
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

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
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[2] / "docs" / "reports" / "feedback_triage"


class TriageAPIClient:
    """Client for the internal feedback API endpoints."""

    def __init__(self, backend_url: str, api_key: str) -> None:
        self.backend_url = backend_url.rstrip("/")
        self.headers = {
            "Content-Type": "application/json",
            "X-Internal-Key": api_key,
        }

    def get_stats(self) -> Dict[str, Any]:
        """GET /api/internal/feedback/stats"""
        resp = requests.get(
            f"{self.backend_url}/api/internal/feedback/stats",
            headers=self.headers,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def query_feedback(
        self,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        rating: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        """POST /api/internal/feedback/query"""
        payload: Dict[str, Any] = {"limit": limit}
        if date_from:
            payload["date_from"] = date_from
        if date_to:
            payload["date_to"] = date_to
        if rating:
            payload["rating"] = rating

        resp = requests.post(
            f"{self.backend_url}/api/internal/feedback/query",
            json=payload,
            headers=self.headers,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def get_conversations(
        self,
        conversation_ids: List[str],
        include_artifacts: bool = True,
    ) -> Dict[str, Any]:
        """POST /api/internal/feedback/conversations"""
        if not conversation_ids:
            return {}

        resp = requests.post(
            f"{self.backend_url}/api/internal/feedback/conversations",
            json={
                "conversation_ids": conversation_ids,
                "include_artifacts": include_artifacts,
            },
            headers=self.headers,
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()

    def get_stale_charts(
        self,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """GET /api/internal/feedback/stale-charts"""
        params: Dict[str, str] = {}
        if date_from:
            params["date_from"] = date_from
        if date_to:
            params["date_to"] = date_to

        resp = requests.get(
            f"{self.backend_url}/api/internal/feedback/stale-charts",
            params=params,
            headers=self.headers,
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()


def generate_report(
    date: str,
    backend_url: str,
    api_key: str,
    output_path: Optional[Path] = None,
    dry_run: bool = False,
) -> str:
    """Generate a complete triage report for the given date."""
    client = TriageAPIClient(backend_url, api_key)

    # Date window: target day 06:00 UTC → next day 06:00 UTC (Mexico City midnight)
    date_from_utc = f"{date}T06:00:00"
    next_day = (datetime.fromisoformat(date) + timedelta(days=1)).strftime("%Y-%m-%d")
    date_to_utc = f"{next_day}T06:00:00"

    # 7-day window for trend
    seven_days_ago = (datetime.fromisoformat(date) - timedelta(days=7)).strftime("%Y-%m-%d")
    date_from_7d = f"{seven_days_ago}T06:00:00"

    print(f"[1/5] Fetching stats...")
    stats = client.get_stats()

    print(f"[2/5] Querying today's feedback ({date_from_utc} → {date_to_utc})...")
    all_today = client.query_feedback(
        date_from=date_from_utc, date_to=date_to_utc, limit=500
    )
    thumbs_down = [fb for fb in all_today if fb.get("rating") == "down"]
    thumbs_up = [fb for fb in all_today if fb.get("rating") == "up"]

    # 7-day thumbs down count
    thumbs_down_7d_list = client.query_feedback(
        date_from=date_from_7d, date_to=date_to_utc, rating="down", limit=500
    )

    # Unique conversations with feedback today
    conv_ids_today = list(set(fb.get("conversation_id", "") for fb in all_today if fb.get("conversation_id")))

    print(f"[3/5] Detecting stale charts...")
    stale_charts = client.get_stale_charts(
        date_from=date_from_utc, date_to=date_to_utc
    )

    print(f"[4/5] Fetching conversation threads ({len(conv_ids_today)} conversations)...")
    conversations = {}
    if conv_ids_today:
        # API limits 20 per request, batch if needed
        for i in range(0, len(conv_ids_today), 20):
            batch = conv_ids_today[i : i + 20]
            batch_result = client.get_conversations(batch)
            conversations.update(batch_result)

    print(f"[5/5] Rendering report...")

    # Render template
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        keep_trailing_newline=True,
    )
    template = env.get_template("triage_report.md.j2")

    rendered = template.render(
        date=date,
        date_from_utc=date_from_utc,
        date_to_utc=date_to_utc,
        agent="scripts/triage/generate_report.py",
        stats=stats,
        feedback_today_count=len(all_today),
        thumbs_down_count=len(thumbs_down),
        thumbs_up_count=len(thumbs_up),
        conversations_today_count=len(conv_ids_today),
        thumbs_down_7d=len(thumbs_down_7d_list),
        stale_charts=stale_charts,
        thumbs_down=thumbs_down,
        conversations=conversations,
        conversation_ids=conv_ids_today,
    )

    if dry_run:
        print("\n--- DRY RUN OUTPUT ---\n")
        print(rendered)
        print(f"\n--- END ({len(rendered)} chars) ---")
        return rendered

    # Write output
    if output_path is None:
        output_path = DEFAULT_OUTPUT_DIR / f"{date}.md"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered, encoding="utf-8")
    print(f"\nReport saved: {output_path}")
    print(f"  Size: {len(rendered)} chars")
    print(f"  Thumbs-down: {len(thumbs_down)}")
    print(f"  Stale charts: {len(stale_charts)}")
    print(f"  Conversations: {len(conversations)}")

    return rendered


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate triage report from feedback API data"
    )
    parser.add_argument(
        "--date",
        required=True,
        help="Report date in YYYY-MM-DD format",
    )
    parser.add_argument(
        "--backend-url",
        default=os.environ.get("BACKEND_URL", "http://localhost:8000"),
        help="Backend API URL (default: $BACKEND_URL or localhost:8000)",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("INTERNAL_API_KEY", os.environ.get("BACKEND_INTERNAL_KEY", "")),
        help="Internal API key (default: $INTERNAL_API_KEY or $BACKEND_INTERNAL_KEY)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output file path (default: docs/reports/feedback_triage/{date}.md)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print report to stdout without writing file",
    )

    args = parser.parse_args()

    if not args.api_key:
        print("ERROR: API key required. Set INTERNAL_API_KEY or use --api-key")
        return 2

    try:
        generate_report(
            date=args.date,
            backend_url=args.backend_url,
            api_key=args.api_key,
            output_path=args.output,
            dry_run=args.dry_run,
        )
        return 0
    except requests.HTTPError as e:
        print(f"ERROR: API request failed: {e}")
        if hasattr(e, "response") and e.response is not None:
            print(f"  Status: {e.response.status_code}")
            print(f"  Body: {e.response.text[:500]}")
        return 1
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
