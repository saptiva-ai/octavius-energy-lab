from __future__ import annotations

import os
import time

import httpx

from .helpers import DEFAULT_BACKEND_URL, fixture_path, get_auth_token, json_or_raise


def main() -> int:
    print(
        "🧪 Test IPC-1: Full audit flow (Frontend → Backend → Demo → FileManager)"
    )

    token = get_auth_token(token=os.environ.get("TOKEN"))
    session_id = f"full_flow_test_{int(time.time())}"

    pdf_path = fixture_path("audit_compliant.pdf")
    with pdf_path.open("rb") as handle:
        upload_response = httpx.post(
            f"{DEFAULT_BACKEND_URL}/api/files/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"files": (pdf_path.name, handle, "application/pdf")},
            data={"session_id": session_id},
            timeout=60,
        )

    payload = json_or_raise(upload_response)
    file_id = (payload.get("files") or [{}])[0].get("file_id")

    if not file_id:
        print("❌ FAIL: Upload failed")
        print(payload)
        return 1

    chat_response = httpx.post(
        f"{DEFAULT_BACKEND_URL}/api/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "message": "Auditar archivo: audit_compliant.pdf",
            "session_id": session_id,
            "file_ids": [file_id],
        },
        timeout=120,
    )

    chat_payload = json_or_raise(chat_response)
    tool_invocations = chat_payload.get("metadata", {}).get("tool_invocations", [])
    artifact_id = None
    if tool_invocations:
        artifact_id = tool_invocations[0].get("result", {}).get("id")

    if not artifact_id:
        print("⚠️  Warning: Artifact ID not found in standard path. checking content...")
        print(chat_payload)
        print("❌ FAIL: Artifact ID not found in response")
        return 1

    artifact_response = httpx.get(
        f"{DEFAULT_BACKEND_URL}/api/artifacts/{artifact_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
    )

    artifact_payload = json_or_raise(artifact_response)
    content = artifact_payload.get("content", "")

    if (
        "Auditoría" in content
        or "Reporte" in content
        or content.strip().startswith("# ")
    ):
        print("✅ PASS: Full audit flow works end-to-end (Artifact content verified)")
        return 0

    print("❌ FAIL: Audit flow incomplete. Content mismatch.")
    print(f"Content start: {content[:100]}...")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
