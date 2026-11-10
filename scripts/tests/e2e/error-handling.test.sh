#!/usr/bin/env bash
#
# Test Error Handling Implementation (P1-HIST-009)
# Manual testing guide with automated verification
#

set -euo pipefail
IFS=$'\n\t'

# Status symbols
RED="✖ "
GREEN="✔ "
YELLOW="▲ "
BLUE="▸ "
NC=""

API_URL="http://localhost:8001"
WEB_URL="http://localhost:3000"
TEST_USER="demo"
TEST_PASS="Demo1234"

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}P1-HIST-009 Error Handling - Test Suite${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# ============================================================================
# Pre-flight checks
# ============================================================================

echo -e "${YELLOW}Pre-flight Checks${NC}"
echo ""

# Check API health
echo -n "  Checking API health... "
if curl -sf ${API_URL}/api/health > /dev/null 2>&1; then
  echo -e "${GREEN}Healthy${NC}"
else
  echo -e "${RED}API not responding${NC}"
  echo -e "${RED}Run 'make dev' first${NC}"
  exit 1
fi

# Check Frontend health
echo -n "  Checking Frontend... "
if curl -sf ${WEB_URL} > /dev/null 2>&1; then
  echo -e "${GREEN}Healthy${NC}"
else
  echo -e "${RED}Frontend not responding${NC}"
  echo -e "${YELLOW}Frontend may still be starting (takes ~30s)${NC}"
  exit 1
fi

# Get auth token
echo -n "  Getting auth token... "
TOKEN=$(curl -s -X POST ${API_URL}/api/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"identifier\":\"${TEST_USER}\",\"password\":\"${TEST_PASS}\"}" 2>/dev/null | \
  grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)

if [ -n "$TOKEN" ]; then
  echo -e "${GREEN}Authenticated${NC}"
else
  echo -e "${RED}Failed to authenticate${NC}"
  echo -e "${YELLOW}Run 'make create-demo-user' first${NC}"
  exit 1
fi

echo ""

# ============================================================================
# Test 1: Success Path (Toasts)
# ============================================================================

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}Test 1: Success Path - Toasts${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

echo -e "${YELLOW}◆ Manual Test Required:${NC}"
echo ""
echo "  1. Open: ${GREEN}${WEB_URL}${NC}"
echo "  2. Login with: ${GREEN}${TEST_USER} / ${TEST_PASS}${NC}"
echo "  3. Create a new conversation"
echo "  4. Rename conversation → ${GREEN}Look for toast: 'Conversación renombrada' (green, 3s)${NC}"
echo "  5. Pin conversation → ${GREEN}Look for toast: 'Conversación fijada' (green, 2s)${NC}"
echo "  6. Delete conversation → ${GREEN}Look for toast: 'Conversación eliminada' (green, 3s)${NC}"
echo ""
echo -e "${YELLOW}Expected:${NC}"
echo "  ✓ Toasts appear in bottom-right corner"
echo "  ✓ Mint color (#49F7D9) for success"
echo "  ✓ Auto-dismiss after specified duration"
echo ""
read -p "Press ENTER when done testing success path..."
echo ""

# ============================================================================
# Test 2: Retry Logic
# ============================================================================

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}Test 2: Retry Logic with Exponential Backoff${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

echo -e "${YELLOW}This test requires stopping/starting the API${NC}"
echo ""
read -p "Press ENTER to start retry test (will stop API)..."

# Stop API
echo ""
echo -n "  Stopping API... "
docker stop octavios-api > /dev/null 2>&1
echo -e "${GREEN}Stopped${NC}"

echo ""
echo -e "${YELLOW}◆ Manual Test Required:${NC}"
echo ""
echo "  1. Go to ${GREEN}${WEB_URL}${NC}"
echo "  2. Try to rename a conversation"
echo "  3. ${GREEN}Observe retry toasts:${NC}"
echo "     - 'Reintentando renombrar... (1/3)' → wait ~1s"
echo "     - 'Reintentando renombrar... (2/3)' → wait ~2s"
echo "     - 'Reintentando renombrar... (3/3)' → wait ~4s"
echo "     - 'Error al renombrar la conversación' (red, 5s)"
echo "  4. ${GREEN}Verify rollback:${NC} Title should revert to original"
echo ""
echo -e "${YELLOW}Expected:${NC}"
echo "  ✓ 3 retry attempts with exponential delays (1s, 2s, 4s)"
echo "  ✓ Loading toast visible during each retry"
echo "  ✓ Final error toast after all retries fail"
echo "  ✓ UI rollback (title returns to original)"
echo ""
read -p "Press ENTER when done observing retry behavior..."

# Restart API
echo ""
echo -n "  Restarting API... "
docker start octavios-api > /dev/null 2>&1
sleep 5  # Wait for API to be ready
echo -e "${GREEN}Started${NC}"

echo ""
echo -e "${YELLOW}◆ Verify Recovery:${NC}"
echo ""
echo "  1. Try renaming again → ${GREEN}Should succeed now${NC}"
echo "  2. Toast should show: 'Conversación renombrada'"
echo ""
read -p "Press ENTER when verified recovery..."
echo ""

# ============================================================================
# Test 3: Optimistic Updates + Rollback
# ============================================================================

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}Test 3: Optimistic Updates + Rollback${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

read -p "Press ENTER to start optimistic update test (will stop API)..."

# Stop API
echo ""
echo -n "  Stopping API... "
docker stop octavios-api > /dev/null 2>&1
echo -e "${GREEN}Stopped${NC}"

echo ""
echo -e "${YELLOW}◆ Manual Test Required:${NC}"
echo ""
echo "  1. Go to ${GREEN}${WEB_URL}${NC}"
echo "  2. Rename a conversation to 'Test Optimistic Update'"
echo "  3. ${GREEN}Observe:${NC}"
echo "     - UI updates IMMEDIATELY (optimistic)"
echo "     - Retry toasts appear in background"
echo "     - After 3 retries → ${GREEN}Title reverts to original (rollback)${NC}"
echo "  4. No inconsistent states should occur"
echo ""
echo -e "${YELLOW}Expected:${NC}"
echo "  ✓ Instant UI response (doesn't wait for API)"
echo "  ✓ Retry attempts in background (non-blocking)"
echo "  ✓ Automatic rollback if all retries fail"
echo "  ✓ No half-broken state (either success or rollback)"
echo ""
read -p "Press ENTER when done testing optimistic updates..."

# Restart API
echo ""
echo -n "  Restarting API... "
docker start octavios-api > /dev/null 2>&1
sleep 5
echo -e "${GREEN}Started${NC}"
echo ""

# ============================================================================
# Test 4: Error Boundary (Dev Mode)
# ============================================================================

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}Test 4: Error Boundary (Optional - Dev Mode)${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

echo -e "${YELLOW}This test requires code injection (dev mode only)${NC}"
echo ""
echo -e "${YELLOW}Steps:${NC}"
echo "  1. Edit: ${GREEN}apps/web/src/components/chat/ConversationList.tsx${NC}"
echo "  2. Add this at line 210 (inside render):"
echo ""
echo -e "     ${BLUE}if (sessions.length > 0) {${NC}"
echo -e "     ${BLUE}throw new Error('Test error boundary')${NC}"
echo -e "     ${BLUE}}${NC}"
echo ""
echo "  3. Save file (Next.js will hot-reload)"
echo "  4. Go to ${GREEN}${WEB_URL}${NC} with existing conversations"
echo "  5. ${GREEN}Observe:${NC}"
echo "     - Fallback UI appears (▸ icon)"
echo "     - Message: 'Error al cargar conversaciones'"
echo "     - Button: 'Recargar'"
echo "     - App does NOT crash"
echo "     - Rest of app remains functional"
echo "  6. Remove the test code and save"
echo ""
echo -e "${YELLOW}Expected:${NC}"
echo "  ✓ Component error caught by boundary"
echo "  ✓ Fallback UI displayed"
echo "  ✓ App doesn't crash"
echo "  ✓ Error logged to console (dev mode)"
echo ""
read -p "Press ENTER to skip or when done testing error boundary..."
echo ""

# ============================================================================
# Summary
# ============================================================================

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}Test Summary${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

echo -e "${GREEN}Test 1: Success Path - Toasts${NC}"
echo "  - Rename toast: 'Conversación renombrada' (3s)"
echo "  - Pin toast: 'Conversación fijada' (2s)"
echo "  - Delete toast: 'Conversación eliminada' (3s)"
echo ""

echo -e "${GREEN}Test 2: Retry Logic${NC}"
echo "  - 3 retry attempts with exponential backoff"
echo "  - Delays: ~1s, ~2s, ~4s (+ jitter)"
echo "  - Final error toast after all retries"
echo "  - UI rollback on failure"
echo ""

echo -e "${GREEN}Test 3: Optimistic Updates${NC}"
echo "  - Instant UI response"
echo "  - Background retry"
echo "  - Automatic rollback on error"
echo ""

echo -e "${YELLOW}Test 4: Error Boundary (Optional)${NC}"
echo "  - Requires manual code injection"
echo "  - Fallback UI prevents crashes"
echo ""

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}All error handling tests completed!${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

echo "Next steps:"
echo "  • All tests passed → ${GREEN}P1-HIST-009 is production-ready${NC}"
echo "  • Continue to P1-HIST-007 (Virtualization)"
echo "  • Or merge to main: ${BLUE}git checkout main && git merge feature/auth-ui-tools-improvements${NC}"
echo ""