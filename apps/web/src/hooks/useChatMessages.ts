/**
 * useChatMessages.ts - React Query hook for chat messages
 *
 * This hook is the KEY to eliminating race conditions.
 *
 * How it works:
 * 1. React Query fetches messages from backend and manages caching
 * 2. Synchronizes server data with Zustand chat-store for UI consumption
 * 3. Marks chat as "hydrated" when data arrives (enables file restoration policies)
 *
 * Benefits:
 * - Automatic request deduplication (multiple components can call this for same chat)
 * - Stale-while-revalidate pattern (instant UI updates on navigation)
 * - Eliminates race conditions between file restoration and message loading
 * - Centralized error handling
 */

import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { useChatStore } from "../lib/stores/chat-store";
import { apiClient } from "../lib/api-client";
import type { ChatMessage } from "../lib/types";
import { logDebug, logError } from "../lib/logger";

export function useChatMessages(chatId: string | null) {
  // Zustand store selectors
  const setMessages = useChatStore((state) => state.setMessages);
  const setHydratedStatus = useChatStore((state) => state.setHydratedStatus);
  const setLoading = useChatStore((state) => state.setLoading);

  // React Query manages the server state
  const {
    data: serverMessages,
    isLoading,
    isError,
    error,
  } = useQuery<ChatMessage[]>({
    queryKey: ["chat", chatId, "messages"],

    queryFn: async () => {
      if (!chatId || chatId === "draft") return [];

      logDebug("[useChatMessages] Fetching messages", { chatId });

      try {
        const historyData = await apiClient.getUnifiedChatHistory(
          chatId,
          50,
          0,
          true,
          false,
        );

        // Convert history events to chat messages
        const messages: ChatMessage[] = [];

        for (const event of historyData.events) {
          if (event.event_type === "chat_message" && event.chat_data) {
            // Merge file data into metadata for UI compatibility
            const enrichedMetadata: Record<string, any> = {
              ...(event.chat_data.metadata || {}),
            };

            if (
              event.chat_data.file_ids &&
              event.chat_data.file_ids.length > 0
            ) {
              enrichedMetadata.file_ids = event.chat_data.file_ids;
            }
            if (event.chat_data.files && event.chat_data.files.length > 0) {
              enrichedMetadata.files = event.chat_data.files;
            }

            messages.push({
              id: event.chat_data.id,
              content: event.chat_data.content,
              role: event.chat_data.role as "user" | "assistant" | "system",
              timestamp: event.chat_data.timestamp || event.created_at,
              status: "delivered",
              metadata: enrichedMetadata,
              model: event.chat_data.model,
              tokens: event.chat_data.tokens,
              latency: event.chat_data.latency_ms,
            });
          }
        }

        return messages;
      } catch (err) {
        logError("[useChatMessages] Failed to fetch messages", err);
        throw err;
      }
    },

    // Only run query for real chats (not draft/temp)
    enabled:
      !!chatId &&
      chatId !== "draft" &&
      !chatId.startsWith("temp-") &&
      !chatId.startsWith("creating"),

    // Cache configuration
    staleTime: 30 * 1000, // 30 seconds (messages can change frequently)
    gcTime: 5 * 60 * 1000, // Keep in cache for 5 minutes after unmount
  });

  // Hidratar Zustand desde RQ UNA sola vez por chatId (no en cada refetch).
  //
  // Antes: este efecto corría en cada cambio de `serverMessages` y usaba
  // heurísticas (hasStreamingMessage / "preserve si hay optimistic") para
  // adivinar si ganaba RQ o el estado local. Eso competía además con
  // `chat-store.loadUnifiedHistory` (invocado por ChatView tras cada
  // `switchChat`), que hidrata la MISMA data por un camino distinto — dos
  // escritores de historial corriendo en paralelo sobre el mismo store.
  //
  // Ahora: `hydratedByChatId` (que switchChat ya invalida al cambiar de chat)
  // es el único árbitro. El primero en resolver -RQ o loadUnifiedHistory- fija
  // los mensajes y marca hydrated=true; el otro ve la bandera en true y no
  // hace nada. Tras la hidratación, Zustand manda solo: el envío optimista y
  // el streaming (useOptimizedChat) actualizan el store directamente sin que
  // ningún refetch de RQ pueda pisarlos.
  useEffect(() => {
    if (serverMessages === undefined) return;
    if (!chatId || chatId === "draft") return;

    if (useChatStore.getState().hydratedByChatId[chatId]) return;

    logDebug("[useChatMessages] Hydrating Zustand from RQ (one-time)", {
      chatId,
      count: serverMessages.length,
    });

    setMessages(serverMessages);
    setHydratedStatus(chatId, true);
  }, [serverMessages, chatId, setMessages, setHydratedStatus]);

  // Handle draft/temp/null chats (no backend fetch needed) - MUST run before loading sync
  useEffect(() => {
    const isDraftOrTemp =
      !chatId ||
      chatId === "draft" ||
      chatId.startsWith("temp-") ||
      chatId.startsWith("creating");

    if (isDraftOrTemp) {
      // ⚠️ CRITICAL FIX: Only clear messages if transitioning FROM a real chat TO draft/temp
      // DO NOT clear messages during optimistic creation flow (temp → real ID transition)
      // This preserves optimistic user messages and streaming assistant responses
      const currentMessages = useChatStore.getState().messages;
      if (currentMessages.length === 0) {
        setMessages([]);
      }

      setLoading(false); // Ensure loading is false for draft/temp/null
      if (chatId && chatId !== "draft") {
        setHydratedStatus(chatId, true);
      }

      logDebug("[useChatMessages] Draft/temp/null chat - skipping fetch", {
        chatId,
        preservingMessages: currentMessages.length > 0,
      });
    }
  }, [chatId, setMessages, setHydratedStatus, setLoading]);

  // Synchronize loading state for real chats
  useEffect(() => {
    const isDraftOrTemp =
      !chatId ||
      chatId === "draft" ||
      chatId.startsWith("temp-") ||
      chatId.startsWith("creating");

    // Only sync loading state for real chats (not draft/temp/null)
    if (!isDraftOrTemp) {
      setLoading(isLoading);
    }
  }, [isLoading, setLoading, chatId]);

  return {
    messages: serverMessages ?? [],
    isLoading,
    isError,
    error,
  };
}
