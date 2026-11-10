/**
 * Chat State Store
 *
 * Manages active chat session state:
 * - Current chat messages
 * - Model selection
 * - Tools configuration
 * - Loading and hydration state
 * - Message sending
 */

import { create } from "zustand";
import { devtools, persist } from "zustand/middleware";
import toast from "react-hot-toast";
import { ChatMessage, ChatModel } from "../types";
import { apiClient } from "../api-client";
import { logDebug, logError, logWarn } from "../logger";
import { logAction } from "../ux-logger";
import { buildModelList, getDefaultModelSlug } from "../modelMap";
import { getAllModels } from "../../config/modelCatalog";
import { isLockedTool, normalizeToolsState } from "../tool-mapping";

// ISSUE-018: UUID format validation
const UUID_REGEX =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

// Defaults + lo sembrado; las tools bloqueadas (la de datos) quedan encendidas.
const mergeToolsState = (seed?: Record<string, boolean>) =>
  normalizeToolsState(seed);

interface ChatState {
  // State
  currentChatId: string | null;
  selectionEpoch: number; // Incremented on same-chat re-selection to force re-render
  messages: ChatMessage[];
  isLoading: boolean;
  models: ChatModel[];
  modelsLoading: boolean;
  selectedModel: string;
  /** true solo si el usuario eligió el modelo a mano (no el default inicial). */
  modelPickedByUser: boolean;
  toolsEnabled: Record<string, boolean>;
  toolsEnabledByChatId: Record<string, Record<string, boolean>>;
  chatNotFound: boolean;

  // Hydration state (stale-while-revalidate pattern)
  hydratedByChatId: Record<string, boolean>;
  isHydratingByChatId: Record<string, boolean>;

  // Actions
  setCurrentChatId: (chatId: string | null) => void;
  switchChat: (
    nextId: string,
    draftToolsEnabled?: Record<string, boolean>,
  ) => void;
  bumpSelectionEpoch: () => void;
  addMessage: (message: ChatMessage) => void;
  updateMessage: (messageId: string, updates: Partial<ChatMessage>) => void;
  clearMessages: () => void;
  setMessages: (messages: ChatMessage[]) => void;
  setLoading: (loading: boolean) => void;
  setHydratedStatus: (chatId: string, status: boolean) => void;
  setSelectedModel: (model: string) => void;
  toggleTool: (toolName: string) => Promise<void>;
  setToolEnabled: (toolName: string, enabled: boolean) => Promise<void>;
  loadModels: () => Promise<void>;
  loadUnifiedHistory: (chatId: string) => Promise<void>;
  refreshChatStatus: (chatId: string) => Promise<void>;
  updateToolsForChat: (chatId: string, tools: Record<string, boolean>) => void;
  updateCurrentTools: (tools: Record<string, boolean>) => void;
  clearAllData: () => void;

  // Document review actions
  addFileReviewMessage: (message: ChatMessage) => void;
  updateFileReviewMessage: (
    messageId: string,
    reviewData: Partial<ChatMessage["review"]>,
  ) => void;
  findFileReviewMessage: (docId: string) => ChatMessage | undefined;
}

