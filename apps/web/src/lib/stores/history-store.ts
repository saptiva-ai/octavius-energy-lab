/**
 * History State Store
 *
 * Manages conversation history and sessions:
 * - List of chat sessions
 * - CRUD operations (create, rename, pin, delete)
 * - Optimistic updates for better UX
 * - Cross-tab synchronization
 */

import { create } from "zustand";
import { devtools } from "zustand/middleware";
import toast from "react-hot-toast";
import { ChatSession, ChatSessionOptimistic } from "../types";
import { apiClient } from "../api-client";
import { logDebug, logError, logWarn } from "../logger";
import { retryWithBackoff, defaultShouldRetry } from "../retry";
import { getSyncInstance } from "../sync";
import { createDefaultToolsState, normalizeToolsState } from "../tool-mapping";

const mergeToolsState = (seed?: Record<string, boolean>) => {
  const extraKeys = seed ? Object.keys(seed) : [];
  const base = createDefaultToolsState(extraKeys);
  return seed ? { ...base, ...seed } : base;
};

interface HistoryState {
  // State
  chatSessions: ChatSession[];
  chatSessionsLoading: boolean;
  isCreatingConversation: boolean;
  pendingCreationId: string | null;

  // Actions
  loadChatSessions: () => Promise<void>;
  addChatSession: (session: ChatSession) => void;
  removeChatSession: (chatId: string) => void;
  renameChatSession: (chatId: string, newTitle: string) => Promise<void>;
  pinChatSession: (chatId: string) => Promise<void>;
  deleteChatSession: (chatId: string) => Promise<void>;
  updateSessionTitle: (chatId: string, newTitle: string) => void;

  // Optimistic conversation creation (P0-UX-HIST-001)
  createConversationOptimistic: (
    tempId?: string,
    createdAt?: string,
    idempotencyKey?: string,
    selectedModel?: string,
    draftTools?: Record<string, boolean>,
  ) => string;
  reconcileConversation: (tempId: string, realSession: ChatSession) => void;
  removeOptimisticConversation: (tempId: string) => void;
  finalizeCreation: (tempId: string) => void;
  cancelCreation: (tempId: string) => void;

  clearAllData: () => void;
}

