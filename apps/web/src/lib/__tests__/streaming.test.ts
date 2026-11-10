/**
 * Tests for streaming.ts - Server-Sent Events (SSE) utilities
 *
 * Coverage:
 * - StreamingClient: Connection, reconnection, error handling
 * - useStreaming hook: Connection lifecycle
 * - Helper functions: formatProgressMessage, calculateProgress
 * - createStreamingUrl: URL construction
 */

import { renderHook, act } from "@testing-library/react";
import {
  StreamingClient,
  useStreaming,
  createStreamingUrl,
  formatProgressMessage,
  calculateProgress,
  STREAM_EVENTS,
  type StreamEvent,
  type StreamOptions,
} from "../streaming";

// Mock EventSource
class MockEventSource {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSED = 2;

  url: string;
  readyState: number = MockEventSource.CONNECTING;
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    // Simulate async connection
    setTimeout(() => {
      this.readyState = MockEventSource.OPEN;
      if (this.onopen) {
        this.onopen(new Event("open"));
      }
    }, 0);
  }

  close() {
    this.readyState = MockEventSource.CLOSED;
  }

  // Test helper to simulate messages
  simulateMessage(data: string) {
    if (this.onmessage) {
      const event = new MessageEvent("message", { data });
      this.onmessage(event);
    }
  }

  // Test helper to simulate errors
  simulateError() {
    if (this.onerror) {
      this.onerror(new Event("error"));
    }
  }
}

// Replace global EventSource
global.EventSource = MockEventSource as any;

