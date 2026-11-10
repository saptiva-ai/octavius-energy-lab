/**
 * Critical tests for auth-client.ts
 *
 * Coverage goals:
 * - initAuthClient: Initialization and callback storage
 * - isTokenExpiringSoon: Expiration detection with 30s skew
 * - tryRefreshOnce: Single-flight refresh pattern
 * - handleExpiration: Logout and error throwing
 * - authFetch: Proactive/reactive token handling, public endpoints, retry logic
 * - authClient wrappers: HTTP method shortcuts
 */

import { jest } from "@jest/globals";
import {
  authFetch,
  authClient,
  initAuthClient,
  __resetAuthClientForTesting,
} from "../auth-client";

// Mock fetch globally
global.fetch = jest.fn() as jest.MockedFunction<typeof fetch>;

// Mock logger
jest.mock("../logger", () => ({
  logDebug: jest.fn(),
  logWarn: jest.fn(),
  logError: jest.fn(),
}));

describe("auth-client", () => {
  let mockGetAuthState: jest.MockedFunction<() => any>;
  let mockUpdateTokens: jest.MockedFunction<
    (token: string, expiresIn: number) => void
  >;
  let mockLogout: jest.MockedFunction<(opts: any) => void>;

  beforeEach(() => {
    jest.clearAllMocks();
    (global.fetch as jest.MockedFunction<typeof fetch>).mockClear();
    __resetAuthClientForTesting(); // Reset module state

    mockGetAuthState = jest.fn();
    mockUpdateTokens = jest.fn();
    mockLogout = jest.fn();
  });

  describe("initAuthClient", () => {
    it("initializes with provided callbacks", () => {
      expect(() => {
        initAuthClient(mockGetAuthState, mockUpdateTokens, mockLogout);
      }).not.toThrow();
    });

    it("throws error when authFetch is called before initialization", async () => {
      // Don't initialize
      await expect(
        authFetch("https://api.example.com/protected"),
      ).rejects.toThrow("AuthClient not initialized");
    });
  });

  describe("authFetch - Public Endpoints", () => {
    beforeEach(() => {
      initAuthClient(mockGetAuthState, mockUpdateTokens, mockLogout);
    });

    const publicEndpoints = [
      "/api/auth/login",
      "/api/auth/register",
      "/api/auth/refresh",
      "/api/health",
      "/api/models",
      "/api/feature-flags",
    ];

    publicEndpoints.forEach((endpoint) => {
      it(`bypasses auth for public endpoint: ${endpoint}`, async () => {
        const mockResponse = new Response(JSON.stringify({ success: true }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });

        (
          global.fetch as jest.MockedFunction<typeof fetch>
        ).mockResolvedValueOnce(mockResponse);

        await authFetch(endpoint);

        // Should call fetch without checking auth state
        expect(global.fetch).toHaveBeenCalledWith(endpoint, undefined);
        expect(mockGetAuthState).not.toHaveBeenCalled();
      });
    });

    it("bypasses auth when skipAuth option is true", async () => {
      const mockResponse = new Response("OK", { status: 200 });
      (global.fetch as jest.MockedFunction<typeof fetch>).mockResolvedValueOnce(
        mockResponse,
      );

      await authFetch("https://api.example.com/some-endpoint", undefined, {
        skipAuth: true,
      });

      expect(global.fetch).toHaveBeenCalledWith(
        "https://api.example.com/some-endpoint",
        undefined,
      );
      expect(mockGetAuthState).not.toHaveBeenCalled();
    });
  });

  describe("authFetch - Token Expiration (Proactive)", () => {
    beforeEach(() => {
      initAuthClient(mockGetAuthState, mockUpdateTokens, mockLogout);
    });

    it("triggers logout when no access token exists", async () => {
      mockGetAuthState.mockReturnValue({
        accessToken: undefined,
        refreshToken: undefined,
        expiresAt: undefined,
      });

      // Mock window.location.pathname
      Object.defineProperty(window, "location", {
        value: { pathname: "/dashboard" },
        writable: true,
      });

      await expect(
        authFetch("https://api.example.com/protected"),
      ).rejects.toThrow("Session expired");

      expect(mockLogout).toHaveBeenCalledWith({
        reason: "expired_proactive",
        redirectPath: "/dashboard",
      });
    });

    it("attempts refresh when token is expiring soon (within 30s)", async () => {
      const now = Math.floor(Date.now() / 1000);
      const expiresAt = (now + 20) * 1000; // Expires in 20s (< 30s threshold)
      const futureExpiresAt = (now + 3600) * 1000;

      // Mock getAuthState to return expiring token first, then updated token after refresh
      let callCount = 0;
      mockGetAuthState.mockImplementation(() => {
        callCount++;
        if (callCount <= 2) {
          return {
            accessToken: "old-token",
            refreshToken: "refresh-token",
            expiresAt,
          };
        }
        return {
          accessToken: "new-token",
          refreshToken: "refresh-token",
          expiresAt: futureExpiresAt,
        };
      });

      // Mock successful refresh
      const refreshResponse = new Response(
        JSON.stringify({ access_token: "new-token", expires_in: 3600 }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );

      const protectedResponse = new Response(
        JSON.stringify({ data: "protected data" }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );

      (global.fetch as jest.MockedFunction<typeof fetch>)
        .mockResolvedValueOnce(refreshResponse)
        .mockResolvedValueOnce(protectedResponse);

      const response = await authFetch("https://api.example.com/protected");

      expect(response.status).toBe(200);
      expect(mockUpdateTokens).toHaveBeenCalledWith("new-token", 3600);
      expect(global.fetch).toHaveBeenCalledWith("/api/auth/refresh", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: "refresh-token" }),
      });
    });

    it("triggers logout when refresh fails proactively", async () => {
      const now = Math.floor(Date.now() / 1000);
      const expiresAt = (now + 20) * 1000;

      mockGetAuthState.mockReturnValue({
        accessToken: "old-token",
        refreshToken: "refresh-token",
        expiresAt,
      });

      // Mock failed refresh
      const refreshResponse = new Response(
        JSON.stringify({ error: "invalid_token" }),
        { status: 401, headers: { "Content-Type": "application/json" } },
      );

      (global.fetch as jest.MockedFunction<typeof fetch>).mockResolvedValueOnce(
        refreshResponse,
      );

      Object.defineProperty(window, "location", {
        value: { pathname: "/settings" },
        writable: true,
      });

      await expect(
        authFetch("https://api.example.com/protected"),
      ).rejects.toThrow("Session expired");

      expect(mockLogout).toHaveBeenCalledWith({
        reason: "expired_proactive",
        redirectPath: "/settings",
      });
    });
  });

  describe("authFetch - 401 Handling (Reactive)", () => {
    beforeEach(() => {
      initAuthClient(mockGetAuthState, mockUpdateTokens, mockLogout);
    });

    it("retries request after successful refresh on 401 with token_expired", async () => {
      const now = Math.floor(Date.now() / 1000);
      const expiresAt = (now + 3600) * 1000; // Valid token (1 hour in future)

      let callCount = 0;
      mockGetAuthState.mockImplementation(() => {
        callCount++;
        // First 2 calls: before and during first request
        if (callCount <= 2) {
          return {
            accessToken: "valid-token",
            refreshToken: "refresh-token",
            expiresAt,
          };
        }
        // After refresh: return new token
        return {
          accessToken: "new-token",
          refreshToken: "refresh-token",
          expiresAt: (now + 7200) * 1000,
        };
      });

      // First request returns 401
      const unauthorizedResponse = new Response(
        JSON.stringify({ code: "token_expired", message: "Token has expired" }),
        { status: 401, headers: { "Content-Type": "application/json" } },
      );

      // Refresh succeeds
      const refreshResponse = new Response(
        JSON.stringify({ access_token: "new-token", expires_in: 3600 }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );

      // Retry succeeds
      const successResponse = new Response(
        JSON.stringify({ data: "success" }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );

      (global.fetch as jest.MockedFunction<typeof fetch>)
        .mockResolvedValueOnce(unauthorizedResponse)
        .mockResolvedValueOnce(refreshResponse)
        .mockResolvedValueOnce(successResponse);

      const response = await authFetch("https://api.example.com/protected");

      expect(response.status).toBe(200);
      expect(mockUpdateTokens).toHaveBeenCalledWith("new-token", 3600);
      // Should have called fetch 3 times: original request, refresh, retry
      expect(global.fetch).toHaveBeenCalledTimes(3);
    });

    it("triggers logout when 401 occurs and refresh fails", async () => {
      const now = Math.floor(Date.now() / 1000);
      const expiresAt = (now + 3600) * 1000;

      mockGetAuthState.mockReturnValue({
        accessToken: "valid-token",
        refreshToken: "refresh-token",
        expiresAt,
      });

      // First request returns 401
      const unauthorizedResponse = new Response(
        JSON.stringify({ code: "token_invalid", message: "Token is invalid" }),
        { status: 401, headers: { "Content-Type": "application/json" } },
      );

      // Refresh fails
      const refreshFailedResponse = new Response(
        JSON.stringify({ error: "refresh_failed" }),
        { status: 401, headers: { "Content-Type": "application/json" } },
      );

      (global.fetch as jest.MockedFunction<typeof fetch>)
        .mockResolvedValueOnce(unauthorizedResponse)
        .mockResolvedValueOnce(refreshFailedResponse);

      // Mock window.location BEFORE the call
      delete (global as any).window;
      (global as any).window = { location: { pathname: "/profile" } };

      await expect(
        authFetch("https://api.example.com/protected"),
      ).rejects.toThrow("Session expired");

      expect(mockLogout).toHaveBeenCalledWith({
        reason: "expired_reactive",
        redirectPath: "/profile",
      });
    });

    it("returns 401 response when error code is not expiration-related", async () => {
      const now = Math.floor(Date.now() / 1000);
      const expiresAt = (now + 7200) * 1000; // 2 hours in future (definitely not expiring)

      mockGetAuthState.mockReturnValue({
        accessToken: "valid-token",
        refreshToken: "refresh-token",
        expiresAt,
      });

      // 401 with non-expiration error code
      const forbiddenResponse = new Response(
        JSON.stringify({
          code: "insufficient_permissions",
          message: "Access denied",
        }),
        { status: 401, headers: { "Content-Type": "application/json" } },
      );

      (global.fetch as jest.MockedFunction<typeof fetch>).mockResolvedValueOnce(
        forbiddenResponse,
      );

      const response = await authFetch("https://api.example.com/protected");

      // Should return the 401 without attempting refresh
      expect(response.status).toBe(401);
      expect(mockUpdateTokens).not.toHaveBeenCalled();
      expect(mockLogout).not.toHaveBeenCalled();
    });

    it("does not retry when retryOnExpired is false", async () => {
      const now = Math.floor(Date.now() / 1000);
      const expiresAt = (now + 7200) * 1000; // 2 hours in future

      mockGetAuthState.mockReturnValue({
        accessToken: "valid-token",
        refreshToken: "refresh-token",
        expiresAt,
      });

      const unauthorizedResponse = new Response(
        JSON.stringify({ code: "token_expired", message: "Token expired" }),
        { status: 401, headers: { "Content-Type": "application/json" } },
      );

      (global.fetch as jest.MockedFunction<typeof fetch>).mockResolvedValueOnce(
        unauthorizedResponse,
      );

      // Mock window.location
      delete (global as any).window;
      (global as any).window = { location: { pathname: "/test" } };

      // Explicitly disable retry
      await expect(
        authFetch("https://api.example.com/protected", undefined, {
          retryOnExpired: false,
        }),
      ).rejects.toThrow("Session expired");

      // Should not attempt refresh (only 1 call for the protected endpoint, no /api/auth/refresh)
      expect(global.fetch).toHaveBeenCalledTimes(1);
      expect(mockLogout).toHaveBeenCalled();
    });
  });

  describe("authFetch - Single-Flight Refresh Pattern", () => {
    beforeEach(() => {
      initAuthClient(mockGetAuthState, mockUpdateTokens, mockLogout);
    });

    it("reuses in-flight refresh for concurrent requests", async () => {
      const now = Math.floor(Date.now() / 1000);
      const expiresAt = (now + 20) * 1000; // Expiring soon
      const futureExpiresAt = (now + 3600) * 1000;

      let callCount = 0;
      mockGetAuthState.mockImplementation(() => {
        callCount++;
        if (callCount <= 4) {
          // Initial checks for both requests
          return {
            accessToken: "old-token",
            refreshToken: "refresh-token",
            expiresAt,
          };
        }
        // After refresh
        return {
          accessToken: "new-token",
          refreshToken: "refresh-token",
          expiresAt: futureExpiresAt,
        };
      });

      // Mock slow refresh response
      const refreshResponse = new Response(
        JSON.stringify({ access_token: "new-token", expires_in: 3600 }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );

      const protectedResponse1 = new Response(
        JSON.stringify({ data: "data1" }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );

      const protectedResponse2 = new Response(
        JSON.stringify({ data: "data2" }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );

      (global.fetch as jest.MockedFunction<typeof fetch>)
        .mockResolvedValueOnce(refreshResponse)
        .mockResolvedValueOnce(protectedResponse1)
        .mockResolvedValueOnce(protectedResponse2);

      // Make two concurrent requests
      const [response1, response2] = await Promise.all([
        authFetch("https://api.example.com/endpoint1"),
        authFetch("https://api.example.com/endpoint2"),
      ]);

      expect(response1.status).toBe(200);
      expect(response2.status).toBe(200);

      // Refresh should only be called once
      expect(global.fetch).toHaveBeenCalledWith(
        "/api/auth/refresh",
        expect.any(Object),
      );
      const refreshCalls = (
        global.fetch as jest.MockedFunction<typeof fetch>
      ).mock.calls.filter((call) => call[0] === "/api/auth/refresh");
      expect(refreshCalls).toHaveLength(1);
    });
  });

  describe("authFetch - Request Headers", () => {
    beforeEach(() => {
      initAuthClient(mockGetAuthState, mockUpdateTokens, mockLogout);
    });

    it("adds Authorization and Content-Type headers to protected requests", async () => {
      const now = Math.floor(Date.now() / 1000);
      const expiresAt = (now + 3600) * 1000;

      mockGetAuthState.mockReturnValue({
        accessToken: "test-token",
        refreshToken: "refresh-token",
        expiresAt,
      });

      const mockResponse = new Response("OK", { status: 200 });
      (global.fetch as jest.MockedFunction<typeof fetch>).mockResolvedValueOnce(
        mockResponse,
      );

      await authFetch("https://api.example.com/protected", {
        method: "POST",
        headers: { "X-Custom-Header": "custom-value" },
      });

      const fetchCall = (global.fetch as jest.MockedFunction<typeof fetch>).mock
        .calls[0];
      const headers = fetchCall[1]?.headers as Headers;

      expect(headers.get("Authorization")).toBe("Bearer test-token");
      expect(headers.get("Content-Type")).toBe("application/json");
      expect(headers.get("X-Custom-Header")).toBe("custom-value");
    });
  });

  describe("authClient HTTP Method Wrappers", () => {
    beforeEach(() => {
      initAuthClient(mockGetAuthState, mockUpdateTokens, mockLogout);

      const now = Math.floor(Date.now() / 1000);
      const expiresAt = (now + 3600) * 1000;

      mockGetAuthState.mockReturnValue({
        accessToken: "test-token",
        refreshToken: "refresh-token",
        expiresAt,
      });
    });

    it("authClient.get sends GET request", async () => {
      const mockResponse = new Response(JSON.stringify({ data: "get" }), {
        status: 200,
      });
      (global.fetch as jest.MockedFunction<typeof fetch>).mockResolvedValueOnce(
        mockResponse,
      );

      await authClient.get("https://api.example.com/resource");

      const fetchCall = (global.fetch as jest.MockedFunction<typeof fetch>).mock
        .calls[0];
      expect(fetchCall[1]?.method).toBe("GET");
    });

    it("authClient.post sends POST request with body", async () => {
      const mockResponse = new Response(JSON.stringify({ id: 1 }), {
        status: 201,
      });
      (global.fetch as jest.MockedFunction<typeof fetch>).mockResolvedValueOnce(
        mockResponse,
      );

      await authClient.post("https://api.example.com/resource", {
        name: "Test",
      });

      const fetchCall = (global.fetch as jest.MockedFunction<typeof fetch>).mock
        .calls[0];
      expect(fetchCall[1]?.method).toBe("POST");
      expect(fetchCall[1]?.body).toBe(JSON.stringify({ name: "Test" }));
    });

    it("authClient.put sends PUT request with body", async () => {
      const mockResponse = new Response(JSON.stringify({ updated: true }), {
        status: 200,
      });
      (global.fetch as jest.MockedFunction<typeof fetch>).mockResolvedValueOnce(
        mockResponse,
      );

      await authClient.put("https://api.example.com/resource/1", {
        name: "Updated",
      });

      const fetchCall = (global.fetch as jest.MockedFunction<typeof fetch>).mock
        .calls[0];
      expect(fetchCall[1]?.method).toBe("PUT");
      expect(fetchCall[1]?.body).toBe(JSON.stringify({ name: "Updated" }));
    });

    it("authClient.patch sends PATCH request with body", async () => {
      const mockResponse = new Response(JSON.stringify({ patched: true }), {
        status: 200,
      });
      (global.fetch as jest.MockedFunction<typeof fetch>).mockResolvedValueOnce(
        mockResponse,
      );

      await authClient.patch("https://api.example.com/resource/1", {
        status: "active",
      });

      const fetchCall = (global.fetch as jest.MockedFunction<typeof fetch>).mock
        .calls[0];
      expect(fetchCall[1]?.method).toBe("PATCH");
      expect(fetchCall[1]?.body).toBe(JSON.stringify({ status: "active" }));
    });

    it("authClient.delete sends DELETE request", async () => {
      const mockResponse = new Response(null, { status: 204 });
      (global.fetch as jest.MockedFunction<typeof fetch>).mockResolvedValueOnce(
        mockResponse,
      );

      await authClient.delete("https://api.example.com/resource/1");

      const fetchCall = (global.fetch as jest.MockedFunction<typeof fetch>).mock
        .calls[0];
      expect(fetchCall[1]?.method).toBe("DELETE");
    });
  });

  describe("Edge Cases", () => {
    beforeEach(() => {
      initAuthClient(mockGetAuthState, mockUpdateTokens, mockLogout);
    });

    it("handles invalid refresh response gracefully", async () => {
      const now = Math.floor(Date.now() / 1000);
      const expiresAt = (now + 20) * 1000;

      mockGetAuthState.mockReturnValue({
        accessToken: "old-token",
        refreshToken: "refresh-token",
        expiresAt,
      });

      // Refresh returns invalid data (missing access_token or expires_in)
      const invalidRefreshResponse = new Response(
        JSON.stringify({ some_other_field: "value" }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );

      (global.fetch as jest.MockedFunction<typeof fetch>).mockResolvedValueOnce(
        invalidRefreshResponse,
      );

      Object.defineProperty(window, "location", {
        value: { pathname: "/test" },
        writable: true,
      });

      await expect(
        authFetch("https://api.example.com/protected"),
      ).rejects.toThrow("Session expired");

      expect(mockLogout).toHaveBeenCalled();
    });

    it("handles non-JSON error responses", async () => {
      const now = Math.floor(Date.now() / 1000);
      const expiresAt = (now + 7200) * 1000; // 2 hours in future

      mockGetAuthState.mockReturnValue({
        accessToken: "valid-token",
        refreshToken: "refresh-token",
        expiresAt,
      });

      // 401 with HTML error page (not JSON)
      const htmlResponse = new Response("<html>Error</html>", {
        status: 401,
        headers: { "Content-Type": "text/html" },
      });

      (global.fetch as jest.MockedFunction<typeof fetch>).mockResolvedValueOnce(
        htmlResponse,
      );

      const response = await authFetch("https://api.example.com/protected");

      // Should return response without crashing (no error code means no retry)
      expect(response.status).toBe(401);
    });

    it("handles missing expiresAt by treating as expired", async () => {
      const now = Math.floor(Date.now() / 1000);
      const futureExpiresAt = (now + 3600) * 1000;

      let callCount = 0;
      mockGetAuthState.mockImplementation(() => {
        callCount++;
        if (callCount <= 2) {
          return {
            accessToken: "token",
            refreshToken: "refresh-token",
            expiresAt: undefined, // No expiration time
          };
        }
        return {
          accessToken: "new-token",
          refreshToken: "refresh-token",
          expiresAt: futureExpiresAt,
        };
      });

      const refreshResponse = new Response(
        JSON.stringify({ access_token: "new-token", expires_in: 3600 }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );

      const protectedResponse = new Response(
        JSON.stringify({ data: "success" }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );

      (global.fetch as jest.MockedFunction<typeof fetch>)
        .mockResolvedValueOnce(refreshResponse)
        .mockResolvedValueOnce(protectedResponse);

      await authFetch("https://api.example.com/protected");

      // Should attempt refresh since expiresAt is missing
      expect(global.fetch).toHaveBeenCalledWith(
        "/api/auth/refresh",
        expect.any(Object),
      );
    });
  });
});
