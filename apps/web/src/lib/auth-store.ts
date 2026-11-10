"use client";

import { createWithEqualityFn } from "zustand/traditional";
import { devtools, persist, createJSONStorage } from "zustand/middleware";

import {
  apiClient,
  setAuthTokenGetter,
  setLogoutHandler,
  LoginRequest,
} from "./api-client";
import type {
  AuthTokens,
  RegisterPayload,
  RefreshTokenResponse,
  UserProfile,
} from "./types";
import { logDebug, logError, logWarn } from "./logger";

// ISSUE-019: Import stores for cleanup on logout
import { useChatStore } from "./stores/chat-store";
import { useHistoryStore } from "./stores/history-store";
import { useFilesStore } from "./stores/files-store";

interface AuthState {
  user: UserProfile | null;
  accessToken: string | null;
  refreshToken: string | null;
  expiresAt: number | null;
  status: "idle" | "loading" | "error";
  error: AuthErrorInfo | null;
  isHydrated: boolean;
  intendedPath: string | null;
}

interface AuthActions {
  login: (credentials: LoginRequest) => Promise<boolean>;
  register: (payload: RegisterPayload) => Promise<boolean>;
  logout: (opts?: { reason?: string; redirectPath?: string }) => Promise<void>;
  refreshSession: () => Promise<boolean>;
  fetchProfile: () => Promise<void>;
  clearError: () => void;
  clearCache: () => void;
  resetAuthState: () => void;
  isAuthenticated: () => boolean;
  setIntendedPath: (path: string | null) => void;
  updateTokens: (accessToken: string, expiresIn: number) => void;
  setHydrated: (isHydrated: boolean) => void;
}

const AUTH_STORAGE_KEY = "copilotos-auth-state";
const ONE_MINUTE_MS = 60_000;

type AuthStore = AuthState & AuthActions;

interface AuthErrorInfo {
  code: string;
  message: string;
  field?: string;
}

const ERROR_MESSAGES: Record<string, string> = {
  // Authentication errors
  BAD_CREDENTIALS: "Correo o contraseña incorrectos.",
  INVALID_CREDENTIALS: "Correo o contraseña incorrectos.",
  ACCOUNT_INACTIVE: "La cuenta está inactiva. Contacta al administrador.",
  INVALID_TOKEN: "El token de sesión ya no es válido.",
  token_expired: "Tu sesión ha expirado. Inicia sesión nuevamente.",
  token_invalid: "Tu sesión ya no es válida. Inicia sesión nuevamente.",
  token_revoked: "Tu sesión ha sido revocada. Inicia sesión nuevamente.",

  // Registration errors
  USER_EXISTS: "Ya existe una cuenta con ese correo.",
  USERNAME_EXISTS: "Ya existe una cuenta con ese usuario.",
  DUPLICATE_EMAIL: "Ya existe una cuenta con ese correo.",
  WEAK_PASSWORD: "La contraseña debe tener al menos 8 caracteres.",

  // General errors
  USER_NOT_FOUND: "Usuario no encontrado.",
  VALIDATION_ERROR: "Error de validación en los datos enviados.",
  MISSING_FIELD: "Campo requerido faltante.",
  INVALID_FORMAT: "Formato de datos inválido.",
  INTERNAL_ERROR: "Error interno del servidor.",

  // P0-FIX: Rate limiting errors
  RATE_LIMITED: "Demasiados intentos. Intenta de nuevo en unos minutos.",
  TOO_MANY_REQUESTS: "Demasiados intentos. Intenta de nuevo en unos minutos.",

  // P0-FIX: Network errors
  NETWORK_ERROR: "Sin conexión. Verifica tu red e intenta nuevamente.",
  ERR_NETWORK: "Sin conexión. Verifica tu red e intenta nuevamente.",
};

function computeExpiry(expiresInSeconds: number): number {
  return Date.now() + expiresInSeconds * 1000;
}

