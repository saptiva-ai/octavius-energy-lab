/**
 * Tests for UI Store
 *
 * Tests sidebar state, theme management, and connection status tracking
 */

import { renderHook, act } from "@testing-library/react";
import { useUIStore, useUI } from "../ui-store";
import { apiClient } from "../../api-client";

// Mock api-client
jest.mock("../../api-client", () => ({
  apiClient: {
    checkConnection: jest.fn(),
  },
}));

// Mock logger
jest.mock("../../logger", () => ({
  logWarn: jest.fn(),
}));

describe("useUIStore", () => {
  beforeEach(() => {
    // Reset store state before each test
    const { result } = renderHook(() => useUIStore());
    act(() => {
      result.current.setSidebarOpen(false);
      result.current.setTheme("light");
      result.current.setConnectionStatus("disconnected");
    });

    // Clear mocks
    jest.clearAllMocks();
  });

  describe("initial state", () => {
    it("should initialize with default state", () => {
      const { result } = renderHook(() => useUIStore());

      expect(result.current.sidebarOpen).toBe(false);
      expect(result.current.theme).toBe("light");
      expect(result.current.connectionStatus).toBe("disconnected");
    });
  });

  describe("sidebar state", () => {
    it("should open sidebar", () => {
      const { result } = renderHook(() => useUIStore());

      act(() => {
        result.current.setSidebarOpen(true);
      });

      expect(result.current.sidebarOpen).toBe(true);
    });

    it("should close sidebar", () => {
      const { result } = renderHook(() => useUIStore());

      act(() => {
        result.current.setSidebarOpen(true);
      });
      expect(result.current.sidebarOpen).toBe(true);

      act(() => {
        result.current.setSidebarOpen(false);
      });
      expect(result.current.sidebarOpen).toBe(false);
    });

    it("should toggle sidebar state", () => {
      const { result } = renderHook(() => useUIStore());

      const initialState = result.current.sidebarOpen;

      act(() => {
        result.current.setSidebarOpen(!initialState);
      });

      expect(result.current.sidebarOpen).toBe(!initialState);
    });
  });

  describe("theme management", () => {
    it("should set theme to dark", () => {
      const { result } = renderHook(() => useUIStore());

      act(() => {
        result.current.setTheme("dark");
      });

      expect(result.current.theme).toBe("dark");
    });

    it("should set theme to light", () => {
      const { result } = renderHook(() => useUIStore());

      act(() => {
        result.current.setTheme("dark");
      });

      act(() => {
        result.current.setTheme("light");
      });

      expect(result.current.theme).toBe("light");
    });

    it("should toggle theme", () => {
      const { result } = renderHook(() => useUIStore());

      const currentTheme = result.current.theme;
      const newTheme = currentTheme === "light" ? "dark" : "light";

      act(() => {
        result.current.setTheme(newTheme);
      });

      expect(result.current.theme).toBe(newTheme);
    });
  });

  describe("connection status", () => {
    it("should set connection status to connected", () => {
      const { result } = renderHook(() => useUIStore());

      act(() => {
        result.current.setConnectionStatus("connected");
      });

      expect(result.current.connectionStatus).toBe("connected");
    });

    it("should set connection status to connecting", () => {
      const { result } = renderHook(() => useUIStore());

      act(() => {
        result.current.setConnectionStatus("connecting");
      });

      expect(result.current.connectionStatus).toBe("connecting");
    });

    it("should set connection status to disconnected", () => {
      const { result } = renderHook(() => useUIStore());

      act(() => {
        result.current.setConnectionStatus("connected");
      });

      act(() => {
        result.current.setConnectionStatus("disconnected");
      });

      expect(result.current.connectionStatus).toBe("disconnected");
    });
  });

  describe("checkConnection", () => {
    it("should set status to connecting then connected on success", async () => {
      const { result } = renderHook(() => useUIStore());
      (apiClient.checkConnection as jest.Mock).mockResolvedValue(true);

      await act(async () => {
        await result.current.checkConnection();
      });

      expect(result.current.connectionStatus).toBe("connected");
    });

    it("should set status to connecting then disconnected on failure", async () => {
      const { result } = renderHook(() => useUIStore());
      (apiClient.checkConnection as jest.Mock).mockResolvedValue(false);

      await act(async () => {
        await result.current.checkConnection();
      });

      expect(result.current.connectionStatus).toBe("disconnected");
    });

    it("should set status to disconnected on error", async () => {
      const { result } = renderHook(() => useUIStore());
      (apiClient.checkConnection as jest.Mock).mockRejectedValue(
        new Error("Network error"),
      );

      await act(async () => {
        await result.current.checkConnection();
      });

      expect(result.current.connectionStatus).toBe("disconnected");
    });

    it("should call apiClient.checkConnection", async () => {
      const { result } = renderHook(() => useUIStore());
      (apiClient.checkConnection as jest.Mock).mockResolvedValue(true);

      await act(async () => {
        await result.current.checkConnection();
      });

      expect(apiClient.checkConnection).toHaveBeenCalledTimes(1);
    });
  });

  describe("clearAllData", () => {
    it("should reset sidebar to closed", () => {
      const { result } = renderHook(() => useUIStore());

      act(() => {
        result.current.setSidebarOpen(true);
      });

      act(() => {
        result.current.clearAllData();
      });

      expect(result.current.sidebarOpen).toBe(false);
    });

    it("should reset connection status to disconnected", () => {
      const { result } = renderHook(() => useUIStore());

      act(() => {
        result.current.setConnectionStatus("connected");
      });

      act(() => {
        result.current.clearAllData();
      });

      expect(result.current.connectionStatus).toBe("disconnected");
    });

    it("should clear localStorage", () => {
      const removeItemSpy = jest.spyOn(Storage.prototype, "removeItem");
      const { result } = renderHook(() => useUIStore());

      act(() => {
        result.current.clearAllData();
      });

      expect(removeItemSpy).toHaveBeenCalled();
    });
  });
});

describe("useUI (backward compatibility)", () => {
  it("should return store state and actions", () => {
    const { result } = renderHook(() => useUI());

    expect(result.current).toHaveProperty("sidebarOpen");
    expect(result.current).toHaveProperty("theme");
    expect(result.current).toHaveProperty("connectionStatus");
    expect(result.current).toHaveProperty("setSidebarOpen");
    expect(result.current).toHaveProperty("setTheme");
    expect(result.current).toHaveProperty("checkConnection");
    expect(result.current).toHaveProperty("clearAllData");
  });

  it("should update state through useUI hook", () => {
    const { result } = renderHook(() => useUI());

    act(() => {
      result.current.setSidebarOpen(true);
    });

    expect(result.current.sidebarOpen).toBe(true);
  });

  it("should update theme through useUI hook", () => {
    const { result } = renderHook(() => useUI());

    act(() => {
      result.current.setTheme("dark");
    });

    expect(result.current.theme).toBe("dark");
  });
});
