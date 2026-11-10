import { logWarn } from "./logger";

export const RUNTIME = {
  NODE_ENV: process.env.NODE_ENV,
  API_BASE: process.env.NEXT_PUBLIC_API_URL,
  ENABLE_MSW: process.env.NEXT_PUBLIC_ENABLE_MSW,
};

export function assertProdNoMock() {
  const isBrowser = typeof window !== "undefined";
  const isProd = process.env.NODE_ENV === "production";
  const isCI = process.env.CI === "true" || process.env.CI === "1";
  const mswFlag = process.env.NEXT_PUBLIC_ENABLE_MSW;

  if (isProd) {
    const isVercel =
      process.env.VERCEL === "1" || process.env.VERCEL === "true";
    const fallbackApiBase =
      process.env.NEXT_PUBLIC_API_URL ??
      (isCI || !isVercel ? "http://localhost:8001" : undefined);

    const resolvedApiBase = fallbackApiBase;

    // Allow empty NEXT_PUBLIC_API_URL when using Next.js proxy (Docker/local development)
    // Empty string means: use Next.js rewrites to proxy /api/* to backend
    const isUsingProxy = process.env.NEXT_PUBLIC_API_URL === "";
    const hasApiAccess = resolvedApiBase || isUsingProxy;

    if (!hasApiAccess) {
      throw new Error(
        "API base missing; refusing to fall back to mocks in production.",
      );
    }

    const effectiveMswFlag = mswFlag ?? (isCI ? "false" : undefined);

    // REMOVED: Cannot assign to process.env in Next.js after build-time replacement
    // if (!process.env.NEXT_PUBLIC_ENABLE_MSW && effectiveMswFlag) {
    //   process.env.NEXT_PUBLIC_ENABLE_MSW = effectiveMswFlag
    // }

    if (effectiveMswFlag === "true") {
      throw new Error(
        "MSW enabled in production env. Disable it or guard behind a feature flag.",
      );
    }
  }

  // Additional runtime checks
  if (isBrowser && isProd) {
    // Check for potential mock indicators in localStorage
    const mockIndicators = ["msw", "mock-api", "dev-mode"];
    for (const indicator of mockIndicators) {
      if (
        localStorage.getItem(indicator) === "true" ||
        localStorage.getItem(indicator) === "on"
      ) {
        logWarn(
          `Found mock indicator '${indicator}' in localStorage during production. Consider clearing.`,
        );
      }
    }
  }
}
