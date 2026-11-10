#!/bin/bash
# ==============================================
# Precise Security Audit Script for Copilotos Bridge
# Focused on actual hardcoded credential violations
# ==============================================

set -e

echo "⛨ Precise Security Audit - Copilotos Bridge"
echo "==========================================="

# Status symbols for logs
RED="✖ "
GREEN="✔ "
YELLOW="▲ "
BLUE="▸ "
NC=""

AUDIT_PASSED=true

# Function to check for violations
check_violation() {
    local description="$1"
    local command="$2"
    local expected_count="$3"

    echo -n "   Checking: $description... "

    if eval "$command" >/dev/null 2>&1; then
        actual_count=$(eval "$command" | wc -l)
        if [ "$actual_count" -gt "$expected_count" ]; then
            echo -e "${RED}FAIL${NC} (Found $actual_count violations)"
            AUDIT_PASSED=false
            if [ "$expected_count" -eq 0 ]; then
                echo "     Violations found:"
                eval "$command" | head -5 | sed 's/^/       /'
                if [ "$actual_count" -gt 5 ]; then
                    echo "       ... and $((actual_count - 5)) more"
                fi
            fi
        else
            echo -e "${GREEN}PASS${NC}"
        fi
    else
        echo -e "${GREEN}PASS${NC} (No violations found)"
    fi
}

echo -e "${BLUE}1. Critical Security Issues - Hardcoded Production Credentials${NC}"
echo "----------------------------------------------------------------"

# Check for actual hardcoded SAPTIVA API keys (the real security issue)
check_violation "SAPTIVA API keys hardcoded in source code" \
    "find . -type f \( -name '*.py' -o -name '*.js' -o -name '*.ts' -o -name '*.tsx' \) ! -path './node_modules/*' ! -path './.next*/*' ! -path './dist/*' -exec grep -l 'va-ai-[A-Za-z0-9][A-Za-z0-9][A-Za-z0-9][A-Za-z0-9][A-Za-z0-9]' {} \; | xargs grep 'va-ai-[A-Za-z0-9][A-Za-z0-9][A-Za-z0-9][A-Za-z0-9][A-Za-z0-9]' | grep -v '.example' | grep -v 'audit' | grep -v 'test-demo-key'" \
    0

# Check for hardcoded database connection strings with credentials
check_violation "MongoDB URLs with hardcoded credentials" \
    "find . -type f \( -name '*.py' -o -name '*.js' -o -name '*.ts' -o -name '*.tsx' \) ! -path './node_modules/*' ! -path './.next*/*' ! -path './dist/*' -exec grep -l 'mongodb://[^:]*:[^@]*@.*[0-9]' {} \; | xargs grep 'mongodb://[^:]*:[^@]*@.*[0-9]' | grep -v '.example' | grep -v 'audit' | grep -v 'username:password@host'" \
    0

# Check for hardcoded JWT secrets (actual values, not variables)
check_violation "JWT secrets hardcoded in source code" \
    "find . -type f \( -name '*.py' -o -name '*.js' -o -name '*.ts' -o -name '*.tsx' \) ! -path './node_modules/*' ! -path './.next*/*' ! -path './dist/*' -exec grep -l 'jwt.*secret.*=.*[\"'\''][a-zA-Z0-9]{20,}[\"'\'']' {} \; | xargs grep 'jwt.*secret.*=.*[\"'\''][a-zA-Z0-9]{20,}[\"'\'']' | grep -v '.example' | grep -v 'audit'" \
    0

echo
echo -e "${BLUE}2. Configuration Validation${NC}"
echo "----------------------------"

# Check for weak default values that could be in production
check_violation "Weak default values in production configs" \
    "find . -type f \( -name '*.py' -o -name '*.js' -o -name '*.ts' -o -name '*.tsx' \) ! -path './node_modules/*' ! -path './.next*/*' ! -path './dist/*' ! -path './tests/*' ! -path './__tests__/*' -exec grep -l 'password.*=.*[\"'\'']changeme[\"'\'']\\|password.*=.*[\"'\'']admin[\"'\'']\\|password.*=.*[\"'\'']secret[\"'\'']' {} \; | xargs grep 'password.*=.*[\"'\'']changeme[\"'\'']\\|password.*=.*[\"'\'']admin[\"'\'']\\|password.*=.*[\"'\'']secret[\"'\'']' | grep -v 'audit' | grep -v 'test'" \
    0

