/**
 * Unified Auth HTTP Client with proactive and reactive token expiration detection
 *
 * Features:
 * - Proactive expiration check (before network call)
 * - Reactive expiration handling (on 401 responses)
 * - Single refresh attempt to avoid loops
 * - Automatic logout and redirect on expiration
 */

import { logDebug, logError, logWarn } from "./logger";

const SKEW_SECONDS = 30; // Check expiration 30s before actual expiry
const EXPIRATION_ERROR_CODES = [
  "token_expired",
  "token_invalid",
  "token_revoked",
];

interface AuthState {
  accessToken?: string;
  refreshToken?: string;
  expiresAt?: number;
}

type LogoutCallback = (opts: { reason: string; redirectPath?: string }) => void;

let authStateGetter: (() => AuthState) | null = null;
let updateTokensCallback:
  | ((accessToken: string, expiresIn: number) => void)
  | null = null;
let logoutCallback: LogoutCallback | null = null;
let refreshInFlight: Promise<boolean> | null = null;

/**
 * Initialize auth client callbacks
 */
export function initAuthClient(
  getAuthState: () => AuthState,
  updateTokens: (accessToken: string, expiresIn: number) => void,
  logout: LogoutCallback,
) {
  authStateGetter = getAuthState;
  updateTokensCallback = updateTokens;
  logoutCallback = logout;
  logDebug("AuthClient initialized");
}

/**
 * Extract error details from response
 */
async function extractErrorDetails(
  response: Response,
): Promise<{ code?: string; message?: string }> {
  try {
    const contentType = response.headers.get("content-type");
    if (contentType && contentType.includes("application/json")) {
      const data = await response.clone().json();
      return {
        code: data?.code || data?.error?.code,
        message: data?.message || data?.error?.message || data?.detail,
      };
    }
  } catch (error) {
    logWarn("Failed to parse error response", error);
  }
  return {};
}

/**
 * Attempt to refresh access token (only once)
 */
export async function tryRefreshOnce(): Promise<boolean> {
  if (!authStateGetter || !updateTokensCallback) {
    logWarn("AuthClient not initialized");
    return false;
  }

  const { refreshToken } = authStateGetter();
  if (!refreshToken) {
    logDebug("No refresh token available");
    return false;
  }

  // Prevent multiple simultaneous refresh attempts
  if (refreshInFlight) {
    logDebug("Refresh already in flight, waiting...");
    return refreshInFlight;
  }

  refreshInFlight = (async () => {
    try {
      logDebug("Attempting to refresh access token");
      const response = await fetch("/api/auth/refresh", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });

      if (!response.ok) {
        const errorDetails = await extractErrorDetails(response);
        logWarn("Token refresh failed", {
          status: response.status,
          ...errorDetails,
        });
        return false;
      }

      const data = await response.json();
      const { access_token, expires_in } = data;

      if (!access_token || !expires_in) {
        logError("Invalid refresh response", data);
        return false;
      }

      // Update tokens in store
      updateTokensCallback(access_token, expires_in);
      logDebug("Token refreshed successfully");
      return true;
    } catch (error) {
      logError("Token refresh error", error);
      return false;
    } finally {
      refreshInFlight = null;
    }
  })();

  return refreshInFlight;
}

/**
 * Handle token expiration with logout and redirect
 */
function handleExpiration(reason: string, currentPath?: string): never {
  if (!logoutCallback) {
    throw new Error("AuthClient not initialized");
  }

  logWarn("Token expired, logging out", { reason, currentPath });

  // Call logout with reason and optional path to return to
  logoutCallback({
    reason: `expired_${reason}`,
    redirectPath: currentPath,
  });

  // Throw to stop execution
  throw new Error("Session expired");
}

/**
 * Check if token is expired or will expire soon (proactive check)
 */
export function isTokenExpiringSoon(expiresAt?: number): boolean {
  if (!expiresAt) return true;

  const now = Math.floor(Date.now() / 1000);
  const expiresAtSeconds = Math.floor(expiresAt / 1000);

  return now > expiresAtSeconds - SKEW_SECONDS;
}

/**
 * Ensure a valid (non-expired) access token is available.
 * Attempts proactive refresh if the token is expiring soon.
 * Returns the valid token, or null if unavailable.
 */
