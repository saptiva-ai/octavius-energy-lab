/**
 * Tests for UX Logger
 *
 * Tests structured logging, log levels, and trace functionality
 */

import {
  logUX,
  logState,
  logEffect,
  logRender,
  logAction,
  logStream,
  logError,
  getLogs,
  clearLogs,
  printTrace,
} from "../ux-logger";

describe("UX Logger", () => {
  beforeEach(() => {
    // Clear logs before each test
    clearLogs();

    // Spy on console.log to prevent output during tests
    jest.spyOn(console, "log").mockImplementation();
    jest.spyOn(console, "group").mockImplementation();
    jest.spyOn(console, "groupEnd").mockImplementation();
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  describe("logUX", () => {
    it("should log a message with level and tag", () => {
      logUX("STATE", "test-tag", { key: "value" });

      const logs = getLogs();
      expect(logs).toHaveLength(1);
      expect(logs[0].level).toBe("STATE");
      expect(logs[0].tag).toBe("test-tag");
      expect(logs[0].data).toEqual({ key: "value" });
    });

    it("should log without data", () => {
      logUX("ACTION", "action-tag");

      const logs = getLogs();
      expect(logs).toHaveLength(1);
      expect(logs[0].level).toBe("ACTION");
      expect(logs[0].tag).toBe("action-tag");
      expect(logs[0].data).toBeUndefined();
    });

    it("should include timestamp in log entry", () => {
      const before = Date.now();
      logUX("EFFECT", "effect-tag");
      const after = Date.now();

      const logs = getLogs();
      expect(logs[0].timestamp).toBeGreaterThanOrEqual(before);
      expect(logs[0].timestamp).toBeLessThanOrEqual(after);
    });

    it("should limit logs to MAX_LOGS", () => {
      // Add more than 100 logs
      for (let i = 0; i < 150; i++) {
        logUX("STATE", `tag-${i}`);
      }

      const logs = getLogs();
      expect(logs.length).toBeLessThanOrEqual(100);
    });

    it("should call console.log", () => {
      logUX("ERROR", "error-tag", { error: "Test error" });

      // eslint-disable-next-line no-console
      expect(console.log).toHaveBeenCalled();
    });
  });

  describe("logState", () => {
    it("should log state with correct format", () => {
      logState("state-update", {
        currentChatId: "chat-123",
        messagesLength: 5,
        isDraftMode: false,
      });

      const logs = getLogs();
      expect(logs).toHaveLength(1);
      expect(logs[0].level).toBe("STATE");
      expect(logs[0].tag).toBe("state-update");
    });

    it("should include chat id in data", () => {
      logState("with-chat-id", {
        currentChatId: "chat-456",
        messagesLength: 10,
        isDraftMode: true,
      });

      const logs = getLogs();
      expect(logs[0].data).toHaveProperty("chatId", "chat-456");
    });

    it("should include messages length", () => {
      logState("with-messages", {
        currentChatId: null,
        messagesLength: 3,
        isDraftMode: false,
      });

      const logs = getLogs();
      expect(logs[0].data).toHaveProperty("msgs", 3);
    });

    it("should include draft mode flag", () => {
      logState("draft-mode", {
        currentChatId: null,
        messagesLength: 0,
        isDraftMode: true,
      });

      const logs = getLogs();
      expect(logs[0].data).toHaveProperty("draft", true);
    });
  });

  describe("logEffect", () => {
    it("should log effect with level EFFECT", () => {
      logEffect("useEffect-test", { dep1: "value1", dep2: "value2" });

      const logs = getLogs();
      expect(logs[0].level).toBe("EFFECT");
    });

    it("should include dependencies in data", () => {
      logEffect("dependencies", { chatId: "chat-123", userId: "user-456" });

      const logs = getLogs();
      expect(logs[0].data).toEqual({ chatId: "chat-123", userId: "user-456" });
    });
  });

  describe("logRender", () => {
    it("should log render with level RENDER", () => {
      logRender("ChatComponent", { prop1: "value1" });

      const logs = getLogs();
      expect(logs[0].level).toBe("RENDER");
    });

    it("should include component name as tag", () => {
      logRender("MessageList", { count: 5 });

      const logs = getLogs();
      expect(logs[0].tag).toBe("MessageList");
    });

    it("should include props in data", () => {
      logRender("Button", { disabled: true, onClick: "function" });

      const logs = getLogs();
      expect(logs[0].data).toHaveProperty("disabled", true);
    });
  });

  describe("logAction", () => {
    it("should log action with level ACTION", () => {
      logAction("send-message", { messageId: "msg-123" });

      const logs = getLogs();
      expect(logs[0].level).toBe("ACTION");
    });

    it("should log action without payload", () => {
      logAction("clear-chat");

      const logs = getLogs();
      expect(logs[0].tag).toBe("clear-chat");
      expect(logs[0].data).toBeUndefined();
    });
  });

  describe("logStream", () => {
    it("should log stream event with level STREAM", () => {
      logStream("message-chunk", { content: "Hello" });

      const logs = getLogs();
      expect(logs[0].level).toBe("STREAM");
    });

    it("should log stream event without data", () => {
      logStream("stream-started");

      const logs = getLogs();
      expect(logs[0].tag).toBe("stream-started");
    });
  });

  describe("logError", () => {
    it("should log error with level ERROR", () => {
      logError("api-failure", { status: 500 });

      const logs = getLogs();
      expect(logs[0].level).toBe("ERROR");
    });

    it("should log error without details", () => {
      logError("unknown-error");

      const logs = getLogs();
      expect(logs[0].tag).toBe("unknown-error");
      expect(logs[0].data).toBeUndefined();
    });

    it("should include error details", () => {
      logError("validation-error", { field: "email", message: "Invalid" });

      const logs = getLogs();
      expect(logs[0].data).toEqual({ field: "email", message: "Invalid" });
    });
  });

  describe("getLogs", () => {
    it("should return all logs", () => {
      logUX("STATE", "log1");
      logUX("ACTION", "log2");
      logUX("ERROR", "log3");

      const logs = getLogs();
      expect(logs).toHaveLength(3);
    });

    it("should filter logs by level", () => {
      logUX("STATE", "state-log");
      logUX("ACTION", "action-log");
      logUX("ERROR", "error-log");
      logUX("STATE", "state-log-2");

      const stateLogs = getLogs("STATE");
      expect(stateLogs).toHaveLength(2);
      expect(stateLogs[0].level).toBe("STATE");
      expect(stateLogs[1].level).toBe("STATE");
    });

    it("should return empty array when no logs", () => {
      const logs = getLogs();
      expect(logs).toEqual([]);
    });

    it("should filter by ERROR level", () => {
      logUX("STATE", "state");
      logUX("ERROR", "error1");
      logUX("ACTION", "action");
      logUX("ERROR", "error2");

      const errorLogs = getLogs("ERROR");
      expect(errorLogs).toHaveLength(2);
    });
  });

  describe("clearLogs", () => {
    it("should clear all logs", () => {
      logUX("STATE", "log1");
      logUX("ACTION", "log2");

      expect(getLogs()).toHaveLength(2);

      clearLogs();

      expect(getLogs()).toHaveLength(0);
    });

    it("should allow new logs after clearing", () => {
      logUX("STATE", "log1");
      clearLogs();
      logUX("ACTION", "log2");

      expect(getLogs()).toHaveLength(1);
      expect(getLogs()[0].tag).toBe("log2");
    });
  });

  describe("printTrace", () => {
    it("should call console.group with scenario name", () => {
      logUX("STATE", "test");

      printTrace("Test Scenario");

      // eslint-disable-next-line no-console
      expect(console.group).toHaveBeenCalledWith(
        expect.stringContaining("Test Scenario"),
      );
    });

    it("should call console.groupEnd", () => {
      logUX("STATE", "test");

      printTrace("Test");

      // eslint-disable-next-line no-console
      expect(console.groupEnd).toHaveBeenCalled();
    });

    it("should print logs with elapsed time", () => {
      logUX("STATE", "log1");
      logUX("ACTION", "log2");

      printTrace("Elapsed Time Test");

      // Should have called console.log for each log entry
      // eslint-disable-next-line no-console
      expect(console.log).toHaveBeenCalledTimes(4); // 2 from logUX + 2 from printTrace
    });

    it("should handle empty logs gracefully", () => {
      clearLogs();

      printTrace("Empty Trace");

      // eslint-disable-next-line no-console
      expect(console.group).toHaveBeenCalled();
      // eslint-disable-next-line no-console
      expect(console.groupEnd).toHaveBeenCalled();
    });
  });

  describe("log ordering", () => {
    it("should maintain chronological order", () => {
      logUX("STATE", "first");
      logUX("ACTION", "second");
      logUX("EFFECT", "third");

      const logs = getLogs();
      expect(logs[0].tag).toBe("first");
      expect(logs[1].tag).toBe("second");
      expect(logs[2].tag).toBe("third");
    });

    it("should have increasing timestamps", () => {
      logUX("STATE", "log1");
      logUX("STATE", "log2");
      logUX("STATE", "log3");

      const logs = getLogs();
      expect(logs[1].timestamp).toBeGreaterThanOrEqual(logs[0].timestamp);
      expect(logs[2].timestamp).toBeGreaterThanOrEqual(logs[1].timestamp);
    });
  });
});