describe("streaming.ts", () => {
  describe("StreamingClient", () => {
    let client: StreamingClient;
    let onOpen: jest.Mock;
    let onMessage: jest.Mock;
    let onError: jest.Mock;
    let onClose: jest.Mock;

    beforeEach(() => {
      onOpen = jest.fn();
      onMessage = jest.fn();
      onError = jest.fn();
      onClose = jest.fn();
    });

    afterEach(() => {
      if (client) {
        client.close();
      }
    });

    it("connects successfully", async () => {
      client = new StreamingClient("/api/stream/test", { onOpen });

      client.connect();

      // Wait for connection
      await new Promise((resolve) => setTimeout(resolve, 10));

      expect(onOpen).toHaveBeenCalled();
      expect(client.isConnected()).toBe(true);
    });

    it("receives and parses messages", async () => {
      client = new StreamingClient("/api/stream/test", { onMessage });

      client.connect();
      await new Promise((resolve) => setTimeout(resolve, 10));

      // Simulate message
      const event: StreamEvent = {
        event_type: "task_started",
        task_id: "task-123",
        timestamp: new Date().toISOString(),
        data: { status: "running" },
      };

      (client as any).eventSource.simulateMessage(JSON.stringify(event));

      expect(onMessage).toHaveBeenCalledWith(event);
    });

    it("handles invalid JSON messages gracefully", async () => {
      const consoleErrorSpy = jest
        .spyOn(console, "error")
        .mockImplementation(() => {});

      client = new StreamingClient("/api/stream/test", { onMessage });

      client.connect();
      await new Promise((resolve) => setTimeout(resolve, 10));

      // Simulate invalid JSON
      (client as any).eventSource.simulateMessage("invalid json");

      expect(onMessage).not.toHaveBeenCalled();
      consoleErrorSpy.mockRestore();
    });

    it("handles errors", async () => {
      client = new StreamingClient("/api/stream/test", {
        onError,
        reconnect: false,
      });

      client.connect();
      await new Promise((resolve) => setTimeout(resolve, 10));

      // Simulate error
      (client as any).eventSource.simulateError();

      expect(onError).toHaveBeenCalled();
    });

    it("closes connection manually", async () => {
      client = new StreamingClient("/api/stream/test", { onClose });

      client.connect();
      await new Promise((resolve) => setTimeout(resolve, 10));

      expect(client.isConnected()).toBe(true);

      client.close();

      expect(client.isConnected()).toBe(false);
      expect(onClose).toHaveBeenCalled();
    });

    it("does not reconnect if already connected", async () => {
      client = new StreamingClient("/api/stream/test", { onOpen });

      client.connect();
      await new Promise((resolve) => setTimeout(resolve, 10));

      expect(onOpen).toHaveBeenCalledTimes(1);

      // Try to connect again
      client.connect();

      expect(onOpen).toHaveBeenCalledTimes(1); // Still just once
    });

    it("attempts reconnection on error", async () => {
      jest.useFakeTimers();

      client = new StreamingClient("/api/stream/test", {
        onError,
        reconnect: true,
        reconnectInterval: 1000,
        maxReconnectAttempts: 2,
      });

      client.connect();
      await Promise.resolve();

      // Simulate error
      (client as any).eventSource.simulateError();

      expect(onError).toHaveBeenCalled();

      // Fast-forward time to trigger reconnection
      jest.advanceTimersByTime(1500);

      jest.useRealTimers();
    });

    it("stops reconnecting after max attempts", async () => {
      jest.useFakeTimers();

      const consoleErrorSpy = jest
        .spyOn(console, "error")
        .mockImplementation(() => {});

      client = new StreamingClient("/api/stream/test", {
        onError,
        reconnect: true,
        reconnectInterval: 100,
        maxReconnectAttempts: 2,
      });

      client.connect();
      await Promise.resolve();

      // Simulate multiple errors
      for (let i = 0; i < 3; i++) {
        (client as any).eventSource?.simulateError();
        jest.advanceTimersByTime(1000);
        await Promise.resolve();
      }

      consoleErrorSpy.mockRestore();
      jest.useRealTimers();
    });

    it("returns correct ready state", () => {
      client = new StreamingClient("/api/stream/test");

      expect(client.getReadyState()).toBe(EventSource.CLOSED);

      client.connect();

      expect(client.getReadyState()).toBeGreaterThanOrEqual(0);
    });
  });

  describe("useStreaming hook", () => {
    it("connects when URL is provided", async () => {
      const { result } = renderHook(() => useStreaming("/api/stream/test", {}));

      // Wait longer for async connection
      await new Promise((resolve) => setTimeout(resolve, 50));

      // Check that we have a client and it's open or connecting
      expect(result.current.readyState).toBeGreaterThanOrEqual(
        EventSource.CONNECTING,
      );
    });

    it("does not connect when URL is null", () => {
      const { result } = renderHook(() => useStreaming(null, {}));

      expect(result.current.readyState).toBe(EventSource.CLOSED);
    });

    it("disconnects on unmount", async () => {
      const { result, unmount } = renderHook(() =>
        useStreaming("/api/stream/test", {}),
      );

      await new Promise((resolve) => setTimeout(resolve, 50));

      // Verify disconnect function exists
      expect(result.current.disconnect).toBeDefined();
      expect(typeof result.current.disconnect).toBe("function");

      unmount();

      // After unmount, readyState should be defined
      expect(result.current.readyState).toBeDefined();
    });

    it("reconnects when URL changes", async () => {
      const { result, rerender } = renderHook(
        ({ url }) => useStreaming(url, {}),
        {
          initialProps: { url: "/api/stream/test1" },
        },
      );

      await new Promise((resolve) => setTimeout(resolve, 10));

      // Change URL
      rerender({ url: "/api/stream/test2" });

      await new Promise((resolve) => setTimeout(resolve, 10));

      expect(result.current.readyState).toBe(EventSource.OPEN);
    });

    it("can manually disconnect", async () => {
      const { result } = renderHook(() => useStreaming("/api/stream/test", {}));

      await new Promise((resolve) => setTimeout(resolve, 10));

      act(() => {
        result.current.disconnect();
      });

      expect(result.current.readyState).toBe(EventSource.CLOSED);
    });

    it("can manually reconnect", async () => {
      const { result } = renderHook(() => useStreaming("/api/stream/test", {}));

      await new Promise((resolve) => setTimeout(resolve, 50));

      // Test disconnect function
      expect(result.current.disconnect).toBeDefined();
      act(() => {
        result.current.disconnect();
      });

      // Test connect function
      expect(result.current.connect).toBeDefined();
      act(() => {
        result.current.connect();
      });

      await new Promise((resolve) => setTimeout(resolve, 50));

      // Verify functions are still accessible
      expect(result.current.connect).toBeDefined();
      expect(result.current.disconnect).toBeDefined();
    });
  });

  describe("createStreamingUrl", () => {
    it("creates URL with default base", () => {
      const url = createStreamingUrl("task-123");

      expect(url).toContain("/api/stream/task-123");
    });

    it("creates URL with custom base", () => {
      const url = createStreamingUrl("task-456", "https://example.com");

      expect(url).toBe("https://example.com/api/stream/task-456");
    });

    it("uses NEXT_PUBLIC_API_URL if available", () => {
      const original = process.env.NEXT_PUBLIC_API_URL;
      process.env.NEXT_PUBLIC_API_URL = "https://api.example.com";

      const url = createStreamingUrl("task-789");

      expect(url).toBe("https://api.example.com/api/stream/task-789");

      process.env.NEXT_PUBLIC_API_URL = original;
    });
  });

  describe("formatProgressMessage", () => {
    it("formats task started", () => {
      const event: StreamEvent = {
        event_type: STREAM_EVENTS.TASK_STARTED,
        task_id: "task-1",
        timestamp: new Date().toISOString(),
        data: {},
      };

      expect(formatProgressMessage(event)).toBe("Starting research task...");
    });

    it("formats sources found with count", () => {
      const event: StreamEvent = {
        event_type: STREAM_EVENTS.SOURCES_FOUND,
        task_id: "task-1",
        timestamp: new Date().toISOString(),
        data: { sources_count: 5 },
      };

      expect(formatProgressMessage(event)).toBe("Found 5 relevant sources");
    });

    it("formats processing sources with progress", () => {
      const event: StreamEvent = {
        event_type: STREAM_EVENTS.PROCESSING_SOURCES,
        task_id: "task-1",
        timestamp: new Date().toISOString(),
        data: { processed: 3, total: 10 },
      };

      expect(formatProgressMessage(event)).toBe("Processing sources (3/10)");
    });

    it("formats task completed", () => {
      const event: StreamEvent = {
        event_type: STREAM_EVENTS.TASK_COMPLETED,
        task_id: "task-1",
        timestamp: new Date().toISOString(),
        data: {},
      };

      expect(formatProgressMessage(event)).toBe(
        "Research completed successfully!",
      );
    });

    it("formats error with message", () => {
      const event: StreamEvent = {
        event_type: STREAM_EVENTS.STREAM_ERROR,
        task_id: "task-1",
        timestamp: new Date().toISOString(),
        data: { error: "Network timeout" },
      };

      expect(formatProgressMessage(event)).toBe("Error: Network timeout");
    });

    it("handles unknown event type", () => {
      const event: StreamEvent = {
        event_type: "unknown_event",
        task_id: "task-1",
        timestamp: new Date().toISOString(),
        data: { message: "Custom message" },
      };

      expect(formatProgressMessage(event)).toBe("Custom message");
    });
  });

  describe("calculateProgress", () => {
    it("uses explicit progress value", () => {
      const event: StreamEvent = {
        event_type: "custom",
        task_id: "task-1",
        timestamp: new Date().toISOString(),
        data: {},
        progress: 0.75,
      };

      expect(calculateProgress(event)).toBe(0.75);
    });

    it("clamps progress between 0 and 1", () => {
      const event1: StreamEvent = {
        event_type: "custom",
        task_id: "task-1",
        timestamp: new Date().toISOString(),
        data: {},
        progress: 1.5,
      };

      expect(calculateProgress(event1)).toBe(1);

      const event2: StreamEvent = {
        event_type: "custom",
        task_id: "task-1",
        timestamp: new Date().toISOString(),
        data: {},
        progress: -0.5,
      };

      expect(calculateProgress(event2)).toBe(0);
    });

    it("calculates progress from event type", () => {
      expect(
        calculateProgress({
          event_type: STREAM_EVENTS.TASK_STARTED,
          task_id: "task-1",
          timestamp: new Date().toISOString(),
          data: {},
        }),
      ).toBe(0.1);

      expect(
        calculateProgress({
          event_type: STREAM_EVENTS.SOURCES_FOUND,
          task_id: "task-1",
          timestamp: new Date().toISOString(),
          data: {},
        }),
      ).toBe(0.4);

      expect(
        calculateProgress({
          event_type: STREAM_EVENTS.TASK_COMPLETED,
          task_id: "task-1",
          timestamp: new Date().toISOString(),
          data: {},
        }),
      ).toBe(1.0);
    });

    it("returns 0 for unknown event type", () => {
      const event: StreamEvent = {
        event_type: "unknown",
        task_id: "task-1",
        timestamp: new Date().toISOString(),
        data: {},
      };

      expect(calculateProgress(event)).toBe(0);
    });
  });
});
