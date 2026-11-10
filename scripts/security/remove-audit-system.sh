#!/usr/bin/env bash
#
# remove-audit-system.sh
# Script para eliminar el sistema de auditoría COPILOTO-AUDIT del código base
#
# Uso: ./scripts/remove-audit-system.sh [--dry-run]
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

DRY_RUN=false

# Parse arguments
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=true
    echo -e "${YELLOW}🔍 DRY RUN MODE - No files will be deleted${NC}\n"
fi

# Function to remove file or directory
remove_item() {
    local item="$1"

    if [[ ! -e "$item" ]]; then
        echo -e "${YELLOW}⚠️  Not found: $item${NC}"
        return
    fi

    if $DRY_RUN; then
        echo -e "${GREEN}Would remove: $item${NC}"
    else
        git rm -r "$item" 2>/dev/null || rm -rf "$item"
        echo -e "${RED}✗ Removed: $item${NC}"
    fi
}

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Removing COPILOTO-AUDIT Audit System${NC}"
echo -e "${GREEN}========================================${NC}\n"

# ============================================================================
# BACKEND FILES
# ============================================================================

echo -e "\n${YELLOW}📦 Backend Services${NC}"

# Auditors
remove_item "apps/api/src/services/validation_coordinator.py"
remove_item "apps/api/src/services/compliance_auditor.py"
remove_item "apps/api/src/services/format_auditor.py"
remove_item "apps/api/src/services/grammar_auditor.py"
remove_item "apps/api/src/services/logo_auditor.py"
remove_item "apps/api/src/services/typography_auditor.py"
remove_item "apps/api/src/services/color_palette_auditor.py"
remove_item "apps/api/src/services/color_auditor.py"
remove_item "apps/api/src/services/semantic_consistency_auditor.py"
remove_item "apps/api/src/services/entity_consistency_auditor.py"

# Policy & validation support
remove_item "apps/api/src/services/policy_manager.py"
remove_item "apps/api/src/services/policy_detector.py"
remove_item "apps/api/src/services/validation_context_formatter.py"
remove_item "apps/api/src/services/summary_formatter.py"
remove_item "apps/api/src/services/report_generator.py"

# Tools
remove_item "apps/api/src/services/tools/audit_file_tool.py"

echo -e "\n${YELLOW}📊 Backend Models & Schemas${NC}"

remove_item "apps/api/src/models/validation_report.py"
remove_item "apps/api/src/schemas/audit_message.py"

echo -e "\n${YELLOW}⚙️  Backend Configuration${NC}"

remove_item "apps/api/src/config/policies.yaml"
remove_item "apps/api/src/config/compliance.yaml"

echo -e "\n${YELLOW}🧪 Backend Tests${NC}"

remove_item "apps/api/tests/unit/test_compliance_auditor.py"
remove_item "apps/api/tests/unit/test_format_numeric.py"
remove_item "apps/api/tests/unit/test_typography.py"
remove_item "apps/api/tests/unit/test_color_palette.py"
remove_item "apps/api/tests/unit/test_entity_consistency.py"
remove_item "apps/api/tests/unit/test_semantic_consistency.py"

# ============================================================================
# FRONTEND FILES
# ============================================================================

echo -e "\n${YELLOW}🎨 Frontend Components${NC}"

remove_item "apps/web/src/components/validation"
remove_item "apps/web/src/components/chat/AuditProgress.tsx"
remove_item "apps/web/src/components/chat/AuditReportCard.tsx"
remove_item "apps/web/src/components/chat/AuditToggle.tsx"
remove_item "apps/web/src/components/chat/MessageAuditCard.tsx"

echo -e "\n${YELLOW}🪝 Frontend Hooks${NC}"

remove_item "apps/web/src/hooks/useAuditFile.ts"
remove_item "apps/web/src/hooks/useAuditFlow.ts"
remove_item "apps/web/src/hooks/__tests__/useAuditFlow.test.ts"

echo -e "\n${YELLOW}💾 Frontend Stores & Types${NC}"

remove_item "apps/web/src/lib/stores/audit-store.ts"
remove_item "apps/web/src/types/validation.ts"

echo -e "\n${YELLOW}🧪 Frontend Tests${NC}"

remove_item "apps/web/src/components/files/__tests__/FileAttachmentList.audit-toggle.test.tsx"

# ============================================================================
# DOCUMENTATION
# ============================================================================

echo -e "\n${YELLOW}📚 Documentation${NC}"

remove_item "docs/copiloto-audit"
remove_item "docs/AUDIT_SYSTEM_ARCHITECTURE.md"

# ============================================================================
# ASSETS
# ============================================================================

echo -e "\n${YELLOW}🖼️  Assets${NC}"

remove_item "apps/api/assets/logo_template.png"

# ============================================================================
# PARTIAL FILE MODIFICATIONS
# ============================================================================

echo -e "\n${YELLOW}📝 Files with audit-related code (manual review needed):${NC}"

FILES_TO_REVIEW=(
    "apps/api/src/routers/chat.py"
    "apps/api/src/routers/reports.py"
    "apps/api/src/routers/documents.py"
    "apps/api/src/models/__init__.py"
    "apps/web/src/components/chat/ChatInterface.tsx"
    "apps/web/src/components/chat/ChatMessage.tsx"
    "apps/web/src/components/chat/ToolsPanel.tsx"
    "apps/web/src/components/files/FileAttachmentList.tsx"
    "apps/web/src/types/tools.tsx"
    "apps/web/src/lib/feature-flags.ts"
)

for file in "${FILES_TO_REVIEW[@]}"; do
    if [[ -e "$file" ]]; then
        echo -e "  ${YELLOW}⚠️  Review: $file${NC}"
    fi
done

# ============================================================================
# SUMMARY
# ============================================================================

echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}Summary${NC}"
echo -e "${GREEN}========================================${NC}"

if $DRY_RUN; then
    echo -e "${YELLOW}This was a DRY RUN. No files were actually deleted.${NC}"
    echo -e "${YELLOW}Run without --dry-run to perform the actual removal.${NC}"
else
    echo -e "${RED}Audit system files have been removed.${NC}"
    echo -e "\n${YELLOW}Next steps:${NC}"
    echo -e "1. Review files listed above for audit-related code"
    echo -e "2. Remove audit tool references from routers/chat.py"
    echo -e "3. Remove ValidationReport from models/__init__.py"
    echo -e "4. Remove audit UI components from ChatInterface.tsx"
    echo -e "5. Update feature flags to remove audit-related flags"
    echo -e "6. Run tests: make test-api && make test-web"
    echo -e "7. Commit changes: git commit -m 'refactor: remove audit system'"
fi

echo -e "\n${GREEN}✓ Done${NC}\n"
