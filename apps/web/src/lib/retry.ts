import { logDebug } from "@/lib/logger";
/**
 * Retry Logic with Exponential Backoff + Jitter
 *
 * Implements a robust retry mechanism for failed operations:
 * - Exponential backoff: 2^attempt * baseDelay
 * - Jitter: Random delay to prevent thundering herd
 * - Max retries: Configurable (default 3)
 * - Max delay: Cap to prevent infinite waiting
 */

export interface RetryOptions {
  /**
   * Maximum number of retry attempts
   * @default 3
   */
  maxRetries?: number;

  /**
   * Base delay in milliseconds for exponential backoff
   * @default 1000
   */
  baseDelay?: number;

  /**
   * Maximum delay in milliseconds
   * @default 10000
   */
  maxDelay?: number;

  /**
   * Custom function to determine if error is retryable
   * @default () => true
   */
  shouldRetry?: (error: Error, attempt: number) => boolean;

  /**
   * Callback for each retry attempt
   */
  onRetry?: (error: Error, attempt: number, nextDelay: number) => void;
}

/**
 * Calculate exponential backoff delay with jitter
 *
 * Formula: min(maxDelay, baseDelay * 2^attempt + random(0, 1000))
 *
 * @param attempt - Current attempt number (0-indexed)
 * @param baseDelay - Base delay in ms
 * @param maxDelay - Maximum delay cap in ms
 * @returns Delay in milliseconds
 */
function calculateBackoff(
  attempt: number,
  baseDelay: number,
  maxDelay: number,
): number {
  // Exponential: 2^attempt * baseDelay
  const exponentialDelay = baseDelay * Math.pow(2, attempt);

  // Add jitter: random 0-1000ms to prevent thundering herd
  const jitter = Math.random() * 1000;

  // Cap at maxDelay
  return Math.min(maxDelay, exponentialDelay + jitter);
}

/**
 * Sleep utility
 */
function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Retry an async operation with exponential backoff
 *
 * @param fn - Async function to retry
 * @param options - Retry configuration
 * @returns Promise resolving to fn's result
 * @throws Last error if all retries fail
 *
 * @example
 * ```typescript
 * const result = await retryWithBackoff(
 *   async () => apiClient.updateChat(id, data),
 *   {
 *     maxRetries: 3,
 *     baseDelay: 1000,
 *     onRetry: (err, attempt, delay) => {
 *       logDebug(`Retry ${attempt} after ${delay}ms: ${err.message}`)
 *     }
 *   }
 * )
 * ```
 */
export async function retryWithBackoff<T>(
  fn: () => Promise<T>,
  options: RetryOptions = {},
): Promise<T> {
  const {
    maxRetries = 3,
    baseDelay = 1000,
    maxDelay = 10000,
    shouldRetry = () => true,
    onRetry,
  } = options;

  let lastError: Error;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      // Execute function
      return await fn();
    } catch (error) {
      lastError = error as Error;

      // If this is the last attempt, throw
      if (attempt >= maxRetries) {
        throw lastError;
      }

      // Check if error is retryable
      if (!shouldRetry(lastError, attempt)) {
        throw lastError;
      }

      // Calculate backoff delay
      const delay = calculateBackoff(attempt, baseDelay, maxDelay);

      // Notify callback
      if (onRetry) {
        onRetry(lastError, attempt + 1, delay);
      }

      // Wait before retrying
      await sleep(delay);
    }
  }

  // This should never be reached, but TypeScript needs it
  throw lastError!;
}

/**
 * Check if error is a network error (retryable)
 */
export function isNetworkError(error: Error): boolean {
  const message = error.message.toLowerCase();
  return (
    message.includes("network") ||
    message.includes("fetch") ||
    message.includes("timeout") ||
    message.includes("econnrefused") ||
    message.includes("enotfound")
  );
}

/**
 * Check if error is a server error (5xx, retryable)
 */
export function isServerError(error: any): boolean {
  return error?.status >= 500 && error?.status < 600;
}

/**
 * Default retry predicate: retry on network/server errors
 */
export function defaultShouldRetry(error: Error): boolean {
  return isNetworkError(error) || isServerError(error);
}

/**
 * Create a retryable version of an async function
 *
 * @example
 * ```typescript
 * const retryableUpdate = withRetry(
 *   (id: string, data: any) => apiClient.updateChat(id, data),
 *   { maxRetries: 3 }
 * )
 *
 * await retryableUpdate('chat-123', { title: 'New Title' })
 * ```
 */
export function withRetry<Args extends any[], Result>(
  fn: (...args: Args) => Promise<Result>,
  options: RetryOptions = {},
): (...args: Args) => Promise<Result> {
  return async (...args: Args) => {
    return retryWithBackoff(() => fn(...args), options);
  };
}
