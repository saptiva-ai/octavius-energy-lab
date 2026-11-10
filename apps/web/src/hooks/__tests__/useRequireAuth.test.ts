/**
 * Critical tests for useRequireAuth hook
 *
 * Coverage goals:
 * - Hydration check before operations
 * - Session refresh on mount with single-flight pattern
 * - Profile fetching when token exists but no user
 * - Redirect to login when no auth state
 * - Prevention of refresh loops with refs
 */

import { renderHook, waitFor } from "@testing-library/react";
import { useRequireAuth } from "../useRequireAuth";
import { useAuthStore } from "../../lib/auth-store";
import { useRouter } from "next/navigation";

// Mock next/navigation
jest.mock("next/navigation", () => ({
  useRouter: jest.fn(),
}));

// Mock auth-store
jest.mock("../../lib/auth-store", () => ({
  useAuthStore: jest.fn(),
}));

describe("useRequireAuth", () => {
  let mockRouter: {
    push: jest.Mock;
    replace: jest.Mock;
  };

  let mockRefreshSession: jest.Mock;
  let mockFetchProfile: jest.Mock;
  let mockLogout: jest.Mock;

  beforeEach(() => {
    jest.clearAllMocks();

    mockRouter = {
      push: jest.fn(),
      replace: jest.fn(),
    };

    mockRefreshSession = jest.fn();
    mockFetchProfile = jest.fn();
    mockLogout = jest.fn();

    (useRouter as jest.Mock).mockReturnValue(mockRouter);

    // Mock getState by default
    (useAuthStore as any).getState = jest.fn().mockReturnValue({
      accessToken: undefined,
      refreshToken: undefined,
      user: null,
    });
  });

  describe("Hydration Check", () => {
    it("waits for hydration before performing operations", () => {
      (useAuthStore as unknown as jest.Mock).mockImplementation((selector) =>
        selector({
          isHydrated: false,
          accessToken: "test-token",
          refreshToken: "refresh-token",
          user: { id: "1", email: "test@example.com" },
          refreshSession: mockRefreshSession,
          fetchProfile: mockFetchProfile,
          logout: mockLogout,
        }),
      );

      renderHook(() => useRequireAuth());

      // Should not call any auth methods while not hydrated
      expect(mockRefreshSession).not.toHaveBeenCalled();
      expect(mockFetchProfile).not.toHaveBeenCalled();
      expect(mockLogout).not.toHaveBeenCalled();
      expect(mockRouter.replace).not.toHaveBeenCalled();
    });

    it("proceeds with session check after hydration", async () => {
      mockRefreshSession.mockResolvedValue(true);

      (useAuthStore as unknown as jest.Mock).mockImplementation((selector) =>
        selector({
          isHydrated: true,
          accessToken: "test-token",
          refreshToken: "refresh-token",
          user: { id: "1", email: "test@example.com" },
          refreshSession: mockRefreshSession,
          fetchProfile: mockFetchProfile,
          logout: mockLogout,
        }),
      );

      renderHook(() => useRequireAuth());

      await waitFor(() => {
        expect(mockRefreshSession).toHaveBeenCalledTimes(1);
      });
    });
  });

  describe("Session Refresh on Mount", () => {
    it("attempts session refresh when hydrated and not checked", async () => {
      mockRefreshSession.mockResolvedValue(true);

      (useAuthStore as unknown as jest.Mock).mockImplementation((selector) =>
        selector({
          isHydrated: true,
          accessToken: "test-token",
          refreshToken: "refresh-token",
          user: { id: "1", email: "test@example.com" },
          refreshSession: mockRefreshSession,
          fetchProfile: mockFetchProfile,
          logout: mockLogout,
        }),
      );

      // Mock getState for the check inside ensureSession
      (useAuthStore as any).getState = jest.fn().mockReturnValue({
        accessToken: "test-token",
        user: { id: "1", email: "test@example.com" },
      });

      renderHook(() => useRequireAuth());

      await waitFor(() => {
        expect(mockRefreshSession).toHaveBeenCalledTimes(1);
      });
    });

    it("redirects to login when refresh fails and no access token", async () => {
      mockRefreshSession.mockResolvedValue(false);
      mockLogout.mockResolvedValue(undefined);

      (useAuthStore as unknown as jest.Mock).mockImplementation((selector) =>
        selector({
          isHydrated: true,
          accessToken: undefined,
          refreshToken: undefined,
          user: null,
          refreshSession: mockRefreshSession,
          fetchProfile: mockFetchProfile,
          logout: mockLogout,
        }),
      );

      // Mock getState to simulate no token after failed refresh
      (useAuthStore as any).getState = jest.fn().mockReturnValue({
        accessToken: undefined,
        user: null,
      });

      renderHook(() => useRequireAuth());

      await waitFor(() => {
        expect(mockRefreshSession).toHaveBeenCalledTimes(1);
        expect(mockLogout).toHaveBeenCalledWith({ reason: "session-expired" });
        expect(mockRouter.replace).toHaveBeenCalledWith(
          "/login?reason=session-expired",
        );
      });
    });

    it("fetches profile when token exists but user is missing", async () => {
      mockRefreshSession.mockResolvedValue(true);
      mockFetchProfile.mockResolvedValue(undefined);

      (useAuthStore as unknown as jest.Mock).mockImplementation((selector) =>
        selector({
          isHydrated: true,
          accessToken: "test-token",
          refreshToken: "refresh-token",
          user: null, // No user initially
          refreshSession: mockRefreshSession,
          fetchProfile: mockFetchProfile,
          logout: mockLogout,
        }),
      );

      // Mock getState to show token exists but no user after refresh
      (useAuthStore as any).getState = jest.fn().mockReturnValue({
        accessToken: "test-token",
        user: null,
      });

      renderHook(() => useRequireAuth());

      await waitFor(() => {
        expect(mockRefreshSession).toHaveBeenCalledTimes(1);
        expect(mockFetchProfile).toHaveBeenCalledTimes(1);
      });
    });

    it("does not fetch profile when user already exists", async () => {
      mockRefreshSession.mockResolvedValue(true);

      (useAuthStore as unknown as jest.Mock).mockImplementation((selector) =>
        selector({
          isHydrated: true,
          accessToken: "test-token",
          refreshToken: "refresh-token",
          user: { id: "1", email: "test@example.com" },
          refreshSession: mockRefreshSession,
          fetchProfile: mockFetchProfile,
          logout: mockLogout,
        }),
      );

      (useAuthStore as any).getState = jest.fn().mockReturnValue({
        accessToken: "test-token",
        user: { id: "1", email: "test@example.com" },
      });

      renderHook(() => useRequireAuth());

      await waitFor(() => {
        expect(mockRefreshSession).toHaveBeenCalledTimes(1);
      });

      // Should not fetch profile since user exists
      expect(mockFetchProfile).not.toHaveBeenCalled();
    });
  });

  describe("Single-Flight Pattern", () => {
    it("prevents multiple concurrent refresh attempts", async () => {
      mockRefreshSession.mockImplementation(
        () => new Promise((resolve) => setTimeout(() => resolve(true), 100)),
      );

      (useAuthStore as unknown as jest.Mock).mockImplementation((selector) =>
        selector({
          isHydrated: true,
          accessToken: "test-token",
          refreshToken: "refresh-token",
          user: { id: "1", email: "test@example.com" },
          refreshSession: mockRefreshSession,
          fetchProfile: mockFetchProfile,
          logout: mockLogout,
        }),
      );

      (useAuthStore as any).getState = jest.fn().mockReturnValue({
        accessToken: "test-token",
        user: { id: "1", email: "test@example.com" },
      });

      const { rerender } = renderHook(() => useRequireAuth());

      // Trigger re-renders during refresh
      rerender();
      rerender();
      rerender();

      await waitFor(() => {
        expect(mockRefreshSession).toHaveBeenCalledTimes(1);
      });

      // Despite multiple re-renders, refresh should only be called once
      expect(mockRefreshSession).toHaveBeenCalledTimes(1);
    });

    it("does not trigger session check on subsequent renders", async () => {
      mockRefreshSession.mockResolvedValue(true);

      (useAuthStore as unknown as jest.Mock).mockImplementation((selector) =>
        selector({
          isHydrated: true,
          accessToken: "test-token",
          refreshToken: "refresh-token",
          user: { id: "1", email: "test@example.com" },
          refreshSession: mockRefreshSession,
          fetchProfile: mockFetchProfile,
          logout: mockLogout,
        }),
      );

      (useAuthStore as any).getState = jest.fn().mockReturnValue({
        accessToken: "test-token",
        user: { id: "1", email: "test@example.com" },
      });

      const { rerender } = renderHook(() => useRequireAuth());

      await waitFor(() => {
        expect(mockRefreshSession).toHaveBeenCalledTimes(1);
      });

      // Re-render after check is complete
      rerender();
      rerender();

      // Should still only have been called once
      expect(mockRefreshSession).toHaveBeenCalledTimes(1);
    });
  });

  describe("Redirect Logic (Secondary Check)", () => {
    it("redirects to login when no tokens exist after check completes", async () => {
      mockRefreshSession.mockResolvedValue(false);

      let renderCount = 0;
      (useAuthStore as unknown as jest.Mock).mockImplementation((selector) => {
        renderCount++;
        return selector({
          isHydrated: true,
          accessToken: renderCount === 1 ? "temp-token" : undefined,
          refreshToken: renderCount === 1 ? "temp-refresh" : undefined,
          user: null,
          refreshSession: mockRefreshSession,
          fetchProfile: mockFetchProfile,
          logout: mockLogout,
        });
      });

      (useAuthStore as any).getState = jest.fn().mockReturnValue({
        accessToken: undefined,
        user: null,
      });

      const { rerender } = renderHook(() => useRequireAuth());

      await waitFor(() => {
        expect(mockRefreshSession).toHaveBeenCalled();
      });

      // Simulate state change after failed refresh
      rerender();

      await waitFor(() => {
        expect(mockRouter.replace).toHaveBeenCalledWith(
          "/login?reason=session-expired",
        );
      });
    });

    it("does not redirect while refresh is in progress", async () => {
      mockRefreshSession.mockImplementation(
        () => new Promise((resolve) => setTimeout(() => resolve(true), 200)),
      );

      (useAuthStore as unknown as jest.Mock).mockImplementation((selector) =>
        selector({
          isHydrated: true,
          accessToken: undefined,
          refreshToken: "refresh-token",
          user: null,
          refreshSession: mockRefreshSession,
          fetchProfile: mockFetchProfile,
          logout: mockLogout,
        }),
      );

      (useAuthStore as any).getState = jest.fn().mockReturnValue({
        accessToken: undefined,
        user: null,
      });

      renderHook(() => useRequireAuth());

      // Wait a bit but not for refresh to complete
      await new Promise((resolve) => setTimeout(resolve, 50));

      // Should not redirect while refresh is in progress
      expect(mockRouter.replace).not.toHaveBeenCalled();

      // Wait for refresh to complete
      await waitFor(() => {
        expect(mockRefreshSession).toHaveBeenCalled();
      });
    });
  });

  describe("Authentication State Return Values", () => {
    it("returns isAuthenticated as true when token and user exist", () => {
      (useAuthStore as unknown as jest.Mock).mockImplementation((selector) =>
        selector({
          isHydrated: true,
          accessToken: "test-token",
          refreshToken: "refresh-token",
          user: { id: "1", email: "test@example.com" },
          refreshSession: mockRefreshSession,
          fetchProfile: mockFetchProfile,
          logout: mockLogout,
        }),
      );

      (useAuthStore as any).getState = jest.fn().mockReturnValue({
        accessToken: "test-token",
        user: { id: "1", email: "test@example.com" },
      });

      const { result } = renderHook(() => useRequireAuth());

      expect(result.current.isAuthenticated).toBe(true);
      expect(result.current.isHydrated).toBe(true);
    });

    it("returns isAuthenticated as false when token exists but no user", () => {
      (useAuthStore as unknown as jest.Mock).mockImplementation((selector) =>
        selector({
          isHydrated: true,
          accessToken: "test-token",
          refreshToken: "refresh-token",
          user: null,
          refreshSession: mockRefreshSession,
          fetchProfile: mockFetchProfile,
          logout: mockLogout,
        }),
      );

      const { result } = renderHook(() => useRequireAuth());

      expect(result.current.isAuthenticated).toBe(false);
    });

    it("returns isAuthenticated as false when user exists but no token", () => {
      (useAuthStore as unknown as jest.Mock).mockImplementation((selector) =>
        selector({
          isHydrated: true,
          accessToken: undefined,
          refreshToken: undefined,
          user: { id: "1", email: "test@example.com" },
          refreshSession: mockRefreshSession,
          fetchProfile: mockFetchProfile,
          logout: mockLogout,
        }),
      );

      const { result } = renderHook(() => useRequireAuth());

      expect(result.current.isAuthenticated).toBe(false);
    });

    it("returns isHydrated correctly", () => {
      (useAuthStore as unknown as jest.Mock).mockImplementation((selector) =>
        selector({
          isHydrated: false,
          accessToken: undefined,
          refreshToken: undefined,
          user: null,
          refreshSession: mockRefreshSession,
          fetchProfile: mockFetchProfile,
          logout: mockLogout,
        }),
      );

      const { result } = renderHook(() => useRequireAuth());

      expect(result.current.isHydrated).toBe(false);
    });
  });

  describe("Edge Cases", () => {
    it("handles refresh that resolves with token but later loses it", async () => {
      mockRefreshSession.mockResolvedValue(true);

      (useAuthStore as unknown as jest.Mock).mockImplementation((selector) =>
        selector({
          isHydrated: true,
          accessToken: "test-token",
          refreshToken: "refresh-token",
          user: { id: "1", email: "test@example.com" },
          refreshSession: mockRefreshSession,
          fetchProfile: mockFetchProfile,
          logout: mockLogout,
        }),
      );

      // First getState returns token, second returns no token (edge case)
      let getStateCallCount = 0;
      (useAuthStore as any).getState = jest.fn().mockImplementation(() => {
        getStateCallCount++;
        if (getStateCallCount === 1) {
          return { accessToken: "test-token", user: { id: "1" } };
        }
        return { accessToken: undefined, user: null };
      });

      const { rerender } = renderHook(() => useRequireAuth());

      await waitFor(() => {
        expect(mockRefreshSession).toHaveBeenCalled();
      });

      // Simulate the state change
      (useAuthStore as unknown as jest.Mock).mockImplementation((selector) =>
        selector({
          isHydrated: true,
          accessToken: undefined,
          refreshToken: undefined,
          user: null,
          refreshSession: mockRefreshSession,
          fetchProfile: mockFetchProfile,
          logout: mockLogout,
        }),
      );

      rerender();

      await waitFor(() => {
        expect(mockRouter.replace).toHaveBeenCalledWith("/login");
      });
    });

    it("handles concurrent logout and redirect gracefully", async () => {
      mockRefreshSession.mockResolvedValue(false);
      mockLogout.mockResolvedValue(undefined);

      (useAuthStore as unknown as jest.Mock).mockImplementation((selector) =>
        selector({
          isHydrated: true,
          accessToken: undefined,
          refreshToken: undefined,
          user: null,
          refreshSession: mockRefreshSession,
          fetchProfile: mockFetchProfile,
          logout: mockLogout,
        }),
      );

      (useAuthStore as any).getState = jest.fn().mockReturnValue({
        accessToken: undefined,
        user: null,
      });

      renderHook(() => useRequireAuth());

      await waitFor(() => {
        expect(mockLogout).toHaveBeenCalledWith({ reason: "session-expired" });
        expect(mockRouter.replace).toHaveBeenCalledWith(
          "/login?reason=session-expired",
        );
      });

      // Should handle gracefully without errors
      expect(mockLogout).toHaveBeenCalledTimes(1);
    });
  });
});
