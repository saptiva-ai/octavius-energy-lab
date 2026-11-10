#!/bin/bash
################################################################################
# Git Secrets Detection Script
#
# Purpose: Detect hardcoded secrets, credentials, IPs, and sensitive data
#          before committing to prevent security leaks
#
# Usage:
#   ./scripts/git-secrets-check.sh [--staged]
#
# Options:
#   --staged    Check only staged files (for pre-commit hook)
#
# Exit codes:
#   0 - No secrets found
#   1 - Secrets detected (commit blocked)
#
################################################################################

set -e

# Colors
RED='\033[0;31m'
YELLOW='\033[0;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

STAGED_ONLY=false
if [[ "$1" == "--staged" ]]; then
    STAGED_ONLY=true
fi

# Get list of files to check
if [ "$STAGED_ONLY" = true ]; then
    FILES=$(git diff --cached --name-only --diff-filter=ACM \
        | grep -v "scripts/git-hooks/git-secrets-check.sh" \
        | grep -v "scripts/git-secrets-check.sh" \
        || true)
else
    FILES=$(git ls-files \
        | grep -v "scripts/git-hooks/git-secrets-check.sh" \
        | grep -v "scripts/git-secrets-check.sh" \
        || true)
fi

# Exit if no files to check
if [ -z "$FILES" ]; then
    echo -e "${GREEN}✓ No files to check${NC}"
    exit 0
fi

echo -e "${BLUE}🔍 Scanning for secrets and sensitive data...${NC}"

# =============================================================================
# DETECTION PATTERNS
# =============================================================================

SECRETS_FOUND=0

# Pattern 1: IP Addresses (exclude localhost, examples, and documentation patterns)
echo -e "${BLUE}  ├─ Checking for hardcoded IP addresses...${NC}"
IP_PATTERN='[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}'
EXCLUDE_IPS='(127\.0\.0\.1|0\.0\.0\.0|localhost|192\.168\.|10\.|172\.(1[6-9]|2[0-9]|3[01])\.|YOUR_SERVER_IP_HERE|1\.2\.3\.4|example\.com)'

for file in $FILES; do
    # Skip binary files, lock files, safe directories, and this script itself
    if [[ "$file" == *.lock ]] || \
       [[ "$file" == *.jpg ]] || \
       [[ "$file" == *.png ]] || \
       [[ "$file" == *.pdf ]] || \
       [[ "$file" == *node_modules* ]] || \
       [[ "$file" == */data/results/* ]] || \
       [[ "$file" == *.example ]] || \
       [[ "$file" == .gitignore ]] || \
       [[ "$file" == */tests/* ]] || \
       [[ "$file" == */test_* ]] || \
       [[ "$file" == "scripts/git-secrets-check.sh" ]]; then
        continue
    fi

    if [ -f "$file" ]; then
        # Check for IPs (excluding common safe IPs)
        MATCHES=$(grep -nE "$IP_PATTERN" "$file" 2>/dev/null | grep -vE "$EXCLUDE_IPS" || true)
        if [ -n "$MATCHES" ]; then
            echo -e "${RED}  │  ✗ IP address found in $file:${NC}"
            echo "$MATCHES" | while read -r line; do
                echo -e "${RED}  │    Line $line${NC}"
            done
            SECRETS_FOUND=$((SECRETS_FOUND + 1))
        fi
    fi
done

# Pattern 2: API Keys and Tokens
echo -e "${BLUE}  ├─ Checking for API keys and tokens...${NC}"
API_KEY_PATTERNS=(
    'api[_-]?key["\s]*[:=]["\s]*[A-Za-z0-9_\-]{20,}'
    'token["\s]*[:=]["\s]*[A-Za-z0-9_\-]{20,}'
    'secret["\s]*[:=]["\s]*[A-Za-z0-9_\-]{20,}'
    'password["\s]*[:=]["\s]*[^"\s]{8,}'
    'SAPTIVA_API_KEY[=:][^\s#]+'
    'ALETHEIA_API_KEY[=:][^\s#]+'
)

EXCLUDE_PATTERNS='(YOUR_.*_HERE|example|placeholder|REDACTED|<.*>|{.*}|\$\{.*\}|\.example)'

for pattern in "${API_KEY_PATTERNS[@]}"; do
    for file in $FILES; do
        if [[ "$file" == *.example ]] || [[ "$file" == .gitignore ]]; then
            continue
        fi

        if [ -f "$file" ]; then
            MATCHES=$(grep -niE "$pattern" "$file" 2>/dev/null | grep -vE "$EXCLUDE_PATTERNS" || true)
            if [ -n "$MATCHES" ]; then
                echo -e "${RED}  │  ✗ Potential API key/token in $file:${NC}"
                echo "$MATCHES" | while read -r line; do
                    # Mask the actual value
                    echo -e "${RED}  │    $(echo "$line" | sed 's/[A-Za-z0-9_-]\{20,\}/[REDACTED]/g')${NC}"
                done
                SECRETS_FOUND=$((SECRETS_FOUND + 1))
            fi
        fi
    done
