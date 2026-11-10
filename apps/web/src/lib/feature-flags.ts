import type { ToolId } from "@/types/tools";
import { logWarn } from "@/lib/logger";

const toBool = (value: string | undefined, defaultValue = false) => {
  if (value === undefined) return defaultValue;
  return value.toLowerCase() === "true";
};

const envFilesFlag =
  process.env.NEXT_PUBLIC_TOOL_FILES ??
  process.env.NEXT_PUBLIC_FEATURE_FILES ??
  process.env.NEXT_PUBLIC_FEATURE_ADD_FILES ??
  "true";

export const featureFlags = {
  webSearch: toBool(process.env.NEXT_PUBLIC_FEATURE_WEB_SEARCH, false),
  deepResearch: toBool(process.env.NEXT_PUBLIC_FEATURE_DEEP_RESEARCH, false),
  files: toBool(envFilesFlag, true),
  legacyAddFiles: toBool(process.env.NEXT_PUBLIC_FEATURE_ADD_FILES, false),
  legacyDocumentReview: toBool(
    process.env.NEXT_PUBLIC_FEATURE_DOCUMENT_REVIEW,
    false,
  ),
  googleDrive: toBool(process.env.NEXT_PUBLIC_FEATURE_GOOGLE_DRIVE, false),
  canvas: toBool(process.env.NEXT_PUBLIC_FEATURE_CANVAS, false),
  agentMode: toBool(process.env.NEXT_PUBLIC_FEATURE_AGENT_MODE, false),
  mic: toBool(process.env.NEXT_PUBLIC_FEATURE_MIC, false),
  // Retail advisor (vertical de datos retail). Default true; el backend lo confirma
  // vía /api/features/tools (settings.tool_retail_advisor_enabled).
  retailAdvisor: toBool(process.env.NEXT_PUBLIC_FEATURE_RETAIL_ADVISOR, true),
  // DEPRECATED: auditFile - functionality now integrated in file attachment cards
  auditInline: toBool(process.env.NEXT_PUBLIC_FEATURE_AUDIT_INLINE, false),
  useProdStyleModels: toBool(
    process.env.NEXT_PUBLIC_FEATURE_PROD_STYLE_MODELS,
    true,
  ),
  modelSelector: toBool(process.env.NEXT_PUBLIC_MODEL_SELECTOR_ENABLED, false),
};

const defaultToolVisibility: Record<ToolId, boolean> = (() => {
  const filesEnabled = featureFlags.files;
  return {
    "web-search": featureFlags.webSearch,
    "deep-research": featureFlags.deepResearch,
    files: filesEnabled,
    "add-files": filesEnabled ? false : featureFlags.legacyAddFiles,
    "document-review": filesEnabled ? false : featureFlags.legacyDocumentReview,
    "google-drive": featureFlags.googleDrive,
    canvas: featureFlags.canvas,
    "agent-mode": featureFlags.agentMode,
    "retail-advisor": featureFlags.retailAdvisor,
    // DEPRECATED: "audit-file" removed - now integrated in file attachment cards
  };
})();

export const getDefaultToolVisibility = (): Record<ToolId, boolean> => ({
  ...defaultToolVisibility,
});

export const fetchToolVisibility = async (): Promise<
  Record<ToolId, boolean>
> => {
  try {
    const response = await fetch("/api/features/tools", {
      credentials: "include",
    });
    if (!response.ok) throw new Error("Failed to fetch tool visibility");

    const payload = await response.json();
    if (!payload?.tools) {
      return getDefaultToolVisibility();
    }

    const next: Record<ToolId, boolean> = getDefaultToolVisibility();
    for (const entry of payload.tools as Array<{
      key: ToolId;
      enabled: boolean;
    }>) {
      if (entry?.key in next) {
        next[entry.key] = Boolean(entry.enabled);
      }
    }
    if (next.files) {
      next["add-files"] = false;
      next["document-review"] = false;
    }
    return next;
  } catch (error) {
    logWarn("[feature-flags] Falling back to env-based visibility", error);
    return getDefaultToolVisibility();
  }
};