export async function ensureValidToken(): Promise<string | null> {
  if (!authStateGetter) return null;

  const { accessToken, expiresAt } = authStateGetter();

  if (accessToken && !isTokenExpiringSoon(expiresAt)) {
    return accessToken;
  }

  const refreshed = await tryRefreshOnce();
  if (!refreshed) return null;

  return authStateGetter()?.accessToken || null;
}

/**
 * Enhanced fetch with automatic token handling
 */
export async function authFetch(
  input: RequestInfo | URL,
  init?: RequestInit,
  options?: { skipAuth?: boolean; retryOnExpired?: boolean },
): Promise<Response> {
  const opts = { skipAuth: false, retryOnExpired: true, ...options };

  if (!authStateGetter) {
    throw new Error("AuthClient not initialized. Call initAuthClient() first.");
  }

  // Skip auth for public endpoints
  const url =
    typeof input === "string"
      ? input
      : input instanceof URL
        ? input.href
        : input.url;
  const isPublicEndpoint =
    url.includes("/auth/login") ||
    url.includes("/auth/register") ||
    url.includes("/auth/refresh") ||
    url.includes("/health") ||
    url.includes("/models") ||
    url.includes("/feature-flags");

  if (isPublicEndpoint || opts.skipAuth) {
    return fetch(input, init);
  }

  // Get current auth state
  const { accessToken, expiresAt } = authStateGetter();

  // Proactive check: Token missing or expiring soon
  if (!accessToken || isTokenExpiringSoon(expiresAt)) {
    logDebug("Token missing or expiring soon, attempting refresh");
    const refreshed = await tryRefreshOnce();

    if (!refreshed) {
      const currentPath =
        typeof window !== "undefined" ? window.location.pathname : undefined;
      handleExpiration("proactive", currentPath);
    }

    // Get updated token after refresh
    const updatedState = authStateGetter();
    if (!updatedState.accessToken) {
      handleExpiration("proactive_no_token");
    }
  }

  // Make request with current token
  const currentToken = authStateGetter().accessToken;
  const headers = new Headers(init?.headers);
  headers.set("Authorization", `Bearer ${currentToken}`);
  headers.set("Content-Type", "application/json");

  const response = await fetch(input, {
    ...init,
    headers,
  });

  // Reactive check: Handle 401 responses
  if (response.status === 401) {
    const errorDetails = await extractErrorDetails(response);

    // Check if it's an expiration error
    if (
      errorDetails.code &&
      EXPIRATION_ERROR_CODES.includes(errorDetails.code)
    ) {
      logWarn("Server returned expiration error", errorDetails);

      // Only retry once
      if (opts.retryOnExpired) {
        const refreshed = await tryRefreshOnce();

        if (refreshed) {
          logDebug("Retrying request after token refresh");
          // Retry the request with new token
          return authFetch(input, init, { ...opts, retryOnExpired: false });
        }
      }

      // Refresh failed or already retried, logout
      const currentPath =
        typeof window !== "undefined" ? window.location.pathname : undefined;
      handleExpiration("reactive", currentPath);
    }
  }

  return response;
}

/**
 * Wrapper for common HTTP methods
 */
export const authClient = {
  get: (url: string, init?: RequestInit) =>
    authFetch(url, { ...init, method: "GET" }),
  post: (url: string, body?: any, init?: RequestInit) =>
    authFetch(url, {
      ...init,
      method: "POST",
      body: body ? JSON.stringify(body) : undefined,
    }),
  put: (url: string, body?: any, init?: RequestInit) =>
    authFetch(url, {
      ...init,
      method: "PUT",
      body: body ? JSON.stringify(body) : undefined,
    }),
  patch: (url: string, body?: any, init?: RequestInit) =>
    authFetch(url, {
      ...init,
      method: "PATCH",
      body: body ? JSON.stringify(body) : undefined,
    }),
  delete: (url: string, init?: RequestInit) =>
    authFetch(url, { ...init, method: "DELETE" }),
};

/**
 * Reset auth client state (for testing only)
 * @internal
 */
export function __resetAuthClientForTesting() {
  authStateGetter = null;
  updateTokensCallback = null;
  logoutCallback = null;
  refreshInFlight = null;
}
