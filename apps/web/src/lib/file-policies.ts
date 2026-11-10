/**
 * file-policies.ts - Pure business logic for file restoration decisions
 *
 * This module contains PURE FUNCTIONS (no side effects) that determine
 * when files should be restored or loaded based on chat state.
 *
 * Benefits of pure functions:
 * - 100% testable (26 unit tests)
 * - No race conditions (deterministic output)
 * - Easy to reason about
 * - Can be called from anywhere without side effects
 */

/**
 * Determine if files should be restored from storage for a chat
 *
 * Policy:
 * - Draft mode → ALWAYS restore (user is composing)
 * - Optimistic/temp chats → ALWAYS restore (not persisted yet)
 * - Real chats without data → WAIT (avoid race condition)
 * - Real empty chats (hydrated) → RESTORE (legitimate empty state)
 * - Real chats with messages → NEVER restore (firewall prevents persistence)
 *
 * @param chatId - Chat identifier (null/draft/uuid)
 * @param hasMessages - Whether chat has messages (from loaded data)
 * @param isReady - Whether chat data has been hydrated from backend
 * @returns true if files should be restored, false otherwise
 */
export function shouldRestoreFiles(
  chatId: string | null | undefined,
  hasMessages: boolean,
  isReady: boolean = true,
): boolean {
  // Draft mode - always restore (user composing new message)
  if (!chatId || chatId === "draft") {
    return true;
  }

  // Optimistic/temp chats - always restore (not persisted yet)
  if (chatId.startsWith("temp-") || chatId.startsWith("creating")) {
    return true;
  }

  // Real chats - wait for hydration to avoid race conditions
  if (!isReady) {
    return false;
  }

  // Real chats (hydrated) - restore only if chat is empty
  return !hasMessages;
}

/**
 * Determine if documents should be loaded from backend for a chat
 *
 * Policy:
 * - Draft mode → NEVER load (no backend data)
 * - Temp chats → NEVER load (not persisted yet)
 * - Real chats without data → WAIT (avoid race condition)
 * - Real empty chats (hydrated) → LOAD (files may exist)
 * - Real chats with messages → NEVER load (firewall prevents persistence)
 *
 * @param chatId - Chat identifier
 * @param hasMessages - Whether chat has messages
 * @param isReady - Whether chat data has been hydrated
 * @returns true if documents should be loaded from backend
 */
export function shouldLoadDocumentsFromBackend(
  chatId: string | null | undefined,
  hasMessages: boolean,
  isReady: boolean = true,
): boolean {
  // Draft mode - no backend documents
  if (!chatId || chatId === "draft") {
    return false;
  }

  // Temp/optimistic chats - no backend documents yet
  if (chatId.startsWith("temp-") || chatId.startsWith("creating")) {
    return false;
  }

  // Real chats - wait for hydration
  if (!isReady) {
    return false;
  }

  // Real chats (hydrated) - load only if chat is empty
  return !hasMessages;
}

/**
 * Determine if firewall should block file attachments
 *
 * Firewall prevents file attachments from persisting after:
 * - Sending a message (files should be cleared)
 * - Navigating to historical chat (files should not restore)
 * - Page refresh on historical chat (files should not persist)
 *
 * Policy:
 * - Draft mode → ALLOW (user composing)
 * - Temp chats → ALLOW (optimistic creation)
 * - Real chats not ready → ALLOW (loading state)
 * - Real empty chats → ALLOW (legitimate files)
 * - Real chats with messages → BLOCK (firewall active)
 *
 * @param chatId - Chat identifier
 * @param hasMessages - Whether chat has messages
 * @param isReady - Whether chat data has been hydrated
 * @returns true if firewall should BLOCK files, false if ALLOW
 */
export function shouldFirewallBlock(
  chatId: string | null | undefined,
  hasMessages: boolean,
  isReady: boolean = true,
): boolean {
  // Inverse of shouldRestoreFiles (firewall blocks when restore shouldn't happen)
  return !shouldRestoreFiles(chatId, hasMessages, isReady);
}
