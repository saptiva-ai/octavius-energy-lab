#!/usr/bin/env bash
# Test Saptiva API connection and model integration
# Usage: ./scripts/test-saptiva-connection.sh [username] [password]

set -euo pipefail
IFS=$'\n\t'

API_URL="${API_URL:-http://localhost:8001}"
USERNAME="${1:-testuser}"
PASSWORD="${2:-TestPass123!}"

echo "═══════════════════════════════════════════════════════════"
echo "  ▸ Saptiva API Connection Test"
echo "═══════════════════════════════════════════════════════════"
echo ""

# Test 1: Check API health
echo "▸ Testing API health..."
if curl -sf "${API_URL}/api/health" > /dev/null; then
    echo "✔ API is healthy"
    echo ""
else
    echo "✖ API health check failed"
    exit 1
fi

# Test 2: Check models endpoint (public)
echo "▸ Testing models endpoint..."
MODELS=$(curl -sf "${API_URL}/api/models")
if echo "$MODELS" | grep -q "Saptiva"; then
    echo "✔ Models endpoint working"
    echo "$MODELS" | python3 -m json.tool 2>/dev/null || echo "$MODELS"
    echo ""
else
    echo "✖ Models endpoint failed"
    exit 1
fi

# Test 3: Authenticate
echo "⛨ Authenticating..."
AUTH_RESPONSE=$(curl -sf -X POST "${API_URL}/api/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"identifier\":\"${USERNAME}\",\"password\":\"${PASSWORD}\"}" 2>/dev/null)

if [ $? -ne 0 ] || [ -z "$AUTH_RESPONSE" ]; then
    echo "▲  Login failed, trying registration..."
    AUTH_RESPONSE=$(curl -sf -X POST "${API_URL}/api/auth/register" \
        -H "Content-Type: application/json" \
        -d "{\"username\":\"${USERNAME}\",\"email\":\"${USERNAME}@example.com\",\"password\":\"${PASSWORD}\",\"name\":\"Test User\"}" 2>/dev/null)

    if [ $? -ne 0 ]; then
        echo "✖ Authentication failed"
        exit 1
    fi
fi

TOKEN=$(echo "$AUTH_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))" 2>/dev/null)

if [ -z "$TOKEN" ]; then
    echo "✖ Failed to get access token"
    exit 1
fi

echo "✔ Authenticated successfully"
echo ""

# Test 4: Check SAPTIVA_API_KEY in container
echo "⛨ Checking SAPTIVA_API_KEY in container..."
if command -v docker &> /dev/null; then
    API_KEY=$(docker exec octavios-api printenv SAPTIVA_API_KEY 2>/dev/null || echo "")
    if [ -n "$API_KEY" ] && [ "$API_KEY" != "blank" ]; then
        echo "✔ SAPTIVA_API_KEY is configured (length: ${#API_KEY})"
        echo ""
    else
        echo "✖ SAPTIVA_API_KEY is not configured"
        exit 1
    fi
else
    echo "▲  Docker not available, skipping key check"
    echo ""
fi

# Test 5: Send chat message to Saptiva
echo "▸ Testing chat with Saptiva Turbo..."
echo "──────────────────────────────────────────────────────────"

CHAT_RESPONSE=$(curl -sf -X POST "${API_URL}/api/chat" \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json" \
    -d '{"message":"Di: Funciona correctamente","model":"Saptiva Turbo","stream":false}' 2>/dev/null)

if [ $? -eq 0 ] && echo "$CHAT_RESPONSE" | grep -q "content"; then
    echo ""
    echo "✔ Chat successful!"
    echo ""

    CONTENT=$(echo "$CHAT_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('content', 'N/A')[:200])" 2>/dev/null)
    MODEL=$(echo "$CHAT_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('model', 'N/A'))" 2>/dev/null)

    echo "▸ Response: \"$CONTENT\""
    echo "▸ Model: $MODEL"
    echo ""

    echo "══════════════════════════════════════════════════════════"
    echo "✔ ALL TESTS PASSED - Saptiva integration working!"
    echo "══════════════════════════════════════════════════════════"
    exit 0
else
    echo ""
    echo "✖ Chat failed"
    echo "Response: $CHAT_RESPONSE"

    # Check logs for errors
    if command -v docker &> /dev/null; then
        echo ""
        echo "▸ Recent API logs:"
        docker logs octavios-api --tail 20 | grep -i "saptiva\|error" || echo "No relevant logs found"
    fi

    exit 1
fi