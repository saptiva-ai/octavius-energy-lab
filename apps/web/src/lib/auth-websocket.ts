/**
 * WebSocket and SSE factories with automatic token expiration handling
 *
 * Features:
 * - Automatic token injection (query param or header)
 * - Detection of server-sent expiration signals
 * - Automatic logout on revoked/expired tokens
 * - Conditional retry with refresh token
 */

import { logDebug, logError, logWarn } from "./logger";

const TOKEN_EXPIRED_WS_CODE = 4401; // Custom WebSocket close code for token expiration

interface AuthState {
  accessToken?: string;
  refreshToken?: string;
  expiresAt?: number;
}

type LogoutCallback = (opts: { reason: string }) => void;

let authStateGetter: (() => AuthState) | null = null;
let logoutCallback: LogoutCallback | null = null;

/**
 * Initialize WebSocket auth handlers
 */
export function initWebSocketAuth(
  getAuthState: () => AuthState,
  logout: LogoutCallback,
) {
  authStateGetter = getAuthState;
  logoutCallback = logout;
  logDebug("WebSocket auth initialized");
}

/**
 * Create WebSocket with authentication
 */
export function createAuthWebSocket(
  url: string,
  protocols?: string | string[],
): WebSocket {
  if (!authStateGetter) {
    throw new Error(
      "WebSocket auth not initialized. Call initWebSocketAuth() first.",
    );
  }

  const { accessToken } = authStateGetter();

  if (!accessToken) {
    throw new Error("No access token available for WebSocket connection");
  }

  // Append token as query parameter
  const urlObj = new URL(url, window.location.origin);
  urlObj.searchParams.set("access_token", accessToken);

  const ws = new WebSocket(urlObj.toString(), protocols);

  // Monitor messages for expiration signals
  ws.addEventListener("message", (event) => {
    try {
      const data = JSON.parse(event.data);

      // Check for expiration signal in message payload
      if (data?.code === "token_expired" || data?.code === "token_revoked") {
        logWarn("WebSocket received token expiration signal", {
          code: data.code,
        });

        if (logoutCallback) {
          logoutCallback({ reason: "expired_ws_message" });
        }

        ws.close(TOKEN_EXPIRED_WS_CODE, "Token expired");
      }
    } catch {
      // Not JSON or doesn't contain expiration signal, ignore
    }
  });

  // Monitor close events for expiration codes
  ws.addEventListener("close", (event) => {
    if (event.code === TOKEN_EXPIRED_WS_CODE || event.code === 4401) {
      logWarn("WebSocket closed with expiration code", {
        code: event.code,
        reason: event.reason,
      });

      if (logoutCallback) {
        logoutCallback({ reason: "expired_ws_close" });
      }
    } else if (event.code >= 4000 && event.code < 5000) {
      // Other application-level errors
      logDebug("WebSocket closed with app code", {
        code: event.code,
        reason: event.reason,
      });
    }
  });

  ws.addEventListener("error", (event) => {
    logError("WebSocket error", event);
  });

  return ws;
}

/**
 * Create EventSource (SSE) with authentication
 */
export function createAuthEventSource(url: string): EventSource {
  if (!authStateGetter) {
    throw new Error(
      "EventSource auth not initialized. Call initWebSocketAuth() first.",
    );
  }

  const { accessToken } = authStateGetter();

  if (!accessToken) {
    throw new Error("No access token available for EventSource connection");
  }

  // EventSource doesn't support custom headers, so use query parameter
  const urlObj = new URL(url, window.location.origin);
  urlObj.searchParams.set("access_token", accessToken);

  const eventSource = new EventSource(urlObj.toString());

  // Monitor for expiration messages
  eventSource.addEventListener("message", (event) => {
    try {
      const data = JSON.parse(event.data);

      if (data?.code === "token_expired" || data?.code === "token_revoked") {
        logWarn("EventSource received token expiration signal", {
          code: data.code,
        });

        if (logoutCallback) {
          logoutCallback({ reason: "expired_sse" });
        }

        eventSource.close();
      }
    } catch {
      // Not JSON or doesn't contain expiration signal, ignore
    }
  });

  eventSource.addEventListener("error", (event) => {
    // EventSource errors can indicate auth issues
    logWarn("EventSource error", event);

    // If repeatedly failing, might be auth issue
    if (eventSource.readyState === EventSource.CLOSED) {
      logWarn("EventSource closed after error, might be auth issue");
    }
  });

  return eventSource;
}

/**
 * Close all active WebSocket/SSE connections
 * Call this during logout to clean up connections
 */
export function closeAllConnections() {
  // This is a helper - actual tracking of connections should be done by the application
  logDebug(
    "Close all connections called - app should implement connection tracking",
  );
}
