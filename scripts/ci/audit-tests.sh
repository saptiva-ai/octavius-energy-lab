#!/usr/bin/env bash

set -euo pipefail
IFS=$'\n\t'

echo "[audit] scanning shell tests for deprecated usage..."

if command -v rg >/dev/null 2>&1; then
  DEPRECATED_TAGS=$(rg -n "@deprecated" scripts/tests || true)
  OLD_ENDPOINTS=$(rg -n "/api/(documents|review)/" scripts/tests || true)
else
  DEPRECATED_TAGS=$(grep -RIn "@deprecated" scripts/tests 2>/dev/null || true)
  OLD_ENDPOINTS=$(grep -RInE "/api/(documents|review)/" scripts/tests 2>/dev/null || true)
fi

echo "== @deprecated markers =="
if [[ -z "$DEPRECATED_TAGS" ]]; then
  echo "<none>"
else
  echo "$DEPRECATED_TAGS"
fi

echo
echo "== legacy endpoint references =="
if [[ -z "$OLD_ENDPOINTS" ]]; then
  echo "<none>"
else
  echo "$OLD_ENDPOINTS"
fi

mkdir -p scripts/tests/deprecated
echo
echo "[audit] move outdated scripts to scripts/tests/deprecated/ and schedule removal as needed."
