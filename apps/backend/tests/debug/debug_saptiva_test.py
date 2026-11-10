#!/usr/bin/env python3
"""
Debug test para verificar conectividad con SAPTIVA API.
"""

import asyncio
import httpx
import os
import sys


async def debug_saptiva():
    print("🔍 Debug SAPTIVA API Connection")
    print("=" * 50)

    base_url = "https://api.saptiva.ai"
    api_key = os.getenv("SAPTIVA_API_KEY")
    if not api_key:
        print("❌ SAPTIVA_API_KEY environment variable not set")
        print("   Please set your API key: export SAPTIVA_API_KEY=your-api-key-here")
        sys.exit(1)

    headers = {
        "User-Agent": "Copilot-OS/1.0",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    async with httpx.AsyncClient(timeout=30) as client:
        # Test 1: Basic connectivity
        print("\n1️⃣ Testing basic connectivity...")
        try:
            response = await client.get(base_url)
            print(f"   Base URL status: {response.status_code}")
            print(f"   Response headers: {dict(response.headers)}")
        except Exception as e:
            print(f"   ❌ Base URL error: {e}")

        # Test 2: Models endpoint
        print("\n2️⃣ Testing /v1/models endpoint...")
        try:
            response = await client.get(f"{base_url}/v1/models", headers=headers)
            print(f"   Models endpoint status: {response.status_code}")
            print(f"   Response headers: {dict(response.headers)}")
            if response.status_code != 200:
                print(f"   Response text: {response.text}")
            else:
                data = response.json()
                print(f"   Models found: {len(data.get('data', []))}")
        except Exception as e:
            print(f"   ❌ Models endpoint error: {e}")

        # Test 3: Chat completions endpoint
        print("\n3️⃣ Testing /v1/chat/completions endpoint...")
        try:
            request_data = {
                "model": "saptiva-cortex",
                "messages": [{"role": "user", "content": "Hello"}],
                "temperature": 0.7,
                "max_tokens": 10
            }

            response = await client.post(
                f"{base_url}/v1/chat/completions",
                json=request_data,
                headers=headers
            )
            print(f"   Chat endpoint status: {response.status_code}")
            print(f"   Response headers: {dict(response.headers)}")
            if response.status_code != 200:
                print(f"   Response text: {response.text}")
            else:
                data = response.json()
                print(f"   Chat response ID: {data.get('id', 'N/A')}")
                if data.get('choices'):
                    content = data['choices'][0]['message']['content']
                    print(f"   Response content: {content}")
        except Exception as e:
            print(f"   ❌ Chat endpoint error: {e}")

        # Test 4: Alternative endpoints
        print("\n4️⃣ Testing alternative common endpoints...")
        alternative_endpoints = [
            "/health",
            "/v1/health",
            "/status",
            "/api/v1/models",
            "/api/models"
        ]

        for endpoint in alternative_endpoints:
            try:
                response = await client.get(f"{base_url}{endpoint}", headers=headers)
                if response.status_code == 200:
                    print(f"   ✅ {endpoint}: {response.status_code}")
                else:
                    print(f"   ❌ {endpoint}: {response.status_code}")
            except Exception as e:
                print(f"   ❌ {endpoint}: {e}")


if __name__ == "__main__":
    asyncio.run(debug_saptiva())