done

# Pattern 3: SSH User@Host patterns (excluding variables and examples)
echo -e "${BLUE}  ├─ Checking for SSH credentials...${NC}"
SSH_PATTERN='[a-z_][a-z0-9_-]*@[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}'
EXCLUDE_SSH='(\$\{.*\}|YOUR_.*|user@|ubuntu@example|root@localhost)'

for file in $FILES; do
    if [[ "$file" == *.example ]] || [[ "$file" == .gitignore ]]; then
        continue
    fi

    if [ -f "$file" ]; then
        MATCHES=$(grep -nE "$SSH_PATTERN" "$file" 2>/dev/null | grep -vE "$EXCLUDE_SSH" || true)
        if [ -n "$MATCHES" ]; then
            echo -e "${RED}  │  ✗ SSH credentials found in $file:${NC}"
            echo "$MATCHES" | while read -r line; do
                echo -e "${RED}  │    Line $line${NC}"
            done
            SECRETS_FOUND=$((SECRETS_FOUND + 1))
        fi
    fi
done

# Pattern 4: MongoDB/Database connection strings
echo -e "${BLUE}  ├─ Checking for database connection strings...${NC}"
DB_PATTERNS=(
    'mongodb://[^"'\''<>\s]+'
    'postgres://[^"'\''<>\s]+'
    'mysql://[^"'\''<>\s]+'
    'redis://[^"'\''<>\s]+'
)

for pattern in "${DB_PATTERNS[@]}"; do
    for file in $FILES; do
        if [[ "$file" == *.example ]]; then
            continue
        fi

        if [ -f "$file" ]; then
            MATCHES=$(grep -niE "$pattern" "$file" 2>/dev/null | grep -vE "(localhost|127\.0\.0\.1|\$\{.*\}|example)" || true)
            if [ -n "$MATCHES" ]; then
                echo -e "${RED}  │  ✗ Database connection string in $file:${NC}"
                echo "$MATCHES" | while read -r line; do
                    # Mask password in connection string
                    echo -e "${RED}  │    $(echo "$line" | sed 's|://[^:]*:[^@]*@|://user:[REDACTED]@|g')${NC}"
                done
                SECRETS_FOUND=$((SECRETS_FOUND + 1))
            fi
        fi
    done
done

# Pattern 5: Private Keys
echo -e "${BLUE}  ├─ Checking for private keys...${NC}"
for file in $FILES; do
    if [ -f "$file" ]; then
        if grep -q "BEGIN.*PRIVATE KEY" "$file" 2>/dev/null; then
            echo -e "${RED}  │  ✗ Private key found in $file${NC}"
            SECRETS_FOUND=$((SECRETS_FOUND + 1))
        fi
    fi
done

# Pattern 6: .env files (should never be committed except .example)
echo -e "${BLUE}  └─ Checking for .env files...${NC}"
for file in $FILES; do
    if [[ "$file" == *.env ]] && [[ "$file" != *.example ]]; then
        echo -e "${RED}     ✗ .env file should not be committed: $file${NC}"
        echo -e "${YELLOW}     → Move to .gitignore or rename to .env.example${NC}"
        SECRETS_FOUND=$((SECRETS_FOUND + 1))
    fi

    if [[ "$file" == */.env.prod ]] || [[ "$file" == */.env.local ]]; then
        echo -e "${RED}     ✗ Production/local env file detected: $file${NC}"
        echo -e "${YELLOW}     → This file is in .gitignore, ensure it's not force-added${NC}"
        SECRETS_FOUND=$((SECRETS_FOUND + 1))
    fi
done

# =============================================================================
# RESULTS
# =============================================================================

echo ""
if [ $SECRETS_FOUND -gt 0 ]; then
    echo -e "${RED}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${RED}⛔ COMMIT BLOCKED: $SECRETS_FOUND potential secret(s) detected${NC}"
    echo -e "${RED}═══════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo -e "${YELLOW}⚠️  Action required:${NC}"
    echo -e "${YELLOW}  1. Remove hardcoded secrets from files above${NC}"
    echo -e "${YELLOW}  2. Move secrets to envs/.env.prod (in .gitignore)${NC}"
    echo -e "${YELLOW}  3. Use environment variables: \${VARIABLE_NAME}${NC}"
    echo -e "${YELLOW}  4. Update code to read from environment${NC}"
    echo ""
    echo -e "${BLUE}💡 False positive?${NC}"
    echo -e "${BLUE}  - Ensure placeholders use: YOUR_*_HERE, example.com, localhost${NC}"
    echo -e "${BLUE}  - Use variables instead of literals: \${PROD_SERVER_HOST}${NC}"
    echo -e "${BLUE}  - Move real values to .env.prod.example (rename if needed)${NC}"
    echo ""
    exit 1
else
    echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}✓ No secrets detected - Safe to commit${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
    exit 0
fi
