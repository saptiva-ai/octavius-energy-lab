/**
 * Tests for utility functions
 *
 * Tests common utility functions like cn, formatDate, truncateText, etc.
 */

import {
  cn,
  formatDate,
  formatRelativeTime,
  truncateText,
  generateId,
  debounce,
} from "../utils";

describe("utils", () => {
  describe("cn (className merger)", () => {
    it("should merge class names", () => {
      const result = cn("class1", "class2");
      expect(result).toContain("class1");
      expect(result).toContain("class2");
    });

    it("should handle conditional classes", () => {
      const result = cn("base", false && "hidden", true && "visible");
      expect(result).toContain("base");
      expect(result).toContain("visible");
      expect(result).not.toContain("hidden");
    });

    it("should merge tailwind classes intelligently", () => {
      const result = cn("text-red-500", "text-blue-500");
      // Should keep only the last text color class
      expect(result).toContain("text-blue-500");
    });

    it("should handle empty input", () => {
      const result = cn();
      expect(result).toBe("");
    });

    it("should handle array of classes", () => {
      const result = cn(["class1", "class2"]);
      expect(result).toContain("class1");
      expect(result).toContain("class2");
    });
  });

  describe("formatDate", () => {
    it("should format Date object", () => {
      const date = new Date("2024-01-15T10:30:00");
      const result = formatDate(date);

      expect(result).toContain("Jan");
      expect(result).toContain("15");
      expect(result).toContain("2024");
    });

    it("should format date string", () => {
      const result = formatDate("2024-01-15T10:30:00");

      expect(result).toContain("Jan");
      expect(result).toContain("15");
    });

    it("should format timestamp number", () => {
      const timestamp = new Date("2024-01-15T12:00:00Z").getTime();
      const result = formatDate(timestamp);

      expect(result).toContain("Jan");
      expect(result).toContain("2024");
    });

    it("should include time in formatted output", () => {
      const date = new Date("2024-01-15T14:30:00");
      const result = formatDate(date);

      // Should include hour and minute
      expect(result).toMatch(/\d{1,2}:\d{2}/);
    });
  });

  describe("formatRelativeTime", () => {
    it('should return "Just now" for recent timestamps', () => {
      const now = new Date();
      const result = formatRelativeTime(now);

      expect(result).toBe("Just now");
    });

    it("should format minutes ago", () => {
      const date = new Date(Date.now() - 5 * 60 * 1000); // 5 minutes ago
      const result = formatRelativeTime(date);

      expect(result).toMatch(/\d+m ago/);
    });

    it("should format hours ago", () => {
      const date = new Date(Date.now() - 3 * 60 * 60 * 1000); // 3 hours ago
      const result = formatRelativeTime(date);

      expect(result).toMatch(/\d+h ago/);
    });

    it("should format days ago", () => {
      const date = new Date(Date.now() - 2 * 24 * 60 * 60 * 1000); // 2 days ago
      const result = formatRelativeTime(date);

      expect(result).toMatch(/\d+d ago/);
    });

    it("should use formatDate for dates older than 7 days", () => {
      const date = new Date(Date.now() - 10 * 24 * 60 * 60 * 1000); // 10 days ago
      const result = formatRelativeTime(date);

      // Should not contain "ago", should be formatted date
      expect(result).not.toContain("ago");
    });

    it("should handle string input", () => {
      const dateString = new Date(Date.now() - 2 * 60 * 1000).toISOString(); // 2 minutes ago
      const result = formatRelativeTime(dateString);

      expect(result).toMatch(/\d+m ago/);
    });

    it("should handle timestamp number", () => {
      const timestamp = Date.now() - 30 * 1000; // 30 seconds ago
      const result = formatRelativeTime(timestamp);

      expect(result).toBe("Just now");
    });
  });

  describe("truncateText", () => {
    it("should truncate text longer than max length", () => {
      const text = "This is a very long text that should be truncated";
      const result = truncateText(text, 20);

      expect(result.length).toBeLessThanOrEqual(23); // 20 + '...'
      expect(result).toContain("...");
    });

    it("should not truncate text shorter than max length", () => {
      const text = "Short text";
      const result = truncateText(text, 20);

      expect(result).toBe(text);
      expect(result).not.toContain("...");
    });

    it("should return original text when equal to max length", () => {
      const text = "12345";
      const result = truncateText(text, 5);

      expect(result).toBe(text);
    });

    it("should handle empty string", () => {
      const result = truncateText("", 10);

      expect(result).toBe("");
    });

    it("should truncate at exact length", () => {
      const text = "Hello World, this is a test";
      const result = truncateText(text, 10);

      expect(result).toBe("Hello Worl...");
    });

    it("should handle max length of 0", () => {
      const text = "Some text";
      const result = truncateText(text, 0);

      expect(result).toBe("...");
    });
  });

  describe("generateId", () => {
    it("should generate a string", () => {
      const id = generateId();

      expect(typeof id).toBe("string");
    });

    it("should generate non-empty id", () => {
      const id = generateId();

      expect(id.length).toBeGreaterThan(0);
    });

    it("should generate unique ids", () => {
      const id1 = generateId();
      const id2 = generateId();
      const id3 = generateId();

      expect(id1).not.toBe(id2);
      expect(id2).not.toBe(id3);
      expect(id1).not.toBe(id3);
    });

    it("should generate alphanumeric id", () => {
      const id = generateId();

      // Should only contain letters and numbers
      expect(id).toMatch(/^[a-z0-9]+$/);
    });

    it("should generate id with reasonable length", () => {
      const id = generateId();

      // Should be around 9 characters
      expect(id.length).toBeGreaterThan(5);
      expect(id.length).toBeLessThan(15);
    });
  });

  describe("debounce", () => {
    beforeEach(() => {
      jest.useFakeTimers();
    });

    afterEach(() => {
      jest.runOnlyPendingTimers();
      jest.useRealTimers();
    });

    it("should delay function execution", () => {
      const func = jest.fn();
      const debouncedFunc = debounce(func, 100);

      debouncedFunc();

      expect(func).not.toHaveBeenCalled();

      jest.advanceTimersByTime(100);

      expect(func).toHaveBeenCalledTimes(1);
    });

    it("should cancel previous call if called again", () => {
      const func = jest.fn();
      const debouncedFunc = debounce(func, 100);

      debouncedFunc();
      jest.advanceTimersByTime(50);
      debouncedFunc();
      jest.advanceTimersByTime(50);

      expect(func).not.toHaveBeenCalled();

      jest.advanceTimersByTime(50);

      expect(func).toHaveBeenCalledTimes(1);
    });

    it("should pass arguments to function", () => {
      const func = jest.fn();
      const debouncedFunc = debounce(func, 100);

      debouncedFunc("arg1", "arg2");

      jest.advanceTimersByTime(100);

      expect(func).toHaveBeenCalledWith("arg1", "arg2");
    });

    it("should handle multiple rapid calls", () => {
      const func = jest.fn();
      const debouncedFunc = debounce(func, 100);

      debouncedFunc();
      debouncedFunc();
      debouncedFunc();
      debouncedFunc();

      jest.advanceTimersByTime(100);

      // Should only call once
      expect(func).toHaveBeenCalledTimes(1);
    });

    it("should work with different wait times", () => {
      const func = jest.fn();
      const debouncedFunc = debounce(func, 500);

      debouncedFunc();

      jest.advanceTimersByTime(400);
      expect(func).not.toHaveBeenCalled();

      jest.advanceTimersByTime(100);
      expect(func).toHaveBeenCalledTimes(1);
    });
  });

  describe("edge cases", () => {
    it("cn should handle null and undefined", () => {
      const result = cn("class1", null, undefined, "class2");

      expect(result).toContain("class1");
      expect(result).toContain("class2");
    });

    it("formatDate should handle invalid date", () => {
      const result = formatDate("invalid-date");

      // Should return some string (might be "Invalid Date")
      expect(typeof result).toBe("string");
    });

    it("truncateText should handle unicode characters", () => {
      const text = "你好世界🌍";
      const result = truncateText(text, 3);

      expect(result.length).toBeLessThanOrEqual(6);
    });
  });
});
