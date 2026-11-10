/**
 * SSE (Server-Sent Events) mock helper for Playwright E2E tests.
 *
 * Builds a standards-compliant SSE response body from an array of
 * event/data objects, suitable for use with page.route().
 */

export interface SSEEvent {
  event: string;
  data: unknown;
}

/**
 * Convert an array of SSE events into a valid text/event-stream body.
 *
 * Each event becomes:
 *   event: <name>\ndata: <json>\n\n
 */
export function createSSEResponse(chunks: SSEEvent[]): string {
  return chunks
    .map(
      (chunk) =>
        `event: ${chunk.event}\ndata: ${JSON.stringify(chunk.data)}\n\n`,
    )
    .join("");
}

/**
 * Build SSE response headers for a mocked route.
 */
export function sseHeaders(): Record<string, string> {
  return {
    "Content-Type": "text/event-stream",
    "Cache-Control": "no-cache",
    Connection: "keep-alive",
  };
}

/**
 * Create a delayed SSE response that streams chunks progressively.
 *
 * Returns chunks with small delays between them to simulate real streaming.
 * Use with `route.fulfill()` — note that Playwright's fulfill sends the
 * body at once, but the event format still exercises the SSE parser.
 */
export function createDelayedSSEResponse(
  chunks: SSEEvent[],
  _delayMs = 50,
): string {
  // In Playwright route.fulfill(), we can't truly stream with delays,
  // but we produce a valid SSE body that exercises the frontend parser.
  return createSSEResponse(chunks);
}
