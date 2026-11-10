/**
 * Tests for useDeepResearch hook
 *
 * Basic tests for deep research functionality
 */

import { renderHook, act } from "@testing-library/react";
import { useDeepResearch } from "../useDeepResearch";

describe("useDeepResearch", () => {
  describe("initialization", () => {
    it("should initialize with default state", () => {
      const { result } = renderHook(() => useDeepResearch());

      expect(result.current.phase).toBe("IDLE");
      expect(result.current.isStreaming).toBe(false);
      expect(result.current.progress).toBe(0);
      expect(result.current.sources).toEqual([]);
      expect(result.current.evidences).toEqual([]);
    });

    it("should provide stop function", () => {
      const { result } = renderHook(() => useDeepResearch());

      expect(typeof result.current.stop).toBe("function");
    });

    it("should provide reset function", () => {
      const { result } = renderHook(() => useDeepResearch());

      expect(typeof result.current.reset).toBe("function");
    });
  });

  describe("state management", () => {
    it("should reset state when reset is called", () => {
      const { result } = renderHook(() => useDeepResearch());

      act(() => {
        result.current.reset();
      });

      expect(result.current.phase).toBe("IDLE");
      expect(result.current.progress).toBe(0);
      expect(result.current.sources).toEqual([]);
    });
  });

  describe("phase tracking", () => {
    it("should track research phases", () => {
      const { result } = renderHook(() => useDeepResearch());

      expect(result.current.phase).toBeDefined();
      expect(typeof result.current.phase).toBe("string");
    });

    it("should initialize phase as IDLE", () => {
      const { result } = renderHook(() => useDeepResearch());

      expect(result.current.phase).toBe("IDLE");
    });
  });

  describe("progress tracking", () => {
    it("should initialize progress at 0", () => {
      const { result } = renderHook(() => useDeepResearch());

      expect(result.current.progress).toBe(0);
    });

    it("should track progress as a number", () => {
      const { result } = renderHook(() => useDeepResearch());

      expect(typeof result.current.progress).toBe("number");
    });
  });

  describe("sources collection", () => {
    it("should initialize with empty sources array", () => {
      const { result } = renderHook(() => useDeepResearch());

      expect(Array.isArray(result.current.sources)).toBe(true);
      expect(result.current.sources).toHaveLength(0);
    });

    it("should clear sources on reset", () => {
      const { result } = renderHook(() => useDeepResearch());

      act(() => {
        result.current.reset();
      });

      expect(result.current.sources).toEqual([]);
    });
  });

  describe("evidence collection", () => {
    it("should initialize with empty evidence array", () => {
      const { result } = renderHook(() => useDeepResearch());

      expect(Array.isArray(result.current.evidences)).toBe(true);
      expect(result.current.evidences).toHaveLength(0);
    });

    it("should clear evidence on reset", () => {
      const { result } = renderHook(() => useDeepResearch());

      act(() => {
        result.current.reset();
      });

      expect(result.current.evidences).toEqual([]);
    });
  });

  describe("active state", () => {
    it("should not be active initially", () => {
      const { result } = renderHook(() => useDeepResearch());

      expect(result.current.isStreaming).toBe(false);
    });
  });

  describe("error handling", () => {
    it("should provide error state", () => {
      const { result } = renderHook(() => useDeepResearch());

      expect(result.current.error).toBeNull();
    });

    it("should clear error on reset", () => {
      const { result } = renderHook(() => useDeepResearch());

      act(() => {
        result.current.reset();
      });

      expect(result.current.error).toBeNull();
    });
  });
});