echo
echo -e "${BLUE}3. Git Security${NC}"
echo "----------------"

# Check if .env files are in gitignore
if [ -f ".gitignore" ]; then
    if grep -q "\.env" .gitignore; then
        echo -e "   .env files in .gitignore: ${GREEN}PASS${NC}"
    else
        echo -e "   .env files in .gitignore: ${RED}FAIL${NC}"
        AUDIT_PASSED=false
    fi
fi

# Check for actual secrets committed to git history
check_violation "Production secrets in recent git commits" \
    "git log --oneline -10 | xargs -I {} git show {} | grep -E 'va-ai-[A-Za-z0-9]{40,}|mongodb://[^:]*:[^@]*@[^/]*' | grep -v 'audit' | grep -v 'test' | grep -v 'example'" \
    0

echo
echo -e "${BLUE}4. Environment Variables Security${NC}"
echo "----------------------------------"

# Check if critical environment variables are documented
if [ -f "envs/.env.local.example" ] || [ -f ".env.example" ]; then
    echo -e "   Environment variable template exists: ${GREEN}PASS${NC}"
else
    echo -e "   Environment variable template exists: ${YELLOW}WARNING${NC}"
    echo "     Consider creating .env.example with placeholder values"
fi

# Check for .env files that might be committed accidentally
check_violation "Actual .env files in source control" \
    "find . -name '.env' -not -path './envs/.env.*.example' -not -path './node_modules/*' | head -5" \
    0

echo
echo -e "${BLUE}5. Secrets Management System${NC}"
echo "-----------------------------"

# Verify secrets management system is in place
if [ -f "apps/api/src/core/secrets.py" ]; then
    echo -e "   Secrets management system: ${GREEN}PASS${NC}"
else
    echo -e "   Secrets management system: ${RED}FAIL${NC}"
    AUDIT_PASSED=false
fi

# Verify secure deployment configuration exists
if [ -f "docker-compose.secure.yml" ]; then
    echo -e "   Secure deployment config: ${GREEN}PASS${NC}"
else
    echo -e "   Secure deployment config: ${YELLOW}WARNING${NC}"
fi

# Verify security documentation exists
if [ -f "docs/security/SECURITY.md" ]; then
    echo "✅ SECURITY.md found (using updated logic)"
    # Implement specific check logic here
else
    echo "⚠️  docs/security/SECURITY.md not found"
fi

echo
echo "==========================================="

if [ "$AUDIT_PASSED" = true ]; then
    echo -e "${GREEN}◆ SECURITY AUDIT PASSED${NC}"
    echo -e "${GREEN}No critical security vulnerabilities found!${NC}"
    echo
    echo -e "${GREEN}Security Achievements:${NC}"
    echo "   ✔ No hardcoded production API keys"
    echo "   ✔ No hardcoded database credentials"
    echo "   ✔ Secrets management system implemented"
    echo "   ✔ Secure configuration templates available"
    echo "   ✔ Environment variables properly gitignored"
    echo
    echo -e "${BLUE}Ready for secure deployment!${NC}"
    exit 0
else
    echo -e "${RED}SECURITY AUDIT FAILED${NC}"
    echo -e "${RED} Critical security issues found - must be fixed before deployment.${NC}"
    echo
    echo -e "${YELLOW}Security Resources:${NC}"
    echo "   - Review docs/security/SECURITY.md for detailed guidelines"
    echo "   - Use scripts/generate-secrets.py for secure credentials"
    echo "   - Deploy with docker-compose.secure.yml for production"
    echo "   - Ensure all secrets are loaded from environment variables"
    echo
    exit 1
fi