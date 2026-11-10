from __future__ import annotations

import os

import httpx

from .helpers import DEFAULT_BACKEND_URL, fixture_path, get_auth_token, json_or_raise


def main() -> int:
    print("🧪 Test 1.3: Backend delegates text extraction to File Manager")

    token = get_auth_token(token=os.environ.get("TOKEN"))
    pdf_path = fixture_path("sample.pdf")

    with pdf_path.open("rb") as handle:
        upload_response = httpx.post(
            f"{DEFAULT_BACKEND_URL}/api/files/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"files": (pdf_path.name, handle, "application/pdf")},
            data={"session_id": "extract_test"},
            timeout=60,
        )

    payload = json_or_raise(upload_response)
    file_id = (payload.get("files") or [{}])[0].get("file_id")

    if not file_id:
        print("❌ FAIL: Upload failed, no file_id")
        print(payload)
        return 1

    extract_response = httpx.post(
        f"{DEFAULT_BACKEND_URL}/api/files/{file_id}/extract",
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
    )

    extract_payload = json_or_raise(extract_response)
    extracted_text = extract_payload.get("extracted_text")

    if extracted_text:
        print("✅ PASS: Text extraction works via delegation")
        return 0

    print("❌ FAIL: No text extracted")
    print(extract_payload)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
