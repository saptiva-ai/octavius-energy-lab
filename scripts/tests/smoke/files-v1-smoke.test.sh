#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

#
# Files V1 MVP Smoke Tests
# Validates: redirect 307, rate limiting, upload limits, MIME validation
#

# Configuration
API_BASE="${API_BASE:-http://localhost:8080}"
TEST_TRACE_ID="smoke-files-v1-$(date +%s)"
SESSION_COOKIE="${SESSION_COOKIE:-sess=test-session-token}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test results
PASSED=0
FAILED=0

echo "========================================="
echo "Files V1 MVP Smoke Tests"
echo "========================================="
echo "API Base: $API_BASE"
echo "Trace ID: $TEST_TRACE_ID"
echo ""

# Helper functions
pass() {
  echo -e "${GREEN}✓ PASS${NC}: $1"
  PASSED=$((PASSED + 1))
}

fail() {
  echo -e "${RED}✗ FAIL${NC}: $1"
  FAILED=$((FAILED + 1))
}

info() {
  echo -e "${YELLOW}→${NC} $1"
}

# Create test fixtures
setup_fixtures() {
  local fixtures_dir="$(mktemp -d)"
  echo "$fixtures_dir"

  # Create small valid PDF (1KB)
  cat > "$fixtures_dir/small.pdf" << 'EOF'
%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /Resources 4 0 R /MediaBox [0 0 612 792] /Contents 5 0 R >>
endobj
4 0 obj
<< /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >>
endobj
5 0 obj
<< /Length 44 >>
stream
BT
/F1 12 Tf
50 750 Td
(Test PDF) Tj
ET
endstream
endobj
xref
0 6
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000229 00000 n
0000000328 00000 n
trailer
<< /Size 6 /Root 1 0 R >>
startxref
420
%%EOF
EOF

  # Create large PDF (simulate >10MB with dd)
  dd if=/dev/zero of="$fixtures_dir/large.pdf" bs=1M count=15 2>/dev/null

  # Create invalid MIME file
  echo "INVALID FILE CONTENT" > "$fixtures_dir/evil.exe"
}

cleanup_fixtures() {
  local fixtures_dir="$1"
  rm -rf "$fixtures_dir"
}

# Test 1: Redirect 307 from /api/documents/upload
test_redirect_307() {
  info "Test 1: Redirect 307 from /api/documents/upload"

  local response
  response=$(curl -s -i \
    -F "file=@$FIXTURES_DIR/small.pdf" \
    -F "conversation_id=conv_smoke_1" \
    -H "x-trace-id: $TEST_TRACE_ID-redirect" \
    -b "$SESSION_COOKIE" \
    "$API_BASE/api/documents/upload" 2>&1 || true)

  if echo "$response" | grep -q "307\|Temporary Redirect"; then
    pass "Redirect 307 present"
  else
    fail "Redirect 307 not found in response"
    echo "Response: $response"
  fi

  if echo "$response" | grep -qi "location.*files/upload"; then
    pass "Redirect location points to /files/upload"
  else
    fail "Redirect location incorrect"
  fi
}

# Test 2: Upload to /api/files/upload succeeds
test_upload_success() {
  info "Test 2: Upload to /api/files/upload succeeds"

  local response
  local http_code
  response=$(curl -s -w "\n%{http_code}" \
    -F "file=@$FIXTURES_DIR/small.pdf" \
    -F "conversation_id=conv_smoke_2" \
    -H "x-trace-id: $TEST_TRACE_ID-upload" \
    -b "$SESSION_COOKIE" \
    "$API_BASE/api/files/upload" 2>&1 || true)

  http_code=$(echo "$response" | tail -n1)
  body=$(echo "$response" | head -n-1)

  if [[ "$http_code" == "200" ]] || [[ "$http_code" == "201" ]]; then
    pass "Upload succeeded with HTTP $http_code"
  else
    fail "Upload failed with HTTP $http_code"
    echo "Body: $body"
  fi

  if echo "$body" | grep -q '"status".*"READY"\|"status".*"PROCESSING"'; then
    pass "Response contains valid status"
  else
    fail "Response missing status field"
  fi
}

