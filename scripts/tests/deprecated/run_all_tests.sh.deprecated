#!/bin/bash

# Script maestro para ejecutar TODOS los tests del proyecto
# Backend (API) + Frontend (Web)

# set -e disabled temporarily for debugging

# Obtener la ruta del directorio del script y la raíz del proyecto
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

# Status symbols
RED="✖ "
GREEN="✔ "
YELLOW="▲ "
BLUE="▸ "
CYAN="◆ "
NC=""

# Banner
echo -e "${CYAN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║     COPILOTOS BRIDGE - SUITE COMPLETA DE TESTS              ║${NC}"
echo -e "${CYAN}║              Backend + Frontend                              ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Función para separador
separator() {
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# Contador de resultados
BACKEND_PASSED=0
FRONTEND_PASSED=0
BACKEND_FAILED=0
FRONTEND_FAILED=0

# ============================================================================
# BACKEND TESTS (API)
# ============================================================================

separator
echo -e "${YELLOW}BACKEND TESTS (API)${NC}"
separator
echo ""

cd "$PROJECT_ROOT/apps/api"

# Activar entorno virtual
if [ -d ".venv" ]; then
    echo -e "${GREEN}Activando entorno virtual${NC}"
    source .venv/bin/activate
else
    echo -e "${RED}Error: .venv no encontrado${NC}"
    echo -e "${YELLOW}Ejecute: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt${NC}"
    exit 1
fi

# Configurar variable de entorno
export PROMPT_REGISTRY_PATH=prompts/registry.yaml

echo -e "${CYAN}1⃣  Tests Unitarios - Prompt Registry${NC}"
python -m pytest tests/test_prompt_registry.py --tb=short > /tmp/test_output.txt 2>&1
EXIT_CODE=$?
tail -15 /tmp/test_output.txt
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}Prompt Registry: PASSED${NC}"
    ((BACKEND_PASSED++))
else
    echo -e "${RED}Prompt Registry: FAILED${NC}"
    ((BACKEND_FAILED++))
fi
echo ""

echo -e "${CYAN}2⃣  Tests E2E - Registry Configuration${NC}"
python -m pytest tests/e2e/test_registry_configuration.py --tb=short > /tmp/test_output.txt 2>&1
EXIT_CODE=$?
tail -15 /tmp/test_output.txt
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}Registry Configuration: PASSED${NC}"
    ((BACKEND_PASSED++))
else
    echo -e "${RED}Registry Configuration: FAILED${NC}"
    ((BACKEND_FAILED++))
fi
echo ""

echo -e "${CYAN}3⃣  Tests de Health Check${NC}"
python -m pytest tests/test_health.py --tb=short > /tmp/test_output.txt 2>&1
EXIT_CODE=$?
tail -15 /tmp/test_output.txt
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}Health Check: PASSED${NC}"
    ((BACKEND_PASSED++))
else
    echo -e "${RED}Health Check: FAILED${NC}"
    ((BACKEND_FAILED++))
fi
echo ""

# Regresar al root
cd "$PROJECT_ROOT"

# ============================================================================
# FRONTEND TESTS (WEB)
# ============================================================================

separator
echo -e "${YELLOW}FRONTEND TESTS (WEB)${NC}"
separator
echo ""

cd "$PROJECT_ROOT/apps/web"

# Verificar que node_modules exista
if [ ! -d "node_modules" ]; then
    echo -e "${YELLOW}node_modules no encontrado. Instalando dependencias...${NC}"
    npm install
fi

echo -e "${CYAN}1⃣  Tests de Model Mapping${NC}"
npm test -- __tests__/modelMap.test.ts > /tmp/test_output.txt 2>&1
EXIT_CODE=$?
tail -10 /tmp/test_output.txt
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}Model Mapping: PASSED${NC}"
    ((FRONTEND_PASSED++))
else
    echo -e "${RED}Model Mapping: FAILED (o no configurado)${NC}"
    ((FRONTEND_FAILED++))
fi
echo ""

echo -e "${CYAN}2⃣  Tests de Chat API${NC}"
npm test -- __tests__/chatAPI.test.ts > /tmp/test_output.txt 2>&1
EXIT_CODE=$?
tail -10 /tmp/test_output.txt
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}Chat API: PASSED${NC}"
    ((FRONTEND_PASSED++))
else
    echo -e "${RED}Chat API: FAILED (o no configurado)${NC}"
    ((FRONTEND_FAILED++))
fi
echo ""

echo -e "${CYAN}3⃣  Tests de Model Selector${NC}"
npm test -- __tests__/modelSelector.test.tsx > /tmp/test_output.txt 2>&1
EXIT_CODE=$?
tail -10 /tmp/test_output.txt
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}Model Selector: PASSED${NC}"
    ((FRONTEND_PASSED++))
else
    echo -e "${RED}Model Selector: FAILED (o no configurado)${NC}"
    ((FRONTEND_FAILED++))
fi
echo ""

# Regresar al root
cd "$PROJECT_ROOT"

# ============================================================================
# RESUMEN FINAL
# ============================================================================

separator
echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║                  RESUMEN FINAL                               ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Backend summary
BACKEND_TOTAL=$((BACKEND_PASSED + BACKEND_FAILED))
echo -e "${YELLOW}BACKEND:${NC}"
echo -e "   ✔ Passed: ${GREEN}${BACKEND_PASSED}/${BACKEND_TOTAL}${NC}"
if [ $BACKEND_FAILED -gt 0 ]; then
    echo -e "   ✖ Failed: ${RED}${BACKEND_FAILED}/${BACKEND_TOTAL}${NC}"
fi
echo ""

# Frontend summary
FRONTEND_TOTAL=$((FRONTEND_PASSED + FRONTEND_FAILED))
echo -e "${YELLOW}FRONTEND:${NC}"
echo -e "   ✔ Passed: ${GREEN}${FRONTEND_PASSED}/${FRONTEND_TOTAL}${NC}"
if [ $FRONTEND_FAILED -gt 0 ]; then
    echo -e "   ✖ Failed: ${RED}${FRONTEND_FAILED}/${FRONTEND_TOTAL}${NC}"
fi
echo ""

# Overall summary
TOTAL_PASSED=$((BACKEND_PASSED + FRONTEND_PASSED))
TOTAL_FAILED=$((BACKEND_FAILED + FRONTEND_FAILED))
TOTAL_TESTS=$((TOTAL_PASSED + TOTAL_FAILED))

separator
echo -e "${CYAN}TOTAL GENERAL:${NC}"
echo -e "   Total: ${TOTAL_TESTS} tests"
echo -e "   ✔ Passed: ${GREEN}${TOTAL_PASSED}${NC}"
if [ $TOTAL_FAILED -gt 0 ]; then
    echo -e "   ✖ Failed: ${RED}${TOTAL_FAILED}${NC}"
fi
echo ""

# Calcular porcentaje
if [ $TOTAL_TESTS -gt 0 ]; then
    PERCENTAGE=$((TOTAL_PASSED * 100 / TOTAL_TESTS))
    echo -e "   Éxito: ${GREEN}${PERCENTAGE}%${NC}"
    echo ""
fi

separator
echo ""

# Exit code basado en failures
if [ $TOTAL_FAILED -gt 0 ]; then
    echo -e "${RED}Algunos tests fallaron${NC}"
    exit 1
else
    echo -e "${GREEN}◆ ¡Todos los tests pasaron!${NC}"
    exit 0
fi