export const useChatStore = create<ChatState>()(
  devtools(
    persist(
      (set, get) => ({
        // Initial state
        currentChatId: null,
        selectionEpoch: 0,
        messages: [],
        isLoading: false,
        models: [],
        modelsLoading: false,
        // Provisional hasta que `loadModels` traiga el default real del backend.
        selectedModel: "turbo",
        modelPickedByUser: false,
        toolsEnabled: mergeToolsState(),
        toolsEnabledByChatId: {},
        chatNotFound: false,
        hydratedByChatId: {},
        isHydratingByChatId: {},

        // Actions
        setCurrentChatId: (chatId) => {
          const state = get();
          const nextToolsByChat = { ...state.toolsEnabledByChatId };
          let resolvedTools: Record<string, boolean>;

          if (chatId) {
            if (!nextToolsByChat[chatId]) {
              // Chat sin entrada = recién creado desde el draft: heredar las
              // tools ACTIVAS (pills del compositor, ej. retail_advisor).
              // Sembrar defaults aquí borraba el pill al crear el chat y los
              // follow-ups mandaban retail_advisor:false (pisando la sesión).
              nextToolsByChat[chatId] = mergeToolsState(state.toolsEnabled);
            }
            resolvedTools = mergeToolsState(nextToolsByChat[chatId]);
          } else {
            resolvedTools = mergeToolsState();
          }

          set({
            currentChatId: chatId,
            toolsEnabled: resolvedTools,
            toolsEnabledByChatId: nextToolsByChat,
          });
        },

        // Switch chat with re-selection support (A→B→C→A pattern)
        switchChat: (
          nextId: string,
          draftToolsEnabled?: Record<string, boolean>,
        ) => {
          // ISSUE-018: Validate chat_id format (UUID or temp-*)
          const isValidId =
            nextId.startsWith("temp-") || UUID_REGEX.test(nextId);
          if (!isValidId) {
            logWarn("switchChat: Invalid chat_id format", { nextId });
            return;
          }

          const {
            currentChatId,
            selectionEpoch,
            hydratedByChatId,
            isHydratingByChatId,
            toolsEnabledByChatId,
          } = get();

          // Always set the activeId AND bump epoch
          const isReselection = currentChatId === nextId;
          const newEpoch = selectionEpoch + 1;

          // CRITICAL: Invalidate hydration for the target chat to force reload
          const newHydratedByChatId = { ...hydratedByChatId };
          delete newHydratedByChatId[nextId];

          // CRITICAL: Also clear isHydratingByChatId flag
          const newIsHydratingByChatId = { ...isHydratingByChatId };
          delete newIsHydratingByChatId[nextId];

          const nextToolsByChat = { ...toolsEnabledByChatId };
          if (!nextToolsByChat[nextId]) {
            // Semilla con el draft si viene (chat nuevo desde el compositor);
            // antes se sembraba con defaults y el `|| draftToolsEnabled` de
            // abajo llegaba tarde (la entrada ya existía) → pills perdidos.
            nextToolsByChat[nextId] = mergeToolsState(draftToolsEnabled);
          }

          const resolvedTools = mergeToolsState(nextToolsByChat[nextId]);

          logDebug("SWITCH_CHAT", {
            from: currentChatId,
            to: nextId,
            reselection: isReselection,
            epochBefore: selectionEpoch,
            epochAfter: newEpoch,
            invalidateHydration: true,
            clearingMessages: true,
            clearingHydratingFlag: true,
            settingLoading: true,
          });

          set({
            currentChatId: nextId,
            selectionEpoch: newEpoch,
            hydratedByChatId: newHydratedByChatId,
            isHydratingByChatId: newIsHydratingByChatId,
            messages: [], // CRITICAL: Clear messages immediately
            isLoading: true, // CRITICAL: Set loading to prevent Hero from showing
            toolsEnabledByChatId: nextToolsByChat,
            toolsEnabled: resolvedTools,
          });
        },

        bumpSelectionEpoch: () => {
          const epoch = get().selectionEpoch;
          logDebug("BUMP_EPOCH", { from: epoch, to: epoch + 1 });
          set({ selectionEpoch: epoch + 1 });
        },

        addMessage: (message) => {
          //   messageId: message.id,
          //   role: message.role,
          //   currentCount: get().messages.length,
          //   newCount: get().messages.length + 1,
          // });
          set((state) => ({
            messages: [...state.messages, message],
          }));
        },

        updateMessage: (messageId, updates) =>
          set((state) => ({
            messages: state.messages.map((msg) =>
              msg.id === messageId ? { ...msg, ...updates } : msg,
            ),
          })),

        clearMessages: () => set({ messages: [] }),
        setMessages: (messages) => {
          //   newCount: messages.length,
          //   currentCount: get().messages.length,
          //   isOverwrite: true,
          // });
          set({ messages });
        },
        setLoading: (loading) => set({ isLoading: loading }),
        setHydratedStatus: (chatId, status) =>
          set((state) => ({
            hydratedByChatId: { ...state.hydratedByChatId, [chatId]: status },
          })),
        setSelectedModel: (model) => {
          logDebug("UI model changed", model);
          // `modelPickedByUser` distingue una elección DELIBERADA del default
          // inicial: al recargar modelos solo se respeta la primera.
          set({ selectedModel: model, modelPickedByUser: true });
        },

        toggleTool: async (toolName) => {
          const state = get();
          const currentValue = state.toolsEnabled[toolName] ?? false;
          await get().setToolEnabled(toolName, !currentValue);
        },

        setToolEnabled: async (toolName, enabled) => {
          if (!enabled && isLockedTool(toolName)) {
            // La herramienta de datos no se apaga (feedback de QA, punto 10).
            return;
          }
          const state = get();
          const currentValue = state.toolsEnabled[toolName] ?? false;
          if (currentValue === enabled) {
            return;
          }

          const nextTools = mergeToolsState({
            ...state.toolsEnabled,
            [toolName]: enabled,
          });

          const currentChatId = state.currentChatId;
          const nextToolsByChat = { ...state.toolsEnabledByChatId };

          if (currentChatId) {
            nextToolsByChat[currentChatId] = nextTools;
          }

          set({
            toolsEnabled: nextTools,
            toolsEnabledByChatId: nextToolsByChat,
          });

          logAction("tool.toggle.changed", { tool: toolName, enabled });

          if (currentChatId && !currentChatId.startsWith("temp-")) {
            try {
              await apiClient.updateChatSession(currentChatId, {
                tools_enabled: nextTools,
              });
            } catch (error) {
              logError("Failed to update tools-enabled state", error);
              toast.error(
                "No se pudo actualizar la configuración de herramientas.",
              );

              const rollbackTools = mergeToolsState({
                ...state.toolsEnabled,
                [toolName]: currentValue,
              });

              set((prevState) => {
                const rollbackMap = { ...prevState.toolsEnabledByChatId };
                if (currentChatId) {
                  rollbackMap[currentChatId] = rollbackTools;
                }
                return {
                  toolsEnabled: rollbackTools,
                  toolsEnabledByChatId: rollbackMap,
                };
              });
            }
          }
        },

        loadModels: async () => {
          try {
            set({ modelsLoading: true });
            const response = await apiClient.getModels();

            // Build model list with catalog and availability
            const modelList = buildModelList(response.allowed_models);

            // Convert to ChatModel format for UI
            const models: ChatModel[] = modelList.map(
              ({ model, available, backendId }) => ({
                id: model.slug,
                value: backendId || model.slug,
                label: model.displayName,
                description: model.description,
                tags: model.badges,
                available,
                backendId,
              }),
            );

            // Get default model slug from backend default
            const defaultSlug = getDefaultModelSlug(response.default_model);

            // Se respeta la elección DELIBERADA del usuario si el gateway
            // todavía la ofrece; si no (p.ej. tras cambiar de gateway), o si
            // solo era el default inicial, manda el default del backend.
            const { selectedModel: seleccionActual, modelPickedByUser } = get();
            const sigueDisponible = models.some(
              (m) => m.id === seleccionActual && m.available,
            );
            const selectedModel =
              modelPickedByUser && sigueDisponible
                ? seleccionActual
                : defaultSlug;

            logDebug("Models loaded", {
              backendModels: response.allowed_models,
              uiModels: models,
              defaultSlug,
              selectedModel,
            });

            set({ models, selectedModel, modelsLoading: false });
          } catch (error) {
            logError("Failed to load models:", error);
            // Si ya había una lista real cargada, se conserva: pisarla con el
            // catálogo local mostraría modelos que quizá no existen.
            if (get().models.length > 0) {
              set({ modelsLoading: false });
              return;
            }
            const fallbackModels: ChatModel[] = getAllModels().map((model) => ({
              id: model.slug,
              value: model.slug,
              label: model.displayName,
              description: model.description,
              tags: model.badges,
              available: false,
              backendId: null,
            }));
            set({ models: fallbackModels, modelsLoading: false });
          }
        },

        loadUnifiedHistory: async (chatId) => {
          const state = get();

          // SWR deduplication: Don't load if already hydrated or currently hydrating
          if (
            state.hydratedByChatId[chatId] ||
            state.isHydratingByChatId[chatId]
          ) {
            logDebug("Skipping load - already hydrated/hydrating", { chatId });
            // CRITICAL: Clear isLoading even on early return
            set({ isLoading: false });
            return;
          }

          try {
            // Mark as hydrating (prevents duplicate calls)
            set((s) => ({
              isHydratingByChatId: { ...s.isHydratingByChatId, [chatId]: true },
              chatNotFound: false,
              currentChatId: chatId,
            }));

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
                // FIX: Schema v2 stores files in explicit fields, but ChatMessage component
                // expects them in metadata.files for display. Merge explicit files into metadata.
                const enrichedMetadata: Record<string, any> = {
                  ...(event.chat_data.metadata || {}),
                };

                // Add file_ids and files to metadata if they exist (schema v2)
                if (
                  event.chat_data.file_ids &&
                  event.chat_data.file_ids.length > 0
                ) {
                  enrichedMetadata.file_ids = event.chat_data.file_ids;
                }
                if (event.chat_data.files && event.chat_data.files.length > 0) {
                  enrichedMetadata.files = event.chat_data.files;
                }

                // DEBUG: Log metadata from backend
                if (event.chat_data.role === "user") {
                  logDebug("[ChatStore] Loading user message from history", {
                    message_id: event.message_id,
                    role: event.chat_data.role,
                    hasFiles: !!(
                      event.chat_data.files && event.chat_data.files.length > 0
                    ),
                    fileCount: event.chat_data.files?.length || 0,
                    hasMetadata: !!event.chat_data.metadata,
                    enrichedHasFiles: !!enrichedMetadata.files,
                  });
                }

                messages.push({
                  id: event.message_id || event.id,
                  role: event.chat_data.role,
                  content: event.chat_data.content,
                  timestamp: event.timestamp,
                  model: event.chat_data.model,
                  tokens: event.chat_data.tokens,
                  latency: event.chat_data.latency_ms,
                  // MVP-LOCK: Include enriched metadata with files for backwards compatibility
                  ...(Object.keys(enrichedMetadata).length > 0 && {
                    metadata: enrichedMetadata,
                  }),
                });
              }
            }

            // Atomic replacement: set messages only when data arrives
            set((s) => ({
              messages,
              currentChatId: chatId,
              hydratedByChatId: { ...s.hydratedByChatId, [chatId]: true },
              isHydratingByChatId: {
                ...s.isHydratingByChatId,
                [chatId]: false,
              },
            }));

            logDebug("Chat hydrated", {
              chatId,
              messageCount: messages.length,
            });
          } catch (error: any) {
            logError("Failed to load unified history:", error);

            // Mark hydration as failed
            set((s) => ({
              isHydratingByChatId: {
                ...s.isHydratingByChatId,
                [chatId]: false,
              },
            }));

            // Check if it's a 404 error (chat not found)
            if (error?.response?.status === 404) {
              set({ chatNotFound: true, messages: [], currentChatId: null });
            }
          } finally {
            // CRITICAL: Always clear isLoading in finally block
            logDebug("loadUnifiedHistory cleanup", {
              chatId,
              clearingLoading: true,
            });
            set({ isLoading: false });
          }
        },

        refreshChatStatus: async (chatId) => {
          // Legacy compatibility: chat status polling moved to research store.
          // Keep no-op to avoid redundant failing calls/noisy logs during navigation.
          logDebug("refreshChatStatus skipped (legacy path)", { chatId });
        },

        updateToolsForChat: (
          chatId: string,
          tools: Record<string, boolean>,
        ) => {
          set((state) => ({
            toolsEnabledByChatId: {
              ...state.toolsEnabledByChatId,
              [chatId]: mergeToolsState(tools),
            },
          }));
        },

        updateCurrentTools: (tools: Record<string, boolean>) => {
          set({ toolsEnabled: mergeToolsState(tools) });
        },

        clearAllData: () => {
          set({
            currentChatId: null,
            selectionEpoch: 0,
            messages: [],
            isLoading: false,
            selectedModel: "turbo",
            modelPickedByUser: false,
            toolsEnabled: mergeToolsState(),
            toolsEnabledByChatId: {},
            chatNotFound: false,
            hydratedByChatId: {},
            isHydratingByChatId: {},
          });
        },

        // Document review message actions
        addFileReviewMessage: (message: ChatMessage) => {
          logDebug("Adding file review message", {
            messageId: message.id,
            filename: message.review?.filename,
          });
          set((state) => ({
            messages: [...state.messages, message],
          }));
        },

        updateFileReviewMessage: (
          messageId: string,
          reviewData: Partial<ChatMessage["review"]>,
        ) => {
          logDebug("Updating file review message", { messageId, reviewData });
          set((state) => ({
            messages: state.messages.map((msg) =>
              msg.id === messageId && msg.kind === "file-review"
                ? {
                    ...msg,
                    review: {
                      ...msg.review!,
                      ...reviewData,
                    },
                  }
                : msg,
            ),
          }));
        },

        findFileReviewMessage: (docId: string) => {
          const state = get();
          return state.messages.find(
            (msg) => msg.kind === "file-review" && msg.review?.docId === docId,
          );
        },
      }),
      {
        name: "chat-store",
        // v1: retail_advisor pasa a default-on (POC): el estado persistido
        // de v0 trae `retail_advisor: false` sin distinguir "default viejo"
        // de "apagado por el usuario", así que la migración lo fuerza ON una
        // sola vez; a partir de ahí el toggle del usuario persiste normal.
        version: 1,
        migrate: (persisted, version) => {
          const state = persisted as {
            selectedModel?: string;
            toolsEnabled?: Record<string, boolean>;
          };
          if (version < 1) {
            return {
              ...state,
              toolsEnabled: normalizeToolsState({
                ...state.toolsEnabled,
                retail_advisor: true,
              }),
            };
          }
          return state;
        },
        partialize: (state) => ({
          selectedModel: state.selectedModel,
          modelPickedByUser: state.modelPickedByUser,
          toolsEnabled: state.toolsEnabled,
        }),
      },
    ),
    {
      name: "chat-store",
    },
  ),
);

// Note: For backward compatibility, import draft methods from draft-store
// The full backward-compatible useChat selector is in stores/index.ts
