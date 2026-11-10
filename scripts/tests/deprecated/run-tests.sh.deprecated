#!/bin/bash

# ============================================================================
# TEST RUNNER SCRIPT FOR COPILOTOS BRIDGE
# ============================================================================

set -e  # Exit on any error

echo "▸ Running Copilotos Bridge Test Suite"
echo "========================================"

# Status symbols for logs
RED="✖ "
GREEN="✔ "
YELLOW="▲ "
BLUE="▸ "
NC=""

# Function to print colored output
print_status() {
    echo -e "${BLUE}${NC} $1"
}

print_success() {
    echo -e "${GREEN}${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}${NC} $1"
}

print_error() {
    echo -e "${RED}${NC} $1"
}

# ============================================================================
# BACKEND TESTS (Python)
# ============================================================================

print_status "Running Backend Tests..."

cd apps/api

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    print_warning "Virtual environment not found. Creating one..."
    python -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
print_status "Installing Python dependencies..."
pip install -r requirements.txt
pip install pytest pytest-cov pytest-asyncio httpx

# Run tests with coverage
print_status "Running Python tests with coverage..."
pytest src/tests/ \
    --cov=src \
    --cov-report=html:htmlcov \
    --cov-report=term-missing \
    --cov-fail-under=70 \
    -v

# Check if tests passed
if [ $? -eq 0 ]; then
    print_success "Backend tests passed!"
else
    print_error "Backend tests failed!"
    exit 1
fi

cd ../..

# ============================================================================
# FRONTEND TESTS (TypeScript/React)
# ============================================================================

print_status "Running Frontend Tests..."

cd apps/web

# Install dependencies
print_status "Installing Node.js dependencies..."
npm install

# Run tests
print_status "Running TypeScript/React tests..."
npm run test -- --coverage --watchAll=false

# Check if tests passed
if [ $? -eq 0 ]; then
    print_success "Frontend tests passed!"
else
    print_error "Frontend tests failed!"
    exit 1
fi

cd ../..

# ============================================================================
# LINTING & TYPE CHECKING
# ============================================================================

print_status "Running Code Quality Checks..."

# Backend linting
print_status "Checking Python code quality..."
cd apps/api
python -m flake8 src/ --max-line-length=100 --ignore=E203,W503
python -m black src/ --check
python -m isort src/ --check-only
cd ../..

# Frontend linting
print_status "Checking TypeScript code quality..."
cd apps/web
npm run lint
npm run type-check
cd ../..

# ============================================================================
# INTEGRATION TESTS (if available)
# ============================================================================

if [ -f "tests/integration/test_api.py" ]; then
    print_status "Running Integration Tests..."
    # Start services if needed
    docker-compose up -d mongodb redis
    sleep 5

    # Run integration tests
    python -m pytest tests/integration/ -v

    # Stop services
    docker-compose down
fi

# ============================================================================
# SUMMARY
# ============================================================================

print_success "◆ All tests completed successfully!"
echo ""
echo "▸ Coverage Reports:"
echo "  - Backend: apps/api/htmlcov/index.html"
echo "  - Frontend: apps/web/coverage/lcov-report/index.html"
echo ""
print_status "Test execution completed."