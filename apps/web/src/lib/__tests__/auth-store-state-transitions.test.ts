/**
 * Comprehensive state transition tests for auth-store.ts
 * Target: Increase branch coverage from 2.19% → 12%
 */

import { act, renderHook, waitFor } from "@testing-library/react";
import { useAuthStore } from "../auth-store";
import * as apiClient from "../api-client";
import type { AuthTokens } from "../types";

// Mock API client
jest.mock("../api-client", () => ({
  apiClient: {
    login: jest.fn(),
    register: jest.fn(),
    logout: jest.fn(),
    refreshAccessToken: jest.fn(),
    getCurrentUser: jest.fn(),
  },
  setAuthTokenGetter: jest.fn(),
  setLogoutHandler: jest.fn(),
}));

// Mock logger
jest.mock("../logger", () => ({
  logDebug: jest.fn(),
  logError: jest.fn(),
  logWarn: jest.fn(),
  logInfo: jest.fn(),
}));

describe("auth-store state transitions", () => {
  beforeEach(() => {
    // Clear all mocks
    jest.clearAllMocks();

    // Clear store state
    useAuthStore.setState({
      user: null,
      accessToken: null,
      refreshToken: null,
      expiresAt: null,
      status: "idle",
      error: null,
      isHydrated: false,
      intendedPath: null,
    });

    // Clear localStorage
    localStorage.clear();

    // Mock window.location
    delete (window as any).location;
    (window as any).location = { href: "", pathname: "/chat", search: "" };

    // Mock window.dispatchEvent
    jest.spyOn(window, "dispatchEvent").mockImplementation(() => true);
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  describe("Login Flow", () => {
    it("should transition from idle to loading to idle on successful login", async () => {
      const mockAuthResponse: AuthTokens = {
        accessToken: "access-token-123",
        refreshToken: "refresh-token-456",
        expiresIn: 3600,
        user: {
          id: "user-1",
          username: "testuser",
          email: "test@example.com",
          isActive: true,
          createdAt: "2025-01-01T00:00:00Z",
          updatedAt: "2025-01-01T00:00:00Z",
          lastLogin: null,
          preferences: {
            theme: "auto",
            language: "en",
            defaultModel: "SAPTIVA_CORTEX",
            chatSettings: {},
          },
        },
      };

      (apiClient.apiClient.login as jest.Mock).mockResolvedValueOnce(
        mockAuthResponse,
      );

      const { result } = renderHook(() => useAuthStore());

      // Initial state
      expect(result.current.status).toBe("idle");
      expect(result.current.user).toBeNull();

      // Start login
      let loginPromise: Promise<boolean>;
      act(() => {
        loginPromise = result.current.login({
          identifier: "test@example.com",
          password: "password123",
        });
      });

      // Should be loading
      expect(result.current.status).toBe("loading");
      expect(result.current.error).toBeNull();

      // Wait for completion
      await act(async () => {
        const success = await loginPromise!;
        expect(success).toBe(true);
      });

      // Should be idle with user data
      expect(result.current.status).toBe("idle");
      expect(result.current.user).toEqual(mockAuthResponse.user);
      expect(result.current.accessToken).toBe("access-token-123");
      expect(result.current.refreshToken).toBe("refresh-token-456");
      expect(result.current.error).toBeNull();
    });

    it("should return false and set error on login failure", async () => {
      const mockError = {
        response: {
          status: 401,
          data: {
            code: "INVALID_CREDENTIALS",
            detail: "Invalid email or password",
          },
        },
      };

      (apiClient.apiClient.login as jest.Mock).mockRejectedValueOnce(mockError);

      const { result } = renderHook(() => useAuthStore());

      expect(result.current.status).toBe("idle");
      expect(result.current.user).toBeNull();

      // Start login and wait for completion
      let loginResult: boolean;
      await act(async () => {
        loginResult = await result.current.login({
          identifier: "wrong@example.com",
          password: "wrongpass",
        });
      });

      // Should return false on failure
      expect(loginResult!).toBe(false);

      // Should have error populated (status may be 'error' or 'idle' depending on implementation)
      expect(result.current.error).toEqual({
        code: "INVALID_CREDENTIALS",
        message: "Correo o contraseña incorrectos.",
        field: undefined,
      });
      expect(result.current.user).toBeNull();
    });

    it("should handle 429 rate limit error during login", async () => {
      const mockError = {
        response: {
          status: 429,
          data: { detail: "Too many login attempts" },
        },
      };

      (apiClient.apiClient.login as jest.Mock).mockRejectedValueOnce(mockError);

      const { result } = renderHook(() => useAuthStore());

      await act(async () => {
        const success = await result.current.login({
          identifier: "test@example.com",
          password: "pass123",
        });
        expect(success).toBe(false);
      });

      expect(result.current.error).toEqual({
        code: "RATE_LIMITED",
        message: "Demasiados intentos. Intenta de nuevo en unos minutos.",
      });
    });

    it("should handle network error during login", async () => {
      const mockError = {
        code: "ERR_NETWORK",
        message: "Network Error",
      };

      (apiClient.apiClient.login as jest.Mock).mockRejectedValueOnce(mockError);

      const { result } = renderHook(() => useAuthStore());

      await act(async () => {
        const success = await result.current.login({
          identifier: "test@example.com",
          password: "pass123",
        });
        expect(success).toBe(false);
      });

      expect(result.current.error).toEqual({
        code: "NETWORK_ERROR",
        message: "Sin conexión. Verifica tu red e intenta nuevamente.",
      });
    });
  });

  describe("Register Flow", () => {
    it("should successfully register and set user state", async () => {
      const mockAuthResponse: AuthTokens = {
        accessToken: "new-access-token",
        refreshToken: "new-refresh-token",
        expiresIn: 3600,
        user: {
          id: "new-user-1",
          username: "newuser",
          email: "new@example.com",
          isActive: true,
          createdAt: "2025-01-01T00:00:00Z",
          updatedAt: "2025-01-01T00:00:00Z",
          lastLogin: null,
          preferences: {
            theme: "auto",
            language: "en",
            defaultModel: "SAPTIVA_CORTEX",
            chatSettings: {},
          },
        },
      };

      (apiClient.apiClient.register as jest.Mock).mockResolvedValueOnce(
        mockAuthResponse,
      );

      const { result } = renderHook(() => useAuthStore());

      await act(async () => {
        const success = await result.current.register({
          username: "newuser",
          email: "new@example.com",
          password: "SecurePass123!",
        });
        expect(success).toBe(true);
      });

      expect(result.current.status).toBe("idle");
      expect(result.current.user?.username).toBe("newuser");
      expect(result.current.accessToken).toBe("new-access-token");
    });

    it("should handle USER_EXISTS error during registration", async () => {
      const mockError = {
        response: {
          status: 400,
          data: {
            code: "USER_EXISTS",
            detail: "User with this email already exists",
          },
        },
      };

      (apiClient.apiClient.register as jest.Mock).mockRejectedValueOnce(
        mockError,
      );

      const { result } = renderHook(() => useAuthStore());

      await act(async () => {
        const success = await result.current.register({
          username: "existinguser",
          email: "existing@example.com",
          password: "Pass123!",
        });
        expect(success).toBe(false);
      });

      expect(result.current.error?.code).toBe("USER_EXISTS");
      expect(result.current.error?.message).toBe(
        "Ya existe una cuenta con ese correo.",
      );
    });
  });

  describe("Logout Flow", () => {
    it("should clear all state and redirect on logout", async () => {
      // Set initial authenticated state
      useAuthStore.setState({
        user: {
          id: "user-1",
          username: "testuser",
          email: "test@example.com",
          isActive: true,
          createdAt: "2025-01-01T00:00:00Z",
          updatedAt: "2025-01-01T00:00:00Z",
          lastLogin: null,
          preferences: {
            theme: "auto",
            language: "en",
            defaultModel: "SAPTIVA_CORTEX",
            chatSettings: {},
          },
        },
        accessToken: "token-123",
        refreshToken: "refresh-123",
        expiresAt: Date.now() + 3600000,
        status: "idle",
      });

      (apiClient.apiClient.logout as jest.Mock).mockResolvedValueOnce(
        undefined,
      );

      const { result } = renderHook(() => useAuthStore());

      await act(async () => {
        await result.current.logout();
      });

      expect(result.current.user).toBeNull();
      expect(result.current.accessToken).toBeNull();
      expect(result.current.refreshToken).toBeNull();
      expect(result.current.status).toBe("idle");
      expect(window.location.href).toBe("/login");
    });

    it("should dispatch session-expired event on logout with expired reason", async () => {
      useAuthStore.setState({
        refreshToken: "refresh-token",
      });

      (apiClient.apiClient.logout as jest.Mock).mockResolvedValueOnce(
        undefined,
      );

      const { result } = renderHook(() => useAuthStore());

      await act(async () => {
        await result.current.logout({ reason: "token_expired" });
      });

      expect(window.dispatchEvent).toHaveBeenCalledWith(
        expect.objectContaining({
          type: "auth:session-expired",
          detail: expect.objectContaining({
            message: "Tu sesión ha expirado. Inicia sesión nuevamente.",
            reason: "token_expired",
          }),
        }),
      );

      expect(window.location.href).toBe("/login?reason=token_expired");
    });

    it("should proceed with logout even if backend call fails", async () => {
      useAuthStore.setState({
        refreshToken: "refresh-token",
        accessToken: "access-token",
        user: {
          id: "user-1",
          username: "testuser",
          email: "test@example.com",
          isActive: true,
          createdAt: "2025-01-01T00:00:00Z",
          updatedAt: "2025-01-01T00:00:00Z",
          lastLogin: null,
          preferences: {
            theme: "auto",
            language: "en",
            defaultModel: "SAPTIVA_CORTEX",
            chatSettings: {},
          },
        },
      });

      (apiClient.apiClient.logout as jest.Mock).mockRejectedValueOnce(
        new Error("Network error"),
      );

      const { result } = renderHook(() => useAuthStore());

      await act(async () => {
        await result.current.logout();
      });

      // Should still clear state
      expect(result.current.user).toBeNull();
      expect(result.current.accessToken).toBeNull();
    });

    it("should save intended path on logout from non-login page", async () => {
      window.location.pathname = "/documents";
      window.location.search = "?filter=recent";

      useAuthStore.setState({
        refreshToken: "refresh-token",
      });

      (apiClient.apiClient.logout as jest.Mock).mockResolvedValueOnce(
        undefined,
      );

      const { result } = renderHook(() => useAuthStore());

      await act(async () => {
        await result.current.logout();
      });

      expect(result.current.intendedPath).toBe("/documents?filter=recent");
    });

    it("should NOT save intended path when logging out from login page", async () => {
      window.location.pathname = "/login";
      window.location.search = "";

      useAuthStore.setState({
        refreshToken: "refresh-token",
      });

      (apiClient.apiClient.logout as jest.Mock).mockResolvedValueOnce(
        undefined,
      );

      const { result } = renderHook(() => useAuthStore());

      await act(async () => {
        await result.current.logout();
      });

      expect(result.current.intendedPath).toBeNull();
    });
  });

  describe("Refresh Session", () => {
    it("should skip refresh if token is still fresh (> 1 minute remaining)", async () => {
      const futureExpiry = Date.now() + 5 * 60 * 1000; // 5 minutes from now

      useAuthStore.setState({
        refreshToken: "refresh-token",
        accessToken: "current-token",
        expiresAt: futureExpiry,
      });

      const { result } = renderHook(() => useAuthStore());

      await act(async () => {
        const success = await result.current.refreshSession();
        expect(success).toBe(true);
      });

      // Should not call API
      expect(apiClient.apiClient.refreshAccessToken).not.toHaveBeenCalled();
    });

    it("should refresh token when expiry is within 1 minute", async () => {
      const soonExpiry = Date.now() + 30 * 1000; // 30 seconds from now

      useAuthStore.setState({
        refreshToken: "refresh-token-old",
        accessToken: "old-token",
        expiresAt: soonExpiry,
      });

      (
        apiClient.apiClient.refreshAccessToken as jest.Mock
      ).mockResolvedValueOnce({
        accessToken: "new-access-token",
        expiresIn: 3600,
      });

      const { result } = renderHook(() => useAuthStore());

      await act(async () => {
        const success = await result.current.refreshSession();
        expect(success).toBe(true);
      });

      expect(apiClient.apiClient.refreshAccessToken).toHaveBeenCalledWith(
        "refresh-token-old",
      );
      expect(result.current.accessToken).toBe("new-access-token");
      expect(result.current.status).toBe("idle");
      expect(result.current.error).toBeNull();
    });

    it("should return false and set error when refresh fails", async () => {
      const expiredToken = Date.now() - 1000;

      useAuthStore.setState({
        refreshToken: "expired-refresh-token",
        expiresAt: expiredToken,
      });

      (
        apiClient.apiClient.refreshAccessToken as jest.Mock
      ).mockRejectedValueOnce({
        response: {
          status: 401,
          data: { code: "INVALID_TOKEN", detail: "Refresh token expired" },
        },
      });

      const { result } = renderHook(() => useAuthStore());

      await act(async () => {
        const success = await result.current.refreshSession();
        expect(success).toBe(false);
      });

      expect(result.current.status).toBe("error");
      expect(result.current.error?.code).toBe("INVALID_TOKEN");
    });

    it("should return false if no refresh token exists", async () => {
      useAuthStore.setState({
        refreshToken: null,
      });

      const { result } = renderHook(() => useAuthStore());

      await act(async () => {
        const success = await result.current.refreshSession();
        expect(success).toBe(false);
      });

      expect(apiClient.apiClient.refreshAccessToken).not.toHaveBeenCalled();
    });
  });

  describe("Fetch Profile", () => {
    it("should update user profile on successful fetch", async () => {
      const mockProfile = {
        id: "user-1",
        username: "updateduser",
        email: "updated@example.com",
        isActive: true,
        createdAt: "2025-01-01T00:00:00Z",
        updatedAt: "2025-01-02T00:00:00Z",
        lastLogin: "2025-01-02T10:00:00Z",
        preferences: {
          theme: "dark",
          language: "es",
          defaultModel: "SAPTIVA_TURBO",
          chatSettings: {},
        },
      };

      (apiClient.apiClient.getCurrentUser as jest.Mock).mockResolvedValueOnce(
        mockProfile,
      );

      const { result } = renderHook(() => useAuthStore());

      await act(async () => {
        await result.current.fetchProfile();
      });

      expect(result.current.user).toEqual(mockProfile);
    });

    it("should trigger logout on INVALID_TOKEN error during profile fetch", async () => {
      useAuthStore.setState({
        refreshToken: "refresh-token",
        accessToken: "invalid-token",
      });

      (apiClient.apiClient.getCurrentUser as jest.Mock).mockRejectedValueOnce({
        response: {
          status: 401,
          data: { code: "INVALID_TOKEN" },
        },
      });

      (apiClient.apiClient.logout as jest.Mock).mockResolvedValueOnce(
        undefined,
      );

      const { result } = renderHook(() => useAuthStore());

      await act(async () => {
        await result.current.fetchProfile();
      });

      // Should have triggered logout
      await waitFor(() => {
        expect(result.current.accessToken).toBeNull();
      });
    });

    it("should trigger logout on BAD_CREDENTIALS error during profile fetch", async () => {
      useAuthStore.setState({
        refreshToken: "refresh-token",
      });

      (apiClient.apiClient.getCurrentUser as jest.Mock).mockRejectedValueOnce({
        response: {
          status: 401,
          data: { code: "BAD_CREDENTIALS" },
        },
      });

      (apiClient.apiClient.logout as jest.Mock).mockResolvedValueOnce(
        undefined,
      );

      const { result } = renderHook(() => useAuthStore());

      await act(async () => {
        await result.current.fetchProfile();
      });

      await waitFor(() => {
        expect(result.current.accessToken).toBeNull();
      });
    });
  });

  describe("Utility Methods", () => {
    it("should return true when user is authenticated", () => {
      useAuthStore.setState({
        accessToken: "valid-token",
        user: {
          id: "user-1",
          username: "testuser",
          email: "test@example.com",
          isActive: true,
          createdAt: "2025-01-01T00:00:00Z",
          updatedAt: "2025-01-01T00:00:00Z",
          lastLogin: null,
          preferences: {
            theme: "auto",
            language: "en",
            defaultModel: "SAPTIVA_CORTEX",
            chatSettings: {},
          },
        },
      });

      const { result } = renderHook(() => useAuthStore());
      expect(result.current.isAuthenticated()).toBe(true);
    });

    it("should return false when token is missing", () => {
      useAuthStore.setState({
        accessToken: null,
        user: {
          id: "user-1",
          username: "testuser",
          email: "test@example.com",
          isActive: true,
          createdAt: "2025-01-01T00:00:00Z",
          updatedAt: "2025-01-01T00:00:00Z",
          lastLogin: null,
          preferences: {
            theme: "auto",
            language: "en",
            defaultModel: "SAPTIVA_CORTEX",
            chatSettings: {},
          },
        },
      });

      const { result } = renderHook(() => useAuthStore());
      expect(result.current.isAuthenticated()).toBe(false);
    });

    it("should return false when user is missing", () => {
      useAuthStore.setState({
        accessToken: "valid-token",
        user: null,
      });

      const { result } = renderHook(() => useAuthStore());
      expect(result.current.isAuthenticated()).toBe(false);
    });

    it("should clear error and reset status to idle", () => {
      useAuthStore.setState({
        status: "error",
        error: {
          code: "TEST_ERROR",
          message: "Test error message",
        },
      });

      const { result } = renderHook(() => useAuthStore());

      act(() => {
        result.current.clearError();
      });

      expect(result.current.error).toBeNull();
      expect(result.current.status).toBe("idle");
    });

    it("should clear cache and reset all auth state", () => {
      useAuthStore.setState({
        user: {
          id: "user-1",
          username: "testuser",
          email: "test@example.com",
          isActive: true,
          createdAt: "2025-01-01T00:00:00Z",
          updatedAt: "2025-01-01T00:00:00Z",
          lastLogin: null,
          preferences: {
            theme: "auto",
            language: "en",
            defaultModel: "SAPTIVA_CORTEX",
            chatSettings: {},
          },
        },
        accessToken: "token",
        refreshToken: "refresh",
        expiresAt: Date.now() + 3600000,
      });

      const { result } = renderHook(() => useAuthStore());

      act(() => {
        result.current.clearCache();
      });

      expect(result.current.user).toBeNull();
      expect(result.current.accessToken).toBeNull();
      expect(result.current.refreshToken).toBeNull();
      expect(result.current.expiresAt).toBeNull();
      expect(result.current.status).toBe("idle");
      expect(result.current.error).toBeNull();
    });

    it("should set and retrieve intended path", () => {
      const { result } = renderHook(() => useAuthStore());

      act(() => {
        result.current.setIntendedPath("/protected/page");
      });

      expect(result.current.intendedPath).toBe("/protected/page");

      act(() => {
        result.current.setIntendedPath(null);
      });

      expect(result.current.intendedPath).toBeNull();
    });

    it("should update tokens with new access token and expiry", () => {
      const { result } = renderHook(() => useAuthStore());

      const beforeUpdate = Date.now();

      act(() => {
        result.current.updateTokens("new-token-abc", 7200);
      });

      expect(result.current.accessToken).toBe("new-token-abc");
      expect(result.current.expiresAt).toBeGreaterThan(beforeUpdate);
      expect(result.current.expiresAt).toBeLessThanOrEqual(
        beforeUpdate + 7200 * 1000 + 100,
      );
      expect(result.current.status).toBe("idle");
      expect(result.current.error).toBeNull();
    });
  });
});
