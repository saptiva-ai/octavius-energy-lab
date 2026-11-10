#!/bin/bash
# ============================================================================
# Password Reset Configuration Checker
# ============================================================================
# Verifies that all required environment variables for password reset
# functionality are properly configured
#
# Usage:
#   ./scripts/check-password-reset-config.sh
#   ./scripts/check-password-reset-config.sh --production
#
# Returns:
#   0 - All configuration valid
#   1 - Missing or invalid configuration
# ============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Track errors
HAS_ERRORS=0

# ============================================================================
# Helper Functions
# ============================================================================

error() {
    echo -e "${RED}✗ ERROR:${NC} $1"
    HAS_ERRORS=1
}

warning() {
    echo -e "${YELLOW}⚠ WARNING:${NC} $1"
}

success() {
    echo -e "${GREEN}✓${NC} $1"
}

info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

check_var() {
    local var_name="$1"
    local var_value="${!var_name}"
    local description="$2"
    local required="${3:-true}"

    if [ -z "$var_value" ]; then
        if [ "$required" = "true" ]; then
            error "$description ($var_name) is MISSING"
        else
            warning "$description ($var_name) is not set (optional)"
        fi
    else
        # Mask sensitive values
        local display_value="$var_value"
        if [[ "$var_name" == *"PASSWORD"* ]] || [[ "$var_name" == *"SECRET"* ]] || [[ "$var_name" == *"KEY"* ]]; then
            display_value="***${var_value: -4}"
        fi
        success "$description ($var_name): $display_value"
    fi
}

# ============================================================================
# Main Check
# ============================================================================

echo ""
echo "=================================================================="
echo "  Password Reset Configuration Checker"
echo "=================================================================="
echo ""

# Determine which env file to check
ENV_FILE="$PROJECT_ROOT/envs/.env"
if [ "$1" = "--production" ]; then
    ENV_FILE="$PROJECT_ROOT/envs/.env"
    info "Checking PRODUCTION configuration"
else
    info "Checking LOCAL configuration"
fi

# Load environment variables
if [ -f "$ENV_FILE" ]; then
    success "Found env file: $ENV_FILE"
    set -a
    source "$ENV_FILE"
    set +a
else
    error "Environment file not found: $ENV_FILE"
    echo ""
    echo "Create it by copying the example:"
    echo "  cp envs/.env.production.example envs/.env"
    exit 1
fi

echo ""
echo "=== SMTP Configuration ==="
check_var "SMTP_HOST" "SMTP Server Host" true
check_var "SMTP_PORT" "SMTP Server Port" true
check_var "SMTP_USER" "SMTP Username" true
check_var "SMTP_PASSWORD" "SMTP Password" true
check_var "SMTP_FROM_EMAIL" "From Email Address" true

echo ""
echo "=== Password Reset URLs ==="
check_var "PASSWORD_RESET_URL_BASE" "Password Reset Base URL" true

# Validate URL format
if [ -n "$PASSWORD_RESET_URL_BASE" ]; then
    if [[ ! "$PASSWORD_RESET_URL_BASE" =~ ^https?:// ]]; then
        error "PASSWORD_RESET_URL_BASE must start with http:// or https://"
    fi
fi

echo ""
echo "=== JWT Configuration ==="
check_var "JWT_SECRET_KEY" "JWT Secret Key" true
check_var "JWT_ALGORITHM" "JWT Algorithm" true

# Check JWT_SECRET_KEY strength
if [ -n "$JWT_SECRET_KEY" ]; then
    if [ ${#JWT_SECRET_KEY} -lt 32 ]; then
        warning "JWT_SECRET_KEY is less than 32 characters (current: ${#JWT_SECRET_KEY})"
        info "Generate stronger key with: openssl rand -hex 32"
    fi
fi

echo ""
echo "=== Docker Services (if applicable) ==="

# Check if backend service is running
if command -v docker &> /dev/null; then
    if docker ps | grep -q "octavios.*backend"; then
        success "Backend container is running"

        # Check if backend can access SMTP config
        echo ""
        info "Testing SMTP configuration in backend container..."
        docker exec octavios-backend-1 python -c "
from apps.backend.src.core.config import get_settings
settings = get_settings()
print(f'SMTP_USER: {bool(settings.smtp_user)}')
print(f'SMTP_PASSWORD: {bool(settings.smtp_password)}')
print(f'SMTP_HOST: {settings.smtp_host}')
print(f'SMTP_PORT: {settings.smtp_port}')
print(f'PASSWORD_RESET_URL_BASE: {settings.password_reset_url_base}')
" 2>/dev/null || warning "Could not verify backend container configuration"
    else
        info "Backend container not running (docker compose may not be started)"
    fi
else
    info "Docker not available - skipping container checks"
fi

echo ""
echo "=================================================================="
if [ $HAS_ERRORS -eq 0 ]; then
    echo -e "${GREEN}✓ All password reset configuration checks passed${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Test password reset: make test-password-reset"
    echo "  2. Check backend logs: docker logs octavios-backend-1 -f"
    echo "  3. Send test email: scripts/testing/test_password_reset.sh"
else
    echo -e "${RED}✗ Configuration errors detected${NC}"
    echo ""
    echo "Required fixes:"
    echo "  1. Set missing environment variables in: $ENV_FILE"
    echo "  2. For Gmail SMTP, generate App Password:"
    echo "     https://myaccount.google.com/apppasswords"
    echo "  3. Restart services: cd infra && docker compose up -d --force-recreate"
    echo "  4. Verify with: scripts/check-password-reset-config.sh"
    exit 1
fi
echo "=================================================================="
echo ""
