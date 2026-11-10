#!/usr/bin/env bash
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEB_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${WEB_DIR}/../.." && pwd)"
REPORTS_DIR="${E2E_REPORTS_DIR:-${REPO_ROOT}/docs/reports/playwright}"

E2E_BASE_URL_EFFECTIVE="${E2E_BASE_URL:-http://127.0.0.1:3000}"
E2E_SKIP_PDF="${E2E_SKIP_PDF:-0}"
E2E_PREFLIGHT="${E2E_PREFLIGHT:-1}"
E2E_PREFLIGHT_TIMEOUT_MS="${E2E_PREFLIGHT_TIMEOUT_MS:-3000}"
E2E_PDF_STRICT="${E2E_PDF_STRICT:-0}"
E2E_REPORT_TYPE="${E2E_REPORT_TYPE:-}"
E2E_REPORT_MODE="${E2E_REPORT_MODE:-}"
E2E_EXCLUDE_PROJECTS="${E2E_EXCLUDE_PROJECTS:-setup}"

ARGS=("$@")
if [[ "${ARGS[0]:-}" == "--" ]]; then
  ARGS=("${ARGS[@]:1}")
fi

sanitize_slug() {
  local raw="${1:-}"
  local normalized
  normalized="$(printf "%s" "${raw}" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+|-+$//g')"
  if [[ -z "${normalized}" ]]; then
    normalized="suite"
  fi
  printf "%s" "${normalized}"
}

detect_report_type() {
  if [[ -n "${E2E_REPORT_TYPE}" ]]; then
    sanitize_slug "${E2E_REPORT_TYPE}"
    return
  fi

  local spec_candidate=""
  local project_candidate=""
  local expecting_project=0
  local arg
  for arg in "${ARGS[@]}"; do
    if [[ "${expecting_project}" == "1" ]]; then
      project_candidate="project-${arg}"
      expecting_project=0
      continue
    fi

    if [[ "${arg}" == "--project" ]]; then
      expecting_project=1
      continue
    fi

    if [[ "${arg}" == --project=* ]]; then
      project_candidate="project-${arg#--project=}"
      continue
    fi

    if [[ "${arg}" == --* ]]; then
      continue
    fi

    if [[ "${arg}" == *".spec.ts" || "${arg}" == *".spec.js" ]]; then
      local file_name="${arg##*/}"
      file_name="${file_name%.spec.ts}"
      file_name="${file_name%.spec.js}"
      spec_candidate="${file_name}"
    fi
  done

  if [[ -n "${spec_candidate}" ]]; then
    sanitize_slug "${spec_candidate}"
    return
  fi

  if [[ -n "${project_candidate}" ]]; then
    sanitize_slug "${project_candidate}"
    return
  fi

  sanitize_slug "suite"
}

REPORT_TYPE="$(detect_report_type)"
REPORT_TIMESTAMP_UTC="$(date -u +%Y%m%dT%H%M%SZ)"
REPORT_STEM="playwright-e2e__${REPORT_TYPE}__${REPORT_TIMESTAMP_UTC}"

JSON_REPORT_PATH="${E2E_JSON_REPORT_PATH:-test-results/results.json}"
PDF_REPORT_PATH="${E2E_PDF_REPORT_PATH:-${REPORTS_DIR}/${REPORT_STEM}.pdf}"
ARCHIVE_JSON_PATH="${E2E_ARCHIVE_JSON_PATH:-${REPORTS_DIR}/${REPORT_STEM}.json}"

if [[ -z "${E2E_REPORT_MODE}" ]]; then
  if [[ "${E2E_SKIP_PDF}" == "1" ]]; then
    E2E_REPORT_MODE="0"
  else
    E2E_REPORT_MODE="1"
  fi
fi
export E2E_REPORT_MODE

read -r E2E_ORIGIN E2E_HOST E2E_PORT <<<"$(node -e '
  const raw = process.argv[1] || "http://127.0.0.1:3000";
  try {
    const url = new URL(raw);
    const port = url.port || (url.protocol === "https:" ? "443" : "80");
    process.stdout.write(`${url.origin} ${url.hostname} ${port}`);
  } catch {
    process.stdout.write("http://127.0.0.1:3000 127.0.0.1 3000");
  }
' "${E2E_BASE_URL_EFFECTIVE}")"

check_port_open() {
  node -e '
    const net = require("node:net");
    const host = process.argv[1];
    const port = Number(process.argv[2]);
    const timeoutMs = Math.max(500, Number(process.argv[3]) || 3000);

    const socket = net.createConnection({ host, port });
    socket.setTimeout(timeoutMs);
    socket.on("connect", () => {
      socket.destroy();
      process.exit(0);
    });
    socket.on("timeout", () => {
      socket.destroy();
      process.exit(1);
    });
    socket.on("error", () => {
      process.exit(1);
    });
  ' "${E2E_HOST}" "${E2E_PORT}" "${E2E_PREFLIGHT_TIMEOUT_MS}"
}

check_origin_http() {
  node -e '
    const http = require("node:http");
    const https = require("node:https");

    const rawOrigin = process.argv[1];
    const timeoutMs = Math.max(500, Number(process.argv[2]) || 3000);

    let originUrl;
    try {
      originUrl = new URL(rawOrigin);
    } catch {
      process.exit(1);
    }

    const client = originUrl.protocol === "https:" ? https : http;
    const req = client.request(
      originUrl,
      { method: "GET", timeout: timeoutMs },
      (res) => {
        res.resume();
        const code = Number(res.statusCode || 0);
        process.exit(code >= 200 && code < 500 ? 0 : 1);
      },
    );

    req.on("timeout", () => req.destroy(new Error("timeout")));
    req.on("error", () => process.exit(1));
    req.end();
  ' "${E2E_ORIGIN}" "${E2E_PREFLIGHT_TIMEOUT_MS}"
}

preflight_server_port() {
  if [[ "${E2E_PREFLIGHT}" != "1" ]]; then
    echo "[e2e-preflight] Disabled: E2E_PREFLIGHT=${E2E_PREFLIGHT}"
    return 0
  fi

  if ! check_port_open; then
    return 0
  fi

  if check_origin_http; then
    echo "[e2e-preflight] Reusing server at ${E2E_ORIGIN}"
    return 0
  fi

  echo "[e2e-preflight] Port ${E2E_PORT} is occupied, but ${E2E_ORIGIN} is not responding as expected."
  echo "[e2e-preflight] Free the port or set E2E_BASE_URL to a reachable host/port."
  exit 2
}

build_run_command() {
  if [[ "${#ARGS[@]}" -eq 0 ]]; then
    printf "playwright test"
    return
  fi

  local quoted
  quoted="$(printf "%q " "${ARGS[@]}")"
  printf "playwright test %s" "${quoted% }"
}

preflight_server_port
mkdir -p "${REPORTS_DIR}" "$(dirname "${PDF_REPORT_PATH}")" "$(dirname "${ARCHIVE_JSON_PATH}")"

# Ensure stale artifacts do not leak into this run.
rm -f "${JSON_REPORT_PATH}" "${PDF_REPORT_PATH}" "${ARCHIVE_JSON_PATH}"

RUN_COMMAND="$(build_run_command)"
GIT_SHA="$(git -C "${REPO_ROOT}" rev-parse --short HEAD 2>/dev/null || printf "unknown")"

playwright test "${ARGS[@]}"
TEST_EXIT_CODE=$?

JSON_ARCHIVE_EXIT_CODE=0
if [[ -f "${JSON_REPORT_PATH}" ]]; then
  cp "${JSON_REPORT_PATH}" "${ARCHIVE_JSON_PATH}" || JSON_ARCHIVE_EXIT_CODE=$?
  if [[ "${JSON_ARCHIVE_EXIT_CODE}" -eq 0 ]]; then
    echo "[json-report] Archived: ${ARCHIVE_JSON_PATH}"
  else
    echo "[json-report] Failed to archive JSON report to ${ARCHIVE_JSON_PATH}"
  fi
else
  echo "[json-report] Skipping archive: ${JSON_REPORT_PATH} not found"
fi

if [[ "${E2E_SKIP_PDF}" == "1" ]]; then
  echo "[pdf-report] Skipping PDF generation: E2E_SKIP_PDF=1"
  exit "${TEST_EXIT_CODE}"
fi

PDF_EXIT_CODE=0
if [[ -f "${JSON_REPORT_PATH}" ]]; then
  node ./scripts/generate-e2e-pdf-report.mjs \
    --json "${JSON_REPORT_PATH}" \
    --output "${PDF_REPORT_PATH}" \
    --title "Playwright E2E Test Report (${REPORT_TYPE})" \
    --test-type "${REPORT_TYPE}" \
    --base-url "${E2E_ORIGIN}" \
    --run-command "${RUN_COMMAND}" \
    --git-sha "${GIT_SHA}" \
    --json-archive-path "${ARCHIVE_JSON_PATH}" \
    --exclude-projects "${E2E_EXCLUDE_PROJECTS}" || PDF_EXIT_CODE=$?
else
  echo "[pdf-report] Skipping PDF generation: ${JSON_REPORT_PATH} not found"
fi

FINAL_EXIT_CODE="${TEST_EXIT_CODE}"
if [[ "${TEST_EXIT_CODE}" -eq 0 && "${E2E_PDF_STRICT}" == "1" ]]; then
  if [[ "${JSON_ARCHIVE_EXIT_CODE}" -ne 0 ]]; then
    echo "[json-report] Strict mode failure: JSON archive step failed with ${JSON_ARCHIVE_EXIT_CODE}"
    FINAL_EXIT_CODE=5
  elif [[ ! -f "${ARCHIVE_JSON_PATH}" ]]; then
    echo "[json-report] Strict mode failure: expected JSON archive not found at ${ARCHIVE_JSON_PATH}"
    FINAL_EXIT_CODE=6
  elif [[ "${PDF_EXIT_CODE}" -ne 0 ]]; then
    echo "[pdf-report] Strict mode failure: PDF generator exited with ${PDF_EXIT_CODE}"
    FINAL_EXIT_CODE=3
  elif [[ ! -f "${PDF_REPORT_PATH}" ]]; then
    echo "[pdf-report] Strict mode failure: expected PDF not found at ${PDF_REPORT_PATH}"
    FINAL_EXIT_CODE=4
  fi
fi

if [[ -f "${PDF_REPORT_PATH}" ]]; then
  echo "[pdf-report] Output: ${PDF_REPORT_PATH}"
fi

exit "${FINAL_EXIT_CODE}"