function mapApiError(error: unknown): AuthErrorInfo {
  const fallback: AuthErrorInfo = {
    code: "UNKNOWN",
    message: "Ocurrió un error. Intenta de nuevo.",
  };

  if (typeof error === "string") {
    return { ...fallback, message: error };
  }

  if (error && typeof error === "object" && "response" in error) {
    const axiosError = error as any;

    // P0-FIX: Detect rate limiting (429)
    if (axiosError.response?.status === 429) {
      return {
        code: "RATE_LIMITED",
        message: ERROR_MESSAGES.RATE_LIMITED,
      };
    }

    // P0-FIX: Detect authentication errors (401)
    if (axiosError.response?.status === 401) {
      const responseData = axiosError.response?.data ?? {};
      const errorDetail =
        responseData?.error ?? responseData?.detail ?? responseData;
      const code =
        errorDetail?.code ?? responseData?.code ?? "INVALID_CREDENTIALS";
      const field = errorDetail?.field ?? responseData?.field;

      return {
        code,
        message: ERROR_MESSAGES[code] || "Correo o contraseña incorrectos.",
        field,
      };
    }

    const responseData = axiosError.response?.data ?? {};

    // Handle new structured error response format
    const errorDetail =
      responseData?.error ?? responseData?.detail ?? responseData;

    const code = errorDetail?.code ?? responseData?.code;
    const field = errorDetail?.field ?? responseData?.field;
    const detailMessage =
      typeof errorDetail?.message === "string"
        ? errorDetail.message
        : undefined;
    const mappedMessage = code ? ERROR_MESSAGES[code] : undefined;

    return {
      code: code ?? "UNKNOWN",
      message:
        mappedMessage ||
        detailMessage ||
        axiosError.message ||
        fallback.message,
      field,
    };
  }

  // P0-FIX: Detect network errors (no response from server)
  if (error && typeof error === "object") {
    const anyError = error as any;

    // Axios network error indicators
    if (
      anyError.code === "ERR_NETWORK" ||
      anyError.message?.includes("Network Error")
    ) {
      return {
        code: "NETWORK_ERROR",
        message: ERROR_MESSAGES.NETWORK_ERROR,
      };
    }

    // Fetch API network error indicators
    if (
      anyError.message?.includes("Failed to fetch") ||
      anyError.message?.includes("NetworkError")
    ) {
      return {
        code: "NETWORK_ERROR",
        message: ERROR_MESSAGES.NETWORK_ERROR,
      };
    }
  }

  if (error instanceof Error) {
    return { ...fallback, message: error.message };
  }

  return fallback;
}

const initialHydrated = false;

