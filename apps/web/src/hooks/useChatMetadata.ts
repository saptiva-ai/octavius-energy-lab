/**
 * useChatMetadata.ts - Single Source of Truth for chat metadata
 *
 * This hook replaces distributed state management across:
 * - filesStore.chatsWithMessages (localStorage)
 * - messages.length checks (component state)
 * - hasMessages useMemo calculations (computed state)
 * - chatHasMessages() function calls (async queries)
 *
 * Benefits:
 * - Centralized metadata (hasMessages, isReady, isLoading)
 * - Consistent data across all components
 * - Eliminates race conditions from async data loading
 * - Enables file restoration policies to wait for data hydration
 */

import { useMemo } from "react";
import { useChatStore } from "../lib/stores/chat-store";

export interface ChatMetadata {
  /** Whether chat has any messages (from loaded data) */
  hasMessages: boolean;
  /** Number of messages in chat */
  messageCount: number;
  /** Whether chat is empty (no messages and not loading) */
  isEmpty: boolean;
  /** Whether data is currently loading */
  isLoading: boolean;
  /** Whether chat data has been hydrated from backend (ready for policies) */
  isReady: boolean;
}

/**
 * Get centralized metadata for a chat
 *
 * @param chatId - Chat ID to get metadata for (null/draft = always ready)
 * @returns Chat metadata object
 *
 * @example
 * ```tsx
 * function ChatComponent({ chatId }: { chatId: string | null }) {
 *   const { hasMessages, isReady } = useChatMetadata(chatId);
 *
 *   // Use in file restoration policy
 *   const shouldRestore = shouldRestoreFiles(chatId, hasMessages, isReady);
 *
 *   // Or use directly
 *   if (!isReady) return <Loading />;
 *   if (isEmpty) return <EmptyState />;
 * }
 * ```
 */
export function useChatMetadata(chatId: string | null): ChatMetadata {
  const messages = useChatStore((state) => state.messages);
  const isLoading = useChatStore((state) => state.isLoading);
  const hydratedByChatId = useChatStore((state) => state.hydratedByChatId);

  // Draft/temp chats are always "ready" (no backend data to wait for)
  const isReady = useMemo(() => {
    if (!chatId || chatId === "draft") return true;
    if (chatId.startsWith("temp-") || chatId.startsWith("creating"))
      return true;
    return hydratedByChatId[chatId] === true;
  }, [chatId, hydratedByChatId]);

  const hasMessages = useMemo(() => messages.length > 0, [messages.length]);

  const isEmpty = useMemo(
    () => !isLoading && messages.length === 0,
    [isLoading, messages.length],
  );

  return {
    hasMessages,
    messageCount: messages.length,
    isEmpty,
    isLoading,
    isReady,
  };
}
