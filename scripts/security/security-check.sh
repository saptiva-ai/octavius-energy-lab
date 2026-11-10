#!/bin/bash
################################################################################
# Security Check Script
#
# Scans for common security issues:
# - Hardcoded secrets in .env files
# - Files that should be gitignored but aren't
# - Weak passwords
# - Exposed API keys
################################################################################

set -e

# Status symbols
RED="✖ "
GREEN="✔ "
YELLOW="▲ "
BLUE="▸ "
NC=""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}⛨ Security Check${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

cd "$PROJECT_ROOT"

ISSUES_FOUND=0

# ============================================================================
# 1. Check for .env files in Git
# ============================================================================
echo -e "${YELLOW}[1/5] Checking for tracked .env files...${NC}"

TRACKED_ENV_FILES=$(git ls-files | grep -E '\.env$|\.env\.' | grep -v '\.example\|\.template' || true)

if [ -n "$TRACKED_ENV_FILES" ]; then
    echo -e "${RED}CRITICAL: .env files are tracked in Git!${NC}"
    echo ""
    echo "Files that should NOT be in Git:"
    echo "$TRACKED_ENV_FILES" | sed 's/^/  /'
    echo ""
    echo "Fix with:"
    echo -e "${GREEN}git rm --cached envs/.env envs/.env.local envs/.env.prod${NC}"
    echo -e "${GREEN}git commit -m \"security: remove env files from tracking\"${NC}"
    echo ""
    ISSUES_FOUND=$((ISSUES_FOUND + 1))
else
    echo -e "${GREEN}No .env files tracked in Git${NC}"
fi

echo ""

# ============================================================================
# 2. Scan for hardcoded secrets
# ============================================================================
echo -e "${YELLOW}[2/5] Scanning for hardcoded secrets...${NC}"

SECRET_PATTERNS=(
    "va-ai-[A-Za-z0-9_-]+"  # SAPTIVA API keys
    "sk-[A-Za-z0-9]{32,}"   # OpenAI-style keys
    "ghp_[A-Za-z0-9]{36}"   # GitHub tokens
)

FOUND_SECRETS=false

for pattern in "${SECRET_PATTERNS[@]}"; do
    # Search in env files (excluding examples)
    if grep -rE "$pattern" envs/ 2>/dev/null | grep -v "\.example\|\.template" | grep -v "your-\|CHANGE_ME" > /dev/null 2>&1; then
        if [ "$FOUND_SECRETS" = false ]; then
            echo -e "${RED}CRITICAL: Real API keys found in env files!${NC}"
            echo ""
            FOUND_SECRETS=true
            ISSUES_FOUND=$((ISSUES_FOUND + 1))
        fi
    fi
done

if [ "$FOUND_SECRETS" = false ]; then
    echo -e "${GREEN}No hardcoded API keys detected${NC}"
fi

echo ""

# ============================================================================
# 3. Check for weak passwords
# ============================================================================
echo -e "${YELLOW}[3/5] Checking for weak/default passwords...${NC}"

WEAK_PASSWORDS=(
    "password"
    "123456"
    "admin"
    "secure_password_change_me"
    "redis_password_change_me"
    "dev-jwt-secret"
    "dev-secret"
)

WEAK_FOUND=false

for weak in "${WEAK_PASSWORDS[@]}"; do
    if grep -r "$weak" envs/.env envs/.env.local 2>/dev/null | grep -q "PASSWORD\|SECRET"; then
        if [ "$WEAK_FOUND" = false ]; then
            echo -e "${YELLOW}WARNING: Weak or default passwords detected${NC}"
            echo ""
            echo "These should be changed before deployment:"
            WEAK_FOUND=true
        fi
        grep -r "$weak" envs/.env envs/.env.local 2>/dev/null | grep "PASSWORD\|SECRET" | sed 's/^/  /' || true
    fi
done

if [ "$WEAK_FOUND" = true ]; then
    echo ""
    echo "Generate strong passwords with:"
    echo -e "${GREEN}make setup${NC}"
    echo ""
    ISSUES_FOUND=$((ISSUES_FOUND + 1))
else
    echo -e "${GREEN}No weak passwords detected${NC}"
fi

echo ""

# ============================================================================
# 4. Verify .gitignore
# ============================================================================
echo -e "${YELLOW}[4/5] Verifying .gitignore configuration...${NC}"

REQUIRED_IGNORES=(
    ".env"
    "*.env"
    ".env.*"
    "envs/.env.local"
    "envs/.env.prod"
    "secrets.json"
    "secrets.yaml"
)

GITIGNORE_ISSUES=false

for pattern in "${REQUIRED_IGNORES[@]}"; do
    if ! grep -q "$pattern" .gitignore 2>/dev/null; then
        if [ "$GITIGNORE_ISSUES" = false ]; then
            echo -e "${YELLOW}WARNING: .gitignore may be missing patterns${NC}"
            GITIGNORE_ISSUES=true
        fi
        echo "  Missing: $pattern"
    fi
done

if [ "$GITIGNORE_ISSUES" = false ]; then
    echo -e "${GREEN}.gitignore properly configured${NC}"
fi

echo ""

# ============================================================================
# 5. Check file permissions
# ============================================================================
echo -e "${YELLOW}[5/5] Checking file permissions...${NC}"

PERMISSION_ISSUES=false

for env_file in envs/.env envs/.env.local envs/.env.prod; do
    if [ -f "$env_file" ]; then
        PERMS=$(stat -c "%a" "$env_file" 2>/dev/null || stat -f "%A" "$env_file" 2>/dev/null)
        if [ "$PERMS" != "600" ] && [ "$PERMS" != "400" ]; then
            if [ "$PERMISSION_ISSUES" = false ]; then
                echo -e "${YELLOW}WARNING: Insecure file permissions${NC}"
                echo ""
                PERMISSION_ISSUES=true
            fi
            echo "  $env_file: $PERMS (should be 600 or 400)"
        fi
    fi
done

if [ "$PERMISSION_ISSUES" = false ]; then
    echo -e "${GREEN}File permissions are secure${NC}"
else
    echo ""
    echo "Fix with:"
    echo -e "${GREEN}chmod 600 envs/.env*${NC}"
    echo ""
fi

echo ""

# ============================================================================
# Summary
# ============================================================================
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}Summary${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

if [ "$ISSUES_FOUND" -eq 0 ]; then
    echo -e "${GREEN}No critical security issues found!${NC}"
    echo ""
    exit 0
else
    echo -e "${RED}Found $ISSUES_FOUND critical security issue(s)${NC}"
    echo ""
    echo "Please review and fix the issues above."
    echo ""
    echo -e "${YELLOW}For guidance, see:${NC}"
    echo "  • SECURITY_ALERT.md"
    echo "  • docs/DEPLOY_GUIDE.md"
    echo "  • make setup (for interactive secure configuration)"
    echo ""
    exit 1
fi
