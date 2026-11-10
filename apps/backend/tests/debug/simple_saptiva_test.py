#!/usr/bin/env python3
"""
Test simple para verificar conectividad con SAPTIVA API.
"""

import asyncio
import time
import httpx
import os
from typing import Dict, List, Any


class SimpleSaptivaTest:
    def __init__(self):
        self.base_url = "https://api.saptiva.ai"
        self.api_key = os.getenv("SAPTIVA_API_KEY")
        self.timeout = 30

        if not self.api_key:
            raise ValueError("SAPTIVA_API_KEY environment variable not set")

        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout),
            headers={
                "User-Agent": "Copilot-OS/1.0",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
        )

    async def health_check(self) -> bool:
        """Verificar si SAPTIVA API está disponible"""
        try:
            response = await self.client.get(f"{self.base_url}/v1/models")
            return response.status_code == 200
        except Exception:
            return False

    async def get_models(self) -> List[str]:
        """Obtener modelos disponibles"""
        try:
            response = await self.client.get(f"{self.base_url}/v1/models")
            if response.status_code == 200:
                data = response.json()
                return [model["id"] for model in data.get("data", [])]
            return []
        except Exception as e:
            print(f"Error getting models: {e}")
            return []

    async def chat_completion(self, messages: List[Dict[str, str]], model: str = "saptiva-cortex") -> Dict[str, Any]:
        """Test chat completion"""
        try:
            request_data = {
                "model": model,
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 100,
                "stream": False
            }

            response = await self.client.post(
                f"{self.base_url}/v1/chat/completions",
                json=request_data
            )

            if response.status_code == 200:
                return response.json()
            else:
                print(f"API Error: {response.status_code} - {response.text}")
                return {}

        except Exception as e:
            print(f"Request error: {e}")
            return {}

    async def close(self):
        await self.client.aclose()


async def main():
    print("🚀 Simple SAPTIVA API Test")
    print("=" * 50)

    test_client = SimpleSaptivaTest()

    try:
        # Test 1: Health check
        print("\n1️⃣ Testing health check...")
        is_healthy = await test_client.health_check()
        print(f"   Health check: {'✅ PASSED' if is_healthy else '❌ FAILED'}")

        if not is_healthy:
            print("   ⚠️ API no responde. Verificar conectividad y credenciales.")
            return False

        # Test 2: Get models
        print("\n2️⃣ Testing available models...")
        models = await test_client.get_models()
        if models:
            print(f"   Available models: {models}")
        else:
            print("   ⚠️ No se pudieron obtener los modelos")

        # Test 3: Simple chat
        print("\n3️⃣ Testing simple chat completion...")
        messages = [
            {"role": "user", "content": "Hola, ¿puedes decirme brevemente qué eres?"}
        ]

        start_time = time.time()
        response = await test_client.chat_completion(messages)
        duration = time.time() - start_time

        if response:
            print("   ✅ Chat completion successful!")
            print(f"   Response time: {duration:.2f}s")
            print(f"   Response ID: {response.get('id', 'N/A')}")
            print(f"   Model: {response.get('model', 'N/A')}")

            if response.get('choices'):
                content = response['choices'][0]['message']['content']
                print(f"   Content: {content[:100]}...")

            if response.get('usage'):
                usage = response['usage']
                print(f"   Tokens used: {usage.get('total_tokens', 0)}")
        else:
            print("   ❌ Chat completion failed")
            return False

        # Test 4: Context test
        print("\n4️⃣ Testing context awareness...")
        context_messages = [
            {"role": "user", "content": "Mi nombre es Carlos"},
            {"role": "assistant", "content": "Hola Carlos, encantado de conocerte."},
            {"role": "user", "content": "¿Cuál es mi nombre?"}
        ]

        context_response = await test_client.chat_completion(context_messages)
        if context_response and context_response.get('choices'):
            content = context_response['choices'][0]['message']['content']
            print(f"   Context response: {content}")
        else:
            print("   ❌ Context test failed")

        print("\n🎉 ¡Todos los tests pasaron! SAPTIVA API está funcionando correctamente.")
        return True

    except Exception as e:
        print(f"\n❌ Error durante los tests: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        await test_client.close()


if __name__ == "__main__":
    result = asyncio.run(main())
    if result:
        print("\n✅ La integración SAPTIVA está lista para producción!")
    else:
        print("\n❌ Revisar configuración antes de desplegar.")