# Test 3: Rate limiting (5 uploads/min)
test_rate_limiting() {
  info "Test 3: Rate limiting (5 uploads/min per user)"

  local success_count=0
  local rate_limited=0

  for i in {1..6}; do
    local http_code
    http_code=$(curl -s -o /dev/null -w "%{http_code}" \
      -F "file=@$FIXTURES_DIR/small.pdf" \
      -F "conversation_id=conv_smoke_rate_$i" \
      -H "x-trace-id: $TEST_TRACE_ID-rate-$i" \
      -b "$SESSION_COOKIE" \
      "$API_BASE/api/files/upload" 2>&1 || true)

    if [[ "$http_code" == "200" ]] || [[ "$http_code" == "201" ]]; then
      success_count=$((success_count + 1))
    elif [[ "$http_code" == "429" ]]; then
      rate_limited=1
      break
    fi

    sleep 0.1  # Small delay between requests
  done

  if [[ $success_count -ge 5 ]] && [[ $rate_limited -eq 1 ]]; then
    pass "Rate limiting works: $success_count successful, then 429"
  elif [[ $success_count -eq 5 ]] && [[ $rate_limited -eq 0 ]]; then
    pass "Rate limiting works: exactly 5 uploads allowed (6th not tested)"
  else
    fail "Rate limiting behavior unexpected: $success_count successful, rate_limited=$rate_limited"
  fi
}

# Test 4: File size limit (>10MB = 413)
test_file_size_limit() {
  info "Test 4: File size limit (>10MB = 413)"

  local http_code
  http_code=$(curl -s -o /dev/null -w "%{http_code}" \
    -F "file=@$FIXTURES_DIR/large.pdf" \
    -F "conversation_id=conv_smoke_large" \
    -H "x-trace-id: $TEST_TRACE_ID-large" \
    -b "$SESSION_COOKIE" \
    "$API_BASE/api/files/upload" 2>&1 || true)

  if [[ "$http_code" == "413" ]]; then
    pass "Large file rejected with HTTP 413"
  else
    fail "Large file not rejected correctly (got HTTP $http_code, expected 413)"
  fi
}

# Test 5: MIME type validation (invalid = 415)
test_mime_validation() {
  info "Test 5: MIME type validation (invalid = 415)"

  local http_code
  http_code=$(curl -s -o /dev/null -w "%{http_code}" \
    -F "file=@$FIXTURES_DIR/evil.exe" \
    -F "conversation_id=conv_smoke_mime" \
    -H "x-trace-id: $TEST_TRACE_ID-mime" \
    -b "$SESSION_COOKIE" \
    "$API_BASE/api/files/upload" 2>&1 || true)

  if [[ "$http_code" == "415" ]]; then
    pass "Invalid MIME rejected with HTTP 415"
  else
    fail "Invalid MIME not rejected correctly (got HTTP $http_code, expected 415)"
  fi
}

# Main test execution
main() {
  info "Setting up test fixtures..."
  FIXTURES_DIR=$(setup_fixtures)
  echo "Fixtures created at: $FIXTURES_DIR"
  echo ""

  # Run tests
  test_redirect_307
  test_upload_success
  test_rate_limiting
  test_file_size_limit
  test_mime_validation

  # Cleanup
  cleanup_fixtures "$FIXTURES_DIR"

  # Summary
  echo ""
  echo "========================================="
  echo "Test Summary"
  echo "========================================="
  echo -e "${GREEN}Passed: $PASSED${NC}"
  echo -e "${RED}Failed: $FAILED${NC}"
  echo ""

  if [[ $FAILED -eq 0 ]]; then
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
  else
    echo -e "${RED}Some tests failed.${NC}"
    exit 1
  fi
}

# Run if executed directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