export const useAuthStore = createWithEqualityFn<AuthStore>()(
  devtools(
    persist(
      (set, get) => ({
        user: null,
        accessToken: null,
        refreshToken: null,
        expiresAt: null,
        status: "idle",
        error: null,
        isHydrated: initialHydrated,
        intendedPath: null,

        async login(credentials) {
          set({ status: "loading", error: null });
          try {
            const authResponse = await apiClient.login(credentials);
            applyAuthResponse(set, authResponse);
            set({ status: "idle" });
            return true;
          } catch (error) {
            const apiError = mapApiError(error);
            set({ status: "error", error: apiError });
            return false;
          }
        },

        async register(payload) {
          set({ status: "loading", error: null });
          try {
            const authResponse = await apiClient.register(payload);
            applyAuthResponse(set, authResponse);
            set({ status: "idle" });
            return true;
          } catch (error) {
            const apiError = mapApiError(error);
            set({ status: "error", error: apiError });
            return false;
          }
        },

        async logout(opts = {}) {
          const { reason, redirectPath } = opts;

          logDebug("Logout initiated", { reason, redirectPath });

          try {
            // Call backend logout endpoint to blacklist tokens
            const currentRefreshToken = get().refreshToken;
            if (currentRefreshToken) {
              await apiClient.logout();
            }
          } catch (error) {
            // Even if backend call fails, proceed with client cleanup
            logWarn("Logout backend call failed:", mapApiError(error).message);
          }

          // Save current path if we want to return after login
          const currentPath =
            typeof window !== "undefined"
              ? window.location.pathname + window.location.search
              : null;
          const pathToSave =
            redirectPath ||
            (currentPath && currentPath !== "/login" ? currentPath : null);

          // Clear local state
          set({
            user: null,
            accessToken: null,
            refreshToken: null,
            expiresAt: null,
            status: "idle",
            error: null,
            intendedPath: pathToSave,
          });

          // Clear localStorage
          get().clearCache();

          // ISSUE-019: Clear all stores to prevent orphaned optimistic conversations
          try {
            useChatStore.getState().clearAllData();
            useHistoryStore.getState().clearAllData();
            useFilesStore.getState().clearAll();
            logDebug("All stores cleared on logout");
          } catch (error) {
            logWarn("Failed to clear some stores on logout", error);
          }

          // Show toast notification if this is due to expiration
          if (typeof window !== "undefined") {
            if (reason && reason.includes("expired")) {
              // Dispatch custom event for toast notification
              window.dispatchEvent(
                new CustomEvent("auth:session-expired", {
                  detail: {
                    message: "Tu sesión ha expirado. Inicia sesión nuevamente.",
                    reason,
                  },
                }),
              );
            }

            // Redirect to login with reason query param
            const loginUrl = reason
              ? `/login?reason=${encodeURIComponent(reason)}`
              : "/login";
            window.location.href = loginUrl;
          }
        },

        async refreshSession() {
          const state = get();
          if (!state.refreshToken) {
            return false;
          }

          if (state.expiresAt && state.expiresAt - Date.now() > ONE_MINUTE_MS) {
            // Token is still fresh enough
            return true;
          }

          try {
            const refreshed: RefreshTokenResponse =
              await apiClient.refreshAccessToken(state.refreshToken);
            set({
              accessToken: refreshed.accessToken,
              expiresAt: computeExpiry(refreshed.expiresIn),
              status: "idle",
              error: null,
            });
            return true;
          } catch (error) {
            const apiError = mapApiError(error);
            logWarn("Failed to refresh session", apiError.message);
            set({ status: "error", error: apiError });
            return false;
          }
        },

        async fetchProfile() {
          try {
            const profile = await apiClient.getCurrentUser();
            set({ user: profile });
          } catch (error) {
            const apiError = mapApiError(error);
            logWarn("Failed to fetch user profile", apiError.message);
            if (
              apiError.code === "INVALID_TOKEN" ||
              apiError.code === "BAD_CREDENTIALS"
            ) {
              get().logout();
            }
          }
        },

        clearError() {
          set({ error: null, status: "idle" });
        },

        clearCache() {
          // Clear all auth-related localStorage
          localStorage.removeItem(AUTH_STORAGE_KEY);
          localStorage.removeItem("demo-notice-dismissed");
          // Reset state to initial
          get().resetAuthState();
          logDebug("Auth cache cleared");
        },

        resetAuthState() {
          set({
            user: null,
            accessToken: null,
            refreshToken: null,
            expiresAt: null,
            status: "idle",
            error: null,
          });
        },

        isAuthenticated() {
          const state = get();
          return Boolean(state.accessToken && state.user);
        },

        setIntendedPath(path) {
          set({ intendedPath: path });
        },

        updateTokens(accessToken, expiresIn) {
          set({
            accessToken,
            expiresAt: computeExpiry(expiresIn),
            status: "idle",
            error: null,
          });
          logDebug("Tokens updated", { expiresIn });
        },

        setHydrated(isHydrated) {
          set({ isHydrated, status: "idle" });
        },
      }),
      {
        name: AUTH_STORAGE_KEY,
        storage: createJSONStorage(() => localStorage),
        version: 1, // Version for cache invalidation
        migrate: (persistedState: any, version: number) => {
          // Simple migration - if version is less than 1, clear the state
          if (version < 1) {
            return {
              user: null,
              accessToken: null,
              refreshToken: null,
              expiresAt: null,
            };
          }
          return persistedState;
        },
        partialize: (state) => ({
          user: state.user,
          accessToken: state.accessToken,
          refreshToken: state.refreshToken,
          expiresAt: state.expiresAt,
        }),
        onRehydrateStorage: () => (state, error) => {
          if (error) {
            logError("Auth store rehydration error", error);
            localStorage.removeItem(AUTH_STORAGE_KEY);
            setTimeout(() => {
              state?.setHydrated?.(true);
            }, 0);
            return;
          }

          // Check if access token is expired
          if (state?.expiresAt && state.expiresAt <= Date.now()) {
            // If refresh token exists, attempt silent renewal
            if (state?.refreshToken) {
              logWarn(
                "Stored auth token expired, attempting refresh on rehydration",
              );
              (async () => {
                try {
                  const response = await fetch("/api/auth/refresh", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                      refresh_token: state.refreshToken,
                    }),
                  });

                  if (response.ok) {
                    const data = await response.json();
                    if (data.access_token && data.expires_in) {
                      state.updateTokens(data.access_token, data.expires_in);
                      logDebug(
                        "Session restored via refresh token on rehydration",
                      );
                      state.setHydrated(true);
                      return;
                    }
                  }
                } catch (err) {
                  logWarn("Refresh on rehydration failed", err);
                }

                // Refresh failed — clear everything
                logWarn("Refresh failed on rehydration, clearing session");
                localStorage.removeItem(AUTH_STORAGE_KEY);
                state.resetAuthState();
                state.setHydrated(true);
              })();
              return; // Async block handles setHydrated
            }

            // No refresh token available — clear immediately
            logWarn("Stored auth token expired, no refresh token, clearing");
            localStorage.removeItem(AUTH_STORAGE_KEY);
            state?.resetAuthState?.();
          }

          // Set hydration state after rehydration finishes
          setTimeout(() => {
            state?.setHydrated?.(true);
          }, 0);
        },
      },
    ),
  ),
);