export const useHistoryStore = create<HistoryState>()(
  devtools(
    (set, get) => ({
      // Initial state
      chatSessions: [],
      chatSessionsLoading: false,
      isCreatingConversation: false,
      pendingCreationId: null,

      // Actions
      loadChatSessions: async () => {
        try {
          set({ chatSessionsLoading: true });
          const response = await apiClient.getChatSessions();
          const sessions: ChatSession[] = response?.sessions || [];

          let mergedSessions: ChatSession[] = sessions;
          let pendingCreationId = get().pendingCreationId;
          let isCreatingConversation = get().isCreatingConversation;

          if (pendingCreationId) {
            const pendingSession = get().chatSessions.find(
              (session) =>
                session.id === pendingCreationId &&
                (session as ChatSessionOptimistic).isOptimistic,
            );

            if (pendingSession) {
              mergedSessions = [
                pendingSession,
                ...sessions.filter(
                  (session) => session.id !== pendingCreationId,
                ),
              ];
            } else {
              pendingCreationId = null;
              isCreatingConversation = false;
            }
          }

          set({
            chatSessions: mergedSessions,
            chatSessionsLoading: false,
            pendingCreationId,
            isCreatingConversation,
          });
        } catch (error) {
          logError("Failed to load chat sessions:", error);
          set({ chatSessions: [], chatSessionsLoading: false });
        }
      },

      addChatSession: (session) => {
        set((state) => {
          const existing = state.chatSessions.filter(
            (s) => s.id !== session.id,
          );
          return {
            chatSessions: [session, ...existing],
            pendingCreationId:
              state.pendingCreationId === session.id
                ? null
                : state.pendingCreationId,
            isCreatingConversation:
              state.pendingCreationId === session.id
                ? false
                : state.isCreatingConversation,
          };
        });

        // Broadcast to other tabs
        getSyncInstance().broadcast("session_created", { session });
      },

      removeChatSession: (chatId) =>
        set((state) => ({
          chatSessions: state.chatSessions.filter(
            (session) => session.id !== chatId,
          ),
        })),

      renameChatSession: async (chatId: string, newTitle: string) => {
        const previousSessions = get().chatSessions;

        try {
          // Optimistic update
          set((state) => ({
            chatSessions: state.chatSessions.map((session) =>
              session.id === chatId ? { ...session, title: newTitle } : session,
            ),
          }));

          // Retry with exponential backoff
          await retryWithBackoff(
            () => apiClient.renameChatSession(chatId, newTitle),
            {
              maxRetries: 3,
              baseDelay: 1000,
              shouldRetry: defaultShouldRetry,
              onRetry: (error, attempt, delay) => {
                logWarn(`Retrying rename (attempt ${attempt})`, {
                  chatId,
                  delay,
                  error: error.message,
                });
                toast.loading(`Reintentando renombrar... (${attempt}/3)`, {
                  id: `rename-retry-${chatId}`,
                  duration: delay,
                });
              },
            },
          );

          // Success toast
          toast.success("Conversación renombrada", {
            id: `rename-retry-${chatId}`,
          });
          logDebug("Chat session renamed", { chatId, newTitle });

          // Broadcast to other tabs
          getSyncInstance().broadcast("session_renamed", { chatId });
        } catch (error) {
          logError("Failed to rename chat session:", error);

          // Rollback optimistic update
          set({ chatSessions: previousSessions });

          // Error toast
          toast.error("Error al renombrar la conversación", {
            id: `rename-retry-${chatId}`,
            duration: 5000,
          });

          throw error;
        }
      },

      pinChatSession: async (chatId: string) => {
        const previousSessions = get().chatSessions;
        const session = previousSessions.find((s) => s.id === chatId);
        const newPinnedState = !session?.pinned;

        try {
          // Optimistic update
          set((state) => ({
            chatSessions: state.chatSessions.map((s) =>
              s.id === chatId ? { ...s, pinned: newPinnedState } : s,
            ),
          }));

          // Retry with exponential backoff
          await retryWithBackoff(
            () => apiClient.pinChatSession(chatId, newPinnedState),
            {
              maxRetries: 3,
              baseDelay: 1000,
              shouldRetry: defaultShouldRetry,
              onRetry: (error, attempt, delay) => {
                logWarn(`Retrying pin (attempt ${attempt})`, {
                  chatId,
                  delay,
                  error: error.message,
                });
                toast.loading(`Reintentando... (${attempt}/3)`, {
                  id: `pin-retry-${chatId}`,
                  duration: delay,
                });
              },
            },
          );

          // Success toast
          toast.success(
            newPinnedState ? "Conversación fijada" : "Conversación desfijada",
            {
              id: `pin-retry-${chatId}`,
              duration: 2000,
            },
          );
          logDebug("Chat session pin toggled", {
            chatId,
            pinned: newPinnedState,
          });

          // Broadcast to other tabs
          getSyncInstance().broadcast("session_pinned", { chatId });
        } catch (error) {
          logError("Failed to pin chat session:", error);

          // Rollback optimistic update
          set({ chatSessions: previousSessions });

          // Error toast
          toast.error("Error al fijar la conversación", {
            id: `pin-retry-${chatId}`,
            duration: 4000,
          });

          throw error;
        }
      },

      deleteChatSession: async (chatId: string) => {
        const previousSessions = get().chatSessions;

        try {
          // Optimistic update
          set((state) => ({
            chatSessions: state.chatSessions.filter(
              (session) => session.id !== chatId,
            ),
          }));

          // Retry with exponential backoff
          await retryWithBackoff(() => apiClient.deleteChatSession(chatId), {
            maxRetries: 3,
            baseDelay: 1000,
            shouldRetry: defaultShouldRetry,
            onRetry: (error, attempt, delay) => {
              logWarn(`Retrying delete (attempt ${attempt})`, {
                chatId,
                delay,
                error: error.message,
              });
              toast.loading(`Reintentando eliminar... (${attempt}/3)`, {
                id: `delete-retry-${chatId}`,
                duration: delay,
              });
            },
          });

          // Success toast
          toast.success("Conversación eliminada", {
            id: `delete-retry-${chatId}`,
            duration: 3000,
          });
          logDebug("Chat session deleted", { chatId });

          // Broadcast to other tabs
          getSyncInstance().broadcast("session_deleted", { chatId });
        } catch (error) {
          logError("Failed to delete chat session:", error);

          // Rollback optimistic update
          set({ chatSessions: previousSessions });

          // Error toast
          toast.error("Error al eliminar la conversación", {
            id: `delete-retry-${chatId}`,
            duration: 5000,
          });

          throw error;
        }
      },

      updateSessionTitle: (chatId: string, newTitle: string) => {
        set((state) => ({
          chatSessions: state.chatSessions.map((session) =>
            session.id === chatId
              ? {
                  ...session,
                  title: newTitle,
                  updated_at: new Date().toISOString(),
                }
              : session,
          ),
        }));

        logDebug("Optimistically updated session title", { chatId, newTitle });
      },

      // P0-UX-HIST-001: Optimistic conversation creation
      createConversationOptimistic: (
        providedTempId?: string,
        providedCreatedAt?: string,
        providedIdempotencyKey?: string,
        selectedModel?: string,
        draftTools?: Record<string, boolean>,
      ) => {
        const generatedKey =
          typeof crypto !== "undefined" && "randomUUID" in crypto
            ? crypto.randomUUID()
            : `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
        const idempotencyKey = providedIdempotencyKey || generatedKey;
        const tempId = providedTempId || `temp-${idempotencyKey}`;
        const now = providedCreatedAt || new Date().toISOString();

        const optimisticSession: ChatSessionOptimistic = {
          id: tempId,
          tempId,
          title: "Nueva conversación",
          created_at: now,
          updated_at: now,
          first_message_at: null,
          last_message_at: null,
          message_count: 0,
          model: selectedModel || "turbo",
          preview: "",
          isOptimistic: true,
          isNew: true,
          pending: true,
          state: "creating",
          idempotency_key: idempotencyKey,
          tools_enabled: mergeToolsState(draftTools),
        };

        set((state) => {
          const withoutDuplicate = state.chatSessions.filter(
            (session) => session.id !== tempId,
          );
          return {
            chatSessions: [optimisticSession, ...withoutDuplicate],
            isCreatingConversation: true,
            pendingCreationId: tempId,
          };
        });

        logDebug("Created optimistic conversation", { tempId });
        return tempId;
      },

      finalizeCreation: (tempId: string) => {
        set((state) => {
          const idx = state.chatSessions.findIndex(
            (session) => session.id === tempId,
          );
          if (idx === -1) {
            return state;
          }

          const session = state.chatSessions[idx] as ChatSessionOptimistic;
          if (!session.isOptimistic || session.pending === false) {
            return state;
          }

          const updatedSession: ChatSessionOptimistic = {
            ...session,
            pending: false,
            state: session.state === "creating" ? "draft" : session.state,
            isNew: session.isNew ?? true,
          };

          const nextSessions = [...state.chatSessions];
          nextSessions[idx] = updatedSession;

          return {
            chatSessions: nextSessions,
          };
        });

        logDebug("Finalized optimistic conversation", { tempId });
      },

      cancelCreation: (tempId: string) => {
        logWarn("Cancelling optimistic conversation", { tempId });
        get().removeOptimisticConversation(tempId);
      },

      reconcileConversation: (tempId: string, realSession: ChatSession) => {
        set((state) => {
          const filteredSessions = state.chatSessions.filter(
            (session) => session.id !== tempId && session.id !== realSession.id,
          );

          const hydratedSession: ChatSessionOptimistic = {
            ...realSession,
            isOptimistic: false,
            isNew: true,
            pending: false,
          };

          return {
            chatSessions: [hydratedSession, ...filteredSessions],
            isCreatingConversation:
              state.pendingCreationId === tempId
                ? false
                : state.isCreatingConversation,
            pendingCreationId:
              state.pendingCreationId === tempId
                ? null
                : state.pendingCreationId,
          };
        });

        // Broadcast to other tabs
        getSyncInstance().broadcast("session_created", {
          session: realSession,
        });

        logDebug("Reconciled optimistic conversation", {
          tempId,
          realId: realSession.id,
        });

        // Clear highlight after subtle delay
        setTimeout(() => {
          set((state) => ({
            chatSessions: state.chatSessions.map((session) =>
              session.id === realSession.id
                ? { ...session, isNew: false }
                : session,
            ),
          }));
        }, 2000);
      },

      removeOptimisticConversation: (tempId: string) => {
        set((state) => {
          const filteredSessions = state.chatSessions.filter(
            (session) => session.id !== tempId,
          );
          const wasPending = state.pendingCreationId === tempId;
          return {
            chatSessions: filteredSessions,
            isCreatingConversation: wasPending
              ? false
              : state.isCreatingConversation,
            pendingCreationId: wasPending ? null : state.pendingCreationId,
          };
        });

        logDebug("Removed optimistic conversation", { tempId });
      },

      clearAllData: () => {
        set({
          chatSessions: [],
          chatSessionsLoading: false,
          pendingCreationId: null,
          isCreatingConversation: false,
        });
      },
    }),
    {
      name: "history-store",
    },
  ),
);
