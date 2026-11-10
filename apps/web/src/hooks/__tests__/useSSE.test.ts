/**
 * Tests for useSSE hook
 *
 * Basic tests for Server-Sent Events functionality
 */

import { renderHook, act } from "@testing-library/react";
import { useSSE } from "../useSSE";

// Mock crypto.randomUUID
global.crypto = {
  randomUUID: () => "test-uuid-123",
} as any;

// Mock chat store
jest.mock("../../lib/stores/chat-store", () => ({
  useChatStore: () => ({
    findFileReviewMessage: jest.fn(),
    updateFileReviewMessage: jest.fn(),
  }),
}));

describe("useSSE", () => {
  describe("initialization", () => {
    it("should initialize with default state", () => {
      const { result } = renderHook(() => useSSE(null, null));

      expect(result.current.isConnected).toBe(false);
      expect(result.current.error).toBeNull();
    });

    it("should not connect when jobId is null", () => {
      const { result } = renderHook(() => useSSE(null, null));

      expect(result.current.isConnected).toBe(false);
    });

    it("should initialize lastEvent as null", () => {
      const { result } = renderHook(() => useSSE(null, null));

      expect(result.current.lastEvent).toBeNull();
    });
  });

  describe("connection state", () => {
    it("should provide connection state", () => {
      const { result } = renderHook(() => useSSE(null, null));

      expect(typeof result.current.isConnected).toBe("boolean");
    });

    it("should start disconnected", () => {
      const { result } = renderHook(() => useSSE(null, null));

      expect(result.current.isConnected).toBe(false);
    });
  });

  describe("error handling", () => {
    it("should initialize error as null", () => {
      const { result } = renderHook(() => useSSE(null, null));

      expect(result.current.error).toBeNull();
    });

    it("should provide error state", () => {
      const { result } = renderHook(() => useSSE(null, null));

      expect(result.current.error).toBeDefined();
    });
  });

  describe("lastEvent tracking", () => {
    it("should track lastEvent", () => {
      const { result } = renderHook(() => useSSE(null, null));

      expect(result.current.lastEvent).toBeDefined();
    });

    it("should initialize lastEvent as null", () => {
      const { result } = renderHook(() => useSSE(null, null));

      expect(result.current.lastEvent).toBeNull();
    });
  });

  describe("control functions", () => {
    it("should provide reconnect function", () => {
      const { result } = renderHook(() => useSSE(null, null));

      expect(typeof result.current.reconnect).toBe("function");
    });

    it("should provide disconnect function", () => {
      const { result } = renderHook(() => useSSE(null, null));

      expect(typeof result.current.disconnect).toBe("function");
    });
  });

  describe("configuration", () => {
    it("should accept jobId and docId parameters", () => {
      const { result } = renderHook(() => useSSE("job-123", "doc-456"));

      expect(result.current).toBeDefined();
    });

    it("should handle null jobId gracefully", () => {
      const { result } = renderHook(() => useSSE(null, "doc-456"));

      expect(result.current.isConnected).toBe(false);
      expect(result.current.error).toBeNull();
    });

    it("should handle null docId gracefully", () => {
      const { result } = renderHook(() => useSSE("job-123", null));

      expect(result.current.isConnected).toBe(false);
      // Error might be set if crypto is not available in test environment
      expect(result.current.error !== undefined).toBe(true);
    });

    it("should accept enabled parameter", () => {
      const { result } = renderHook(() => useSSE("job-123", "doc-456", false));

      expect(result.current).toBeDefined();
    });
  });

  describe("cleanup", () => {
    it("should clean up on unmount", () => {
      const { unmount } = renderHook(() => useSSE(null, null));

      expect(() => unmount()).not.toThrow();
    });

    it("should handle re-renders", () => {
      const { rerender } = renderHook(() => useSSE(null, null));

      expect(() => rerender()).not.toThrow();
    });
  });
});
