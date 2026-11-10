#!/bin/bash
# ==============================================
# Security Audit Script for Copilotos Bridge
# ==============================================

set -e

echo "⛨ Security Audit - Copilotos Bridge"
echo "===================================="

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

echo -e "${BLUE}1. Hardcoded Credentials Check${NC}"
echo "--------------------------------"

# Check for hardcoded API keys
check_violation "API keys in source code" \
    "grep -r --include='*.py' --include='*.js' --include='*.ts' --include='*.tsx' 'va-ai-[A-Za-z0-9]\\+' . | grep -v '.example' | grep -v 'audit'" \
    0

# Check for hardcoded passwords
check_violation "Hardcoded passwords" \
    "grep -r --include='*.py' --include='*.js' --include='*.ts' --include='*.tsx' 'password.*=.*[\"'][^\"']*[\"']' . | grep -v '.example' | grep -v 'placeholder' | grep -v 'your-' | grep -v 'audit'" \
    0

# Check for hardcoded secrets
check_violation "Hardcoded JWT secrets" \
    "grep -r --include='*.py' --include='*.js' --include='*.ts' --include='*.tsx' 'secret.*=.*[\"'][^\"']*[\"']' . | grep -v '.example' | grep -v 'placeholder' | grep -v 'your-' | grep -v 'audit'" \
    0

# Check for database URLs with credentials
check_violation "Database URLs with embedded credentials" \
    "grep -r --include='*.py' --include='*.js' --include='*.ts' --include='*.tsx' 'mongodb://[^:]*:[^@]*@' . | grep -v '.example' | grep -v 'audit'" \
    0

echo
echo -e "${BLUE}2. Configuration Security Check${NC}"
echo "-------------------------------"

# Check for weak default values
check_violation "Weak default passwords" \
    "grep -r --include='*.py' --include='*.js' --include='*.ts' --include='*.tsx' --include='*.yml' --include='*.yaml' 'password.*changeme\\|password.*change_me\\|password.*admin\\|password.*secret\\|password.*123' . | grep -v 'audit'" \
    0

# Check for TODO security items
check_violation "Unresolved security TODOs" \
    "grep -r --include='*.py' --include='*.js' --include='*.ts' --include='*.tsx' 'TODO.*security\\|TODO.*secret\\|TODO.*credential\\|TODO.*password' . | grep -v 'audit'" \
    0

echo
echo -e "${BLUE}3. File Permissions Check${NC}"
echo "------------------------------"

# Check for world-readable secret files
if [ -d "/etc/octavios/secrets" ]; then
    check_violation "World-readable secret files" \
        "find /etc/octavios/secrets -type f \\( -perm -004 -o -perm -040 \\)" \
        0
fi

# Check for executable configs
check_violation "Executable config files" \
    "find . -name '*.env*' -executable -type f | grep -v 'audit'" \
    0

echo
echo -e "${BLUE}4. Git Security Check${NC}"
echo "---------------------"

# Check if .env files are in gitignore
if [ -f ".gitignore" ]; then
    if grep -q "\.env" .gitignore; then
        echo -e "   .env files in .gitignore: ${GREEN}PASS${NC}"
    else
        echo -e "   .env files in .gitignore: ${RED}FAIL${NC}"
        AUDIT_PASSED=false
    fi
fi

# Check for secrets in git history (recent commits)
check_violation "Secrets in recent git commits" \
    "git log --oneline -10 | xargs -I {} git show {} | grep -i 'password\\|secret\\|key.*=' | grep -v 'audit'" \
    0

echo
echo -e "${BLUE}5. Docker Security Check${NC}"
echo "-------------------------"

# Check for secrets in Docker files
check_violation "Secrets in Dockerfiles" \
    "grep -r --include='Dockerfile*' --include='*.yml' --include='*.yaml' 'ENV.*PASSWORD\\|ENV.*SECRET\\|ENV.*KEY.*=' . | grep -v 'audit'" \
    0

echo
echo -e "${BLUE}6. Dependencies Security Check${NC}"
echo "-------------------------------"

# Check for known vulnerable patterns
check_violation "Eval/exec usage (potential RCE)" \
    "grep -r --include='*.py' --include='*.js' --include='*.ts' 'eval(\\|exec(' . | grep -v 'audit'" \
    0

echo
echo "===================================="

if [ "$AUDIT_PASSED" = true ]; then
    echo -e "${GREEN}◆ SECURITY AUDIT PASSED${NC}"
    echo -e "${GREEN}All security checks completed successfully!${NC}"
    exit 0
else
    echo -e "${RED}SECURITY AUDIT FAILED${NC}"
    echo -e "${RED} Please fix the identified security issues before deployment.${NC}"
    echo
    echo -e "${YELLOW}Security Resources:${NC}"
    echo "   - Review docs/security/SECURITY.md for detailed guidelines"
    echo "   - Use scripts/generate-secrets.py for secure credentials"
    echo "   - Deploy with docker-compose.secure.yml for production"
    echo
    exit 1
fi