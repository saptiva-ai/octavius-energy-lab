/**
 * Stores Barrel Export
 *
 * Centralized export for all Zustand stores.
 * Provides backward compatibility with the old monolithic store.
 */

// Individual stores
export {
  useUIStore,
  useUI,
  type ConnectionStatus,
  type Theme,
} from "./ui-store";
export { useCanvasStore } from "./canvas-store";
export { useSettingsStore, useSettings } from "./settings-store";
export { useResearchStore, useResearch } from "./research-store";
export { useDraftStore } from "./draft-store";
export { useChatStore } from "./chat-store";
export { useHistoryStore } from "./history-store";

// Re-export backward compatibility hooks
import { useUIStore } from "./ui-store";
import { useSettingsStore } from "./settings-store";
import { useResearchStore } from "./research-store";
import { useDraftStore } from "./draft-store";
import { useChatStore } from "./chat-store";
import { useHistoryStore } from "./history-store";

/**
 * Combined Chat hook for backward compatibility.
 * Combines chat, draft, and history state.
 */
export const useChat = () => {
  const chat = useChatStore();
  const draft = useDraftStore();
  const history = useHistoryStore();
  const settings = useSettingsStore();

  return {
    // Chat state
    currentChatId: chat.currentChatId,
    selectionEpoch: chat.selectionEpoch,
    messages: chat.messages,
    isLoading: chat.isLoading,
    models: chat.models,
    modelsLoading: chat.modelsLoading,
    selectedModel: chat.selectedModel,
    toolsEnabled: chat.toolsEnabled,
    chatNotFound: chat.chatNotFound,
    hydratedByChatId: chat.hydratedByChatId,
    isHydratingByChatId: chat.isHydratingByChatId,
    setCurrentChatId: chat.setCurrentChatId,
    switchChat: (nextId: string) =>
      chat.switchChat(nextId, draft.draftToolsEnabled),
    bumpSelectionEpoch: chat.bumpSelectionEpoch,
    addMessage: chat.addMessage,
    updateMessage: chat.updateMessage,
    clearMessages: chat.clearMessages,
    setLoading: chat.setLoading,
    setSelectedModel: chat.setSelectedModel,
    toggleTool: chat.toggleTool,
    setToolEnabled: chat.setToolEnabled,
    loadModels: chat.loadModels,
    loadUnifiedHistory: chat.loadUnifiedHistory,
    refreshChatStatus: chat.refreshChatStatus,

    // Draft state
    draft: draft.draft,
    draftToolsEnabled: draft.draftToolsEnabled,
    openDraft: () => draft.openDraft(chat.selectedModel),
    discardDraft: draft.discardDraft,
    setDraftText: draft.setDraftText,
    isDraftMode: draft.isDraftMode,
    startNewChat: () => draft.openDraft(chat.selectedModel),

    // History state
    chatSessions: history.chatSessions,
    chatSessionsLoading: history.chatSessionsLoading,
    isCreatingConversation: history.isCreatingConversation,
    pendingCreationId: history.pendingCreationId,
    loadChatSessions: history.loadChatSessions,
    addChatSession: history.addChatSession,
    removeChatSession: history.removeChatSession,
    renameChatSession: history.renameChatSession,
    pinChatSession: history.pinChatSession,
    deleteChatSession: history.deleteChatSession,
    updateSessionTitle: history.updateSessionTitle,
    createConversationOptimistic: (
      tempId?: string,
      createdAt?: string,
      idempotencyKey?: string,
    ) =>
      history.createConversationOptimistic(
        tempId,
        createdAt,
        idempotencyKey,
        chat.selectedModel,
        draft.draftToolsEnabled,
      ),
    reconcileConversation: history.reconcileConversation,
    removeOptimisticConversation: history.removeOptimisticConversation,
    finalizeCreation: history.finalizeCreation,
    cancelCreation: history.cancelCreation,

    // Feature flags
    featureFlags: settings.featureFlags,
    featureFlagsLoading: settings.featureFlagsLoading,
    loadFeatureFlags: settings.loadFeatureFlags,
  };
};

