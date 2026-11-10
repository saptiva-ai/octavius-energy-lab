/**
 * Store Re-exports (Backward Compatibility Layer)
 *
 * This file maintains backward compatibility with the old monolithic store
 * by re-exporting from the new modular stores architecture.
 *
 * Components can continue using:
 * - import { useAppStore } from '../lib/store'
 * - import { useChat, useUI, useSettings, useResearch } from '../lib/store'
 *
 * New code should import directly from stores/:
 * - import { useChatStore } from '../lib/stores/chat-store'
 * - import { useUIStore } from '../lib/stores/ui-store'
 * etc.
 */

export {
  // Combined store (backward compatibility)
  useAppStore,

  // Individual stores
  useUIStore,
  useSettingsStore,
  useResearchStore,
  useDraftStore,
  useChatStore,
  useHistoryStore,
  useCanvasStore,

  // Selector hooks (backward compatibility)
  useUI,
  useSettings,
  useResearch,
  useChat,

  // Types
  type ConnectionStatus,
  type Theme,
} from "./stores";