function applyAuthResponse(
  set: (fn: (state: AuthStore) => Partial<AuthStore>) => void,
  authResponse: AuthTokens,
) {
  set(() => ({
    user: authResponse.user,
    accessToken: authResponse.accessToken,
    refreshToken: authResponse.refreshToken,
    expiresAt: computeExpiry(authResponse.expiresIn),
    error: null,
  }));
}

// Initialize auth token getter and logout handler after store creation
setTimeout(() => {
  setAuthTokenGetter(() => {
    try {
      const state = useAuthStore.getState();
      return state.accessToken;
    } catch (error) {
      logWarn("Failed to get auth token from store", error);
      return null;
    }
  });

  setLogoutHandler((opts) => {
    try {
      const state = useAuthStore.getState();
      state.logout(opts);
    } catch (error) {
      logError("Failed to trigger logout from handler", error);
    }
  });

  logDebug("Auth token getter and logout handler initialized");

  // Initialize auth client with store callbacks
  if (typeof window !== "undefined") {
    // Dynamic import to avoid circular dependencies
    import("./auth-client")
      .then(({ initAuthClient }) => {
        initAuthClient(
          // Get auth state
          () => {
            const state = useAuthStore.getState();
            return {
              accessToken: state.accessToken || undefined,
              refreshToken: state.refreshToken || undefined,
              expiresAt: state.expiresAt || undefined,
            };
          },
          // Update tokens callback
          (accessToken: string, expiresIn: number) => {
            useAuthStore.getState().updateTokens(accessToken, expiresIn);
          },
          // Logout callback
          (opts) => {
            useAuthStore.getState().logout(opts);
          },
        );
        logDebug("AuthClient initialized with store callbacks");
      })
      .catch((error) => {
        logError("Failed to initialize AuthClient", error);
      });

    // Initialize WebSocket auth
    import("./auth-websocket")
      .then(({ initWebSocketAuth }) => {
        initWebSocketAuth(
          // Get auth state
          () => {
            const state = useAuthStore.getState();
            return {
              accessToken: state.accessToken || undefined,
              refreshToken: state.refreshToken || undefined,
              expiresAt: state.expiresAt || undefined,
            };
          },
          // Logout callback
          (opts) => {
            useAuthStore.getState().logout(opts);
          },
        );
        logDebug("WebSocket auth initialized with store callbacks");
      })
      .catch((error) => {
        logError("Failed to initialize WebSocket auth", error);
      });
  }
}, 0);
