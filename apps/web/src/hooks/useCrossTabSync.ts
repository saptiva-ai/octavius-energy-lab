/**
 * React hook for cross-tab synchronization
 * Listens to sync events and updates the store accordingly
 */

import { useEffect, useRef } from "react";
import { getSyncInstance } from "@/lib/sync";
import { useHistoryStore } from "@/lib/stores";
import { logDebug } from "@/lib/logger";

/**
 * Setup cross-tab sync listeners
 * This hook should be used ONCE at the app root level
 */
export function useCrossTabSync() {
  const loadChatSessions = useHistoryStore((state) => state.loadChatSessions);
  const setupDone = useRef(false);

  useEffect(() => {
    // Prevent double setup in React StrictMode
    if (setupDone.current) return;
    setupDone.current = true;

    const sync = getSyncInstance();
    logDebug("Setting up cross-tab sync listeners", sync.getStatus());

    // Listen for session created
    const unsubscribeCreated = sync.on("session_created", (event) => {
      logDebug("Sync event: session_created", {
        chatId: event.payload.session?.id,
      });
      // Reload sessions to get the new one
      loadChatSessions();
    });

    // Listen for session renamed
    const unsubscribeRenamed = sync.on("session_renamed", (event) => {
      logDebug("Sync event: session_renamed", { chatId: event.payload.chatId });
      // Reload sessions to get updated title
      loadChatSessions();
    });

    // Listen for session pinned
    const unsubscribePinned = sync.on("session_pinned", (event) => {
      logDebug("Sync event: session_pinned", { chatId: event.payload.chatId });
      // Reload sessions to get updated pin state
      loadChatSessions();
    });

    // Listen for session deleted
    const unsubscribeDeleted = sync.on("session_deleted", (event) => {
      logDebug("Sync event: session_deleted", { chatId: event.payload.chatId });
      // Reload sessions to remove deleted one
      loadChatSessions();
    });

    // Listen for full reload
    const unsubscribeReloaded = sync.on("sessions_reloaded", () => {
      logDebug("Sync event: sessions_reloaded");
      loadChatSessions();
    });

    // Cleanup on unmount
    return () => {
      unsubscribeCreated();
      unsubscribeRenamed();
      unsubscribePinned();
      unsubscribeDeleted();
      unsubscribeReloaded();
      sync.cleanup();
      logDebug("Cross-tab sync cleaned up");
    };
  }, [loadChatSessions]);
}
