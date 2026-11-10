/**
 * Tests for retry.ts - Exponential backoff retry logic
 *
 * Coverage:
 * - retryWithBackoff: Success/failure scenarios, custom retry logic
 * - calculateBackoff: Exponential delay with jitter
 * - Error detection: isNetworkError, isServerError
 * - withRetry HOF: Function wrapping
 */

import {
  retryWithBackoff,
  withRetry,
  isNetworkError,
  isServerError,
  defaultShouldRetry,
  type RetryOptions,
} from "../retry";

// Mock timers for controlled testing
jest.useFakeTimers();

describe("retry.ts", () => {
  afterEach(() => {
    jest.clearAllTimers();
  });

  describe("retryWithBackoff", () => {
    it("succeeds on first attempt", async () => {
      const fn = jest.fn().mockResolvedValue("success");

      const result = await retryWithBackoff(fn);

      expect(result).toBe("success");
      expect(fn).toHaveBeenCalledTimes(1);
    });

    it("succeeds after retries", async () => {
      const fn = jest
        .fn()
        .mockRejectedValueOnce(new Error("Fail 1"))
        .mockRejectedValueOnce(new Error("Fail 2"))
        .mockResolvedValueOnce("success");

      const promise = retryWithBackoff(fn, { baseDelay: 100, maxRetries: 3 });

      // Fast-forward through delays
      await jest.runAllTimersAsync();

      const result = await promise;

      expect(result).toBe("success");
      expect(fn).toHaveBeenCalledTimes(3);
    });

    it("throws error after max retries", async () => {
      jest.useRealTimers(); // Use real timers for this test

      const error = new Error("Persistent failure");
      const fn = jest.fn().mockRejectedValue(error);

      const promise = retryWithBackoff(fn, { baseDelay: 10, maxRetries: 2 });

      await expect(promise).rejects.toThrow("Persistent failure");
      expect(fn).toHaveBeenCalledTimes(3); // Initial + 2 retries

      jest.useFakeTimers(); // Restore fake timers
    });

    it("respects shouldRetry predicate", async () => {
      const error = new Error("Non-retryable");
      const fn = jest.fn().mockRejectedValue(error);

      const shouldRetry = jest.fn().mockReturnValue(false);

      const promise = retryWithBackoff(fn, {
        maxRetries: 3,
        shouldRetry,
      });

      await expect(promise).rejects.toThrow("Non-retryable");
      expect(fn).toHaveBeenCalledTimes(1); // No retries
      expect(shouldRetry).toHaveBeenCalledWith(error, 0);
    });

    it("calls onRetry callback with correct parameters", async () => {
      const fn = jest
        .fn()
        .mockRejectedValueOnce(new Error("Fail 1"))
        .mockResolvedValueOnce("success");

      const onRetry = jest.fn();

      const promise = retryWithBackoff(fn, {
        baseDelay: 1000,
        onRetry,
      });

      await jest.runAllTimersAsync();
      await promise;

      expect(onRetry).toHaveBeenCalledTimes(1);
      expect(onRetry).toHaveBeenCalledWith(
        expect.objectContaining({ message: "Fail 1" }),
        1, // Attempt number
        expect.any(Number), // Delay with jitter
      );
    });

    it("uses exponential backoff with jitter", async () => {
      const fn = jest
        .fn()
        .mockRejectedValueOnce(new Error("Fail 1"))
        .mockRejectedValueOnce(new Error("Fail 2"))
        .mockResolvedValueOnce("success");

      const onRetry = jest.fn();

      const promise = retryWithBackoff(fn, {
        baseDelay: 1000,
        maxDelay: 10000,
        onRetry,
      });

      await jest.runAllTimersAsync();
      await promise;

      expect(onRetry).toHaveBeenCalledTimes(2);

      // First retry: ~1000ms * 2^0 + jitter = ~1000-2000ms
      const firstDelay = onRetry.mock.calls[0][2];
      expect(firstDelay).toBeGreaterThanOrEqual(1000);
      expect(firstDelay).toBeLessThan(3000);

      // Second retry: ~1000ms * 2^1 + jitter = ~2000-3000ms
      const secondDelay = onRetry.mock.calls[1][2];
      expect(secondDelay).toBeGreaterThanOrEqual(2000);
      expect(secondDelay).toBeLessThan(5000);
    });

    it("caps delay at maxDelay", async () => {
      const fn = jest
        .fn()
        .mockRejectedValueOnce(new Error("Fail"))
        .mockResolvedValueOnce("success");

      const onRetry = jest.fn();

      // With baseDelay=5000 and attempt=3, exponential would be huge
      // But maxDelay should cap it
      const promise = retryWithBackoff(fn, {
        baseDelay: 5000,
        maxDelay: 6000,
        onRetry,
      });

      await jest.runAllTimersAsync();
      await promise;

      const delay = onRetry.mock.calls[0][2];
      expect(delay).toBeLessThanOrEqual(6000);
    });
  });

  describe("withRetry", () => {
    it("wraps function with retry logic", async () => {
      const originalFn = jest
        .fn()
        .mockRejectedValueOnce(new Error("Fail"))
        .mockResolvedValueOnce("success");

      const retryableFn = withRetry(originalFn, { baseDelay: 100 });

      const promise = retryableFn();

      await jest.runAllTimersAsync();
      const result = await promise;

      expect(result).toBe("success");
      expect(originalFn).toHaveBeenCalledTimes(2);
    });

    it("passes arguments correctly", async () => {
      const originalFn = jest
        .fn()
        .mockImplementation((a: number, b: string) =>
          Promise.resolve(`${a}-${b}`),
        );

      const retryableFn = withRetry(originalFn, { maxRetries: 1 });

      const result = await retryableFn(42, "test");

      expect(result).toBe("42-test");
      expect(originalFn).toHaveBeenCalledWith(42, "test");
    });

    it("retries with same arguments", async () => {
      const originalFn = jest
        .fn()
        .mockRejectedValueOnce(new Error("Fail"))
        .mockResolvedValueOnce("success");

      const retryableFn = withRetry(originalFn, { baseDelay: 100 });

      const promise = retryableFn("arg1", "arg2");

      await jest.runAllTimersAsync();
      await promise;

      expect(originalFn).toHaveBeenCalledTimes(2);
      expect(originalFn).toHaveBeenNthCalledWith(1, "arg1", "arg2");
      expect(originalFn).toHaveBeenNthCalledWith(2, "arg1", "arg2");
    });
  });

  describe("Error Detection", () => {
    describe("isNetworkError", () => {
      it("detects network errors", () => {
        expect(isNetworkError(new Error("Network request failed"))).toBe(true);
        expect(isNetworkError(new Error("fetch failed"))).toBe(true);
        expect(isNetworkError(new Error("timeout"))).toBe(true);
        expect(isNetworkError(new Error("ECONNREFUSED"))).toBe(true);
        expect(isNetworkError(new Error("ENOTFOUND"))).toBe(true);
      });

      it("rejects non-network errors", () => {
        expect(isNetworkError(new Error("Validation failed"))).toBe(false);
        expect(isNetworkError(new Error("Not found"))).toBe(false);
      });
    });

    describe("isServerError", () => {
      it("detects 5xx server errors", () => {
        expect(isServerError({ status: 500 })).toBe(true);
        expect(isServerError({ status: 502 })).toBe(true);
        expect(isServerError({ status: 503 })).toBe(true);
        expect(isServerError({ status: 599 })).toBe(true);
      });

      it("rejects non-5xx errors", () => {
        expect(isServerError({ status: 400 })).toBe(false);
        expect(isServerError({ status: 404 })).toBe(false);
        expect(isServerError({ status: 200 })).toBe(false);
        expect(isServerError({})).toBe(false);
        expect(isServerError(null)).toBe(false);
      });
    });

    describe("defaultShouldRetry", () => {
      it("retries on network errors", () => {
        expect(defaultShouldRetry(new Error("Network failed"))).toBe(true);
      });

      it("retries on server errors", () => {
        const serverError = new Error("Server error");
        (serverError as any).status = 503;
        expect(defaultShouldRetry(serverError)).toBe(true);
      });

      it("does not retry on client errors", () => {
        expect(defaultShouldRetry(new Error("Validation failed"))).toBe(false);
      });
    });
  });

  describe("Edge Cases", () => {
    it("handles zero maxRetries", async () => {
      const fn = jest.fn().mockRejectedValue(new Error("Fail"));

      const promise = retryWithBackoff(fn, { maxRetries: 0 });

      await expect(promise).rejects.toThrow("Fail");
      expect(fn).toHaveBeenCalledTimes(1);
    });

    it("handles undefined error", async () => {
      jest.useRealTimers();

      const fn = jest.fn().mockRejectedValue(undefined);

      const promise = retryWithBackoff(fn, { maxRetries: 1, baseDelay: 10 });

      // Check that promise rejects (with any value including undefined)
      await expect(promise).rejects.toBe(undefined);

      jest.useFakeTimers();
    });

    it("handles shouldRetry returning false on first attempt", async () => {
      const fn = jest.fn().mockRejectedValue(new Error("Fail"));

      const promise = retryWithBackoff(fn, {
        shouldRetry: () => false,
      });

      await expect(promise).rejects.toThrow("Fail");
      expect(fn).toHaveBeenCalledTimes(1);
    });
  });
});