/**
 * Combined store hook for backward compatibility.
 * Combines all stores into a single interface matching the old useAppStore.
 *
 * @deprecated Use individual stores instead (useUIStore, useChatStore, etc.)
 */
export const useAppStore = () => {
  const ui = useUIStore();
  const settings = useSettingsStore();
  const research = useResearchStore();
  const draft = useDraftStore();
  const chat = useChatStore();
  const history = useHistoryStore();

  return {
    // UI state
    sidebarOpen: ui.sidebarOpen,
    theme: ui.theme,
    connectionStatus: ui.connectionStatus,
    setSidebarOpen: ui.setSidebarOpen,
    setTheme: ui.setTheme,
    setConnectionStatus: ui.setConnectionStatus,
    checkConnection: ui.checkConnection,

    // Chat state
    currentChatId: chat.currentChatId,
    selectionEpoch: chat.selectionEpoch,
    messages: chat.messages,
    isLoading: chat.isLoading,
    models: chat.models,
    modelsLoading: chat.modelsLoading,
    selectedModel: chat.selectedModel,
    toolsEnabled: chat.toolsEnabled,
    toolsEnabledByChatId: chat.toolsEnabledByChatId,
    chatNotFound: chat.chatNotFound,
    hydratedByChatId: chat.hydratedByChatId,
    isHydratingByChatId: chat.isHydratingByChatId,
    setCurrentChatId: chat.setCurrentChatId,
    switchChat: chat.switchChat,
    bumpSelectionEpoch: chat.bumpSelectionEpoch,
    addMessage: chat.addMessage,
    updateMessage: chat.updateMessage,
    clearMessages: chat.clearMessages,
    setLoading: chat.setLoading,
    setSelectedModel: chat.setSelectedModel,
    toggleTool: chat.toggleTool,
    setToolEnabled: chat.setToolEnabled,
    loadModels: chat.loadModels,
    loadUnifiedHistory: chat.loadUnifiedHistory,
    refreshChatStatus: chat.refreshChatStatus,

    // History state
    chatSessions: history.chatSessions,
    chatSessionsLoading: history.chatSessionsLoading,
    isCreatingConversation: history.isCreatingConversation,
    pendingCreationId: history.pendingCreationId,
    loadChatSessions: history.loadChatSessions,
    addChatSession: history.addChatSession,
    removeChatSession: history.removeChatSession,
    renameChatSession: history.renameChatSession,
    pinChatSession: history.pinChatSession,
    deleteChatSession: history.deleteChatSession,
    updateSessionTitle: history.updateSessionTitle,
    createConversationOptimistic: history.createConversationOptimistic,
    reconcileConversation: history.reconcileConversation,
    removeOptimisticConversation: history.removeOptimisticConversation,
    finalizeCreation: history.finalizeCreation,
    cancelCreation: history.cancelCreation,

    // Research state
    activeTasks: research.activeTasks,
    currentTaskId: research.currentTaskId,
    addTask: research.addTask,
    updateTask: research.updateTask,
    removeTask: research.removeTask,
    setCurrentTaskId: research.setCurrentTaskId,

    // Draft state
    draft: draft.draft,
    draftToolsEnabled: draft.draftToolsEnabled,
    openDraft: () => draft.openDraft(chat.selectedModel),
    discardDraft: draft.discardDraft,
    setDraftText: draft.setDraftText,
    isDraftMode: draft.isDraftMode,

    // Settings state
    settings: settings.settings,
    featureFlags: settings.featureFlags,
    featureFlagsLoading: settings.featureFlagsLoading,
    updateSettings: settings.updateSettings,
    loadFeatureFlags: settings.loadFeatureFlags,

    // Combined actions
    startNewChat: () => draft.openDraft(chat.selectedModel),
    invalidateOnContextChange: () => {
      chat.clearAllData();
      history.clearAllData();
      research.clearAllData();
      ui.setConnectionStatus("disconnected");
    },
    clearAllData: () => {
      ui.clearAllData();
      settings.clearAllData();
      research.clearAllData();
      draft.clearAllData();
      chat.clearAllData();
      history.clearAllData();
    },
  };
};
