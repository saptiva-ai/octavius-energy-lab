/**
 * Draft Conversation State Store
 *
 * Manages draft conversations using Progressive Commitment Pattern:
 * - Memory-only state (no backend persistence)
 * - Auto-cleanup after timeout
 * - Upgrades to real conversation on first message
 */

import { create } from "zustand";
import { devtools } from "zustand/middleware";
import { DraftConversation, INITIAL_DRAFT_STATE } from "../conversation-utils";
import { logAction, logDebug } from "../logger";
import { createDefaultToolsState, normalizeToolsState } from "../tool-mapping";

const mergeToolsState = (seed?: Record<string, boolean>) => {
  const extraKeys = seed ? Object.keys(seed) : [];
  const base = createDefaultToolsState(extraKeys);
  return seed ? { ...base, ...seed } : base;
};

interface DraftState {
  // State
  draft: DraftConversation;
  draftToolsEnabled: Record<string, boolean>;

  // Actions
  openDraft: (selectedModel: string) => void;
  discardDraft: () => void;
  setDraftText: (text: string) => void;
  isDraftMode: () => boolean;
  getDraftCid: () => string | null;
  updateDraftTools: (tools: Record<string, boolean>) => void;
  clearAllData: () => void;
}

export const useDraftStore = create<DraftState>()(
  devtools(
    (set, get) => ({
      // Initial state
      draft: INITIAL_DRAFT_STATE,
      draftToolsEnabled: mergeToolsState(),

      // Actions
      openDraft: (selectedModel: string) => {
        const state = get();

        // Clear any existing cleanup timer
        if (state.draft.cleanupTimerId) {
          clearTimeout(state.draft.cleanupTimerId);
        }

        // Generate client ID for idempotency
        const cid =
          typeof crypto !== "undefined" && "randomUUID" in crypto
            ? crypto.randomUUID()
            : `draft-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;

        const startedAt = Date.now();

        // Auto-cleanup after 2.5s if no message is sent
        const DRAFT_TIMEOUT_MS = 2500;
        const cleanupTimerId = window.setTimeout(() => {
          const currentState = get();
          // Only cleanup if still in draft mode and same cid
          if (
            currentState.draft.isDraftMode &&
            currentState.draft.cid === cid
          ) {
            logAction("chat.draft.cleaned", {
              cid,
              durationMs: Date.now() - startedAt,
              reason: "timeout",
            });
            get().discardDraft();
          }
        }, DRAFT_TIMEOUT_MS);

        set({
          draft: {
            isDraftMode: true,
            draftText: "",
            draftModel: selectedModel,
            cid,
            startedAt,
            cleanupTimerId,
          },
        });

        logAction("chat.draft.created", {
          cid,
          model: selectedModel,
          timeoutMs: DRAFT_TIMEOUT_MS,
        });
        logDebug("Draft mode activated with auto-cleanup", {
          model: selectedModel,
          cid,
          timeoutMs: DRAFT_TIMEOUT_MS,
        });
      },

      discardDraft: () => {
        const state = get();
        const hadText = state.draft.draftText.length > 0;
        const cid = state.draft.cid;

        // Clear cleanup timer if exists
        if (state.draft.cleanupTimerId) {
          clearTimeout(state.draft.cleanupTimerId);
        }

        set({
          draft: INITIAL_DRAFT_STATE,
        });

        if (cid) {
          logAction("chat.draft.discarded", {
            cid,
            hadText,
            durationMs: state.draft.startedAt
              ? Date.now() - state.draft.startedAt
              : 0,
          });
        }
        logDebug("Draft discarded", { hadText, cid });
      },

      setDraftText: (text: string) => {
        set((state) => ({
          draft: { ...state.draft, draftText: text },
        }));
      },

      isDraftMode: () => {
        return get().draft.isDraftMode;
      },

      getDraftCid: () => {
        return get().draft.cid ?? null;
      },

      updateDraftTools: (tools: Record<string, boolean>) => {
        set({ draftToolsEnabled: mergeToolsState(tools) });
      },

      clearAllData: () => {
        const state = get();
        if (state.draft.cleanupTimerId) {
          clearTimeout(state.draft.cleanupTimerId);
        }
        set({
          draft: INITIAL_DRAFT_STATE,
          draftToolsEnabled: mergeToolsState(),
        });
      },
    }),
    {
      name: "draft-store",
    },
  ),
);
