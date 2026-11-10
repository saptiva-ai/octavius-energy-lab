#!/usr/bin/env python3
"""
Test para encontrar el endpoint correcto de SAPTIVA API.
"""

import asyncio
import httpx
import os
import sys


async def test_saptiva_domains():
    print("🔍 Testing SAPTIVA Domain Patterns")
    print("=" * 50)

    api_key = os.getenv("SAPTIVA_API_KEY")
    if not api_key:
        print("❌ SAPTIVA_API_KEY environment variable not set")
        print("   Please set your API key: export SAPTIVA_API_KEY=your-api-key-here")
        sys.exit(1)

    # Possible domains
    domains = [
        "https://saptiva.ai",
        "https://api.saptiva.ai",
        "https://chat.saptiva.ai",
        "https://app.saptiva.ai",
        "https://www.saptiva.ai",
        "http://saptiva.ai",
        "https://saptiva.ai/api",
        "https://saptiva.ai/v1"
    ]

    headers = {
        "User-Agent": "Copilot-OS/1.0",
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(timeout=10) as client:
        for domain in domains:
            print(f"\n🌐 Testing: {domain}")

            # Test basic connectivity
            try:
                response = await client.get(domain, headers=headers)
                print(f"   ✅ Base: {response.status_code}")
                if response.status_code == 200:
                    print(f"   Response: {response.text[:100]}...")
            except Exception as e:
                print(f"   ❌ Base: {e}")

            # Test /v1/models
            try:
                response = await client.get(f"{domain}/v1/models", headers=headers)
                if response.status_code == 200:
                    print(f"   ✅ /v1/models: {response.status_code}")
                    data = response.json()
                    print(f"   Models: {[m.get('id', 'unknown') for m in data.get('data', [])][:3]}")
                else:
                    print(f"   ❌ /v1/models: {response.status_code}")
            except Exception as e:
                print(f"   ❌ /v1/models: {e}")

            # Test /models
            try:
                response = await client.get(f"{domain}/models", headers=headers)
                if response.status_code == 200:
                    print(f"   ✅ /models: {response.status_code}")
                else:
                    print(f"   ❌ /models: {response.status_code}")
            except Exception as e:
                print(f"   ❌ /models: {e}")

    print("\n" + "=" * 50)
    print("💡 Si algún endpoint funcionó, actualizar la configuración SAPTIVA_BASE_URL")


if __name__ == "__main__":
    asyncio.run(test_saptiva_domains())
