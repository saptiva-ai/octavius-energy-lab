/**
 * Critical tests for chat-store.ts
 *
 * Coverage goals:
 * - switchChat: Epoch bumping, hydration invalidation, message clearing
 * - loadUnifiedHistory: SWR deduplication, 404 handling, hydration flags
 * - setToolEnabled: Optimistic updates, rollback on error, API sync
 * - Message management: Add, update, clear operations
 * - Model selection: Loading, fallback, default model
 * - Tool state management: Per-chat persistence, merging
 */

import { renderHook, act, waitFor } from "@testing-library/react";
import { useChatStore } from "../chat-store";
import { apiClient } from "../../api-client";
import toast from "react-hot-toast";

// Mock dependencies
jest.mock("../../api-client", () => ({
  apiClient: {
    getUnifiedChatHistory: jest.fn(),
    getChatStatus: jest.fn(),
    getModels: jest.fn(),
    updateChatSession: jest.fn(),
  },
}));

jest.mock("react-hot-toast", () => {
  const mockToast = {
    error: jest.fn(),
    success: jest.fn(),
  };
  return {
    __esModule: true,
    default: mockToast,
  };
});

jest.mock("../../logger", () => ({
  logDebug: jest.fn(),
  logError: jest.fn(),
  logWarn: jest.fn(),
}));

jest.mock("../../ux-logger", () => ({
  logAction: jest.fn(),
}));

jest.mock("../../modelMap", () => ({
  buildModelList: jest.fn((models) =>
    models.map((m: string) => ({
      model: { slug: m, displayName: m, description: "", badges: [] },
      available: true,
      backendId: m,
    })),
  ),
  getDefaultModelSlug: jest.fn((model) => model || "turbo"),
}));

jest.mock("../../../config/modelCatalog", () => ({
  getAllModels: jest.fn(() => [
    {
      slug: "turbo",
      displayName: "Saptiva Turbo",
      description: "Fast model",
      badges: [],
    },
    {
      slug: "cortex",
      displayName: "Saptiva Cortex",
      description: "Advanced model",
      badges: [],
    },
  ]),
}));

jest.mock("../../tool-mapping", () => {
  const createDefaultToolsState = jest.fn((extraKeys: string[] = []) => {
    const base: Record<string, boolean> = {
      web_search: false,
      code_execution: false,
    };
    extraKeys.forEach((key: string) => {
      base[key] = false;
    });
    return base;
  });
  return {
    createDefaultToolsState,
    // Defaults + lo sembrado, como el real (sin tools bloqueadas en el mock).
    normalizeToolsState: jest.fn((state?: Record<string, boolean>) => ({
      ...createDefaultToolsState(state ? Object.keys(state) : []),
      ...(state ?? {}),
    })),
    isLockedTool: jest.fn(
      (k: string) => k === "retail_advisor" || k === "retail-advisor",
    ),
  };
});

describe("chat-store", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    // Reset store state
    const { result } = renderHook(() => useChatStore());
    act(() => {
      result.current.clearAllData();
    });
  });

  describe("switchChat", () => {
    it("increments selection epoch on chat switch", () => {
      const { result } = renderHook(() => useChatStore());

      const initialEpoch = result.current.selectionEpoch;

      act(() => {
        result.current.switchChat("temp-123");
      });

      expect(result.current.selectionEpoch).toBe(initialEpoch + 1);
      expect(result.current.currentChatId).toBe("temp-123");
    });

    it("increments epoch even when switching to same chat (re-selection)", () => {
      const { result } = renderHook(() => useChatStore());

      act(() => {
        result.current.switchChat("temp-123");
      });

      const epochAfterFirst = result.current.selectionEpoch;

      act(() => {
        result.current.switchChat("temp-123"); // Same chat
      });

      expect(result.current.selectionEpoch).toBe(epochAfterFirst + 1);
    });

    it("clears messages immediately on switch", () => {
      const { result } = renderHook(() => useChatStore());

      act(() => {
        result.current.addMessage({
          id: "msg-1",
          role: "user",
          content: "Hello",
          timestamp: new Date().toISOString(),
        });
      });

      expect(result.current.messages).toHaveLength(1);

      act(() => {
        result.current.switchChat("temp-456");
      });

      expect(result.current.messages).toHaveLength(0);
    });

    it("sets loading state on switch", () => {
      const { result } = renderHook(() => useChatStore());

      act(() => {
        result.current.switchChat("temp-789");
      });

      expect(result.current.isLoading).toBe(true);
    });

    it("invalidates hydration for target chat", () => {
      const { result } = renderHook(() => useChatStore());

      // Simulate hydrated state
      act(() => {
        result.current.switchChat("temp-100");
        // Manually set hydrated (normally done by loadUnifiedHistory)
        useChatStore.setState((state) => ({
          hydratedByChatId: { ...state.hydratedByChatId, "temp-100": true },
        }));
      });

      expect(result.current.hydratedByChatId["temp-100"]).toBe(true);

      // Switch away and back
      act(() => {
        result.current.switchChat("temp-200");
      });

      act(() => {
        result.current.switchChat("temp-100");
      });

      // Should be invalidated
      expect(result.current.hydratedByChatId["temp-100"]).toBeUndefined();
    });

    it("initializes tools for new chat", () => {
      const { result } = renderHook(() => useChatStore());

      act(() => {
        result.current.switchChat("temp-new-tools");
      });

      expect(
        result.current.toolsEnabledByChatId["temp-new-tools"],
      ).toBeDefined();
      expect(result.current.toolsEnabled).toHaveProperty("web_search");
      expect(result.current.toolsEnabled).toHaveProperty("code_execution");
    });

    it("seeds a brand-new chat with the provided draft tools (pills persist)", () => {
      const { result } = renderHook(() => useChatStore());

      act(() => {
        result.current.switchChat("temp-draft-tools", {
          retail_advisor: true,
        });
      });

      // El pill del draft (retail_advisor) debe sobrevivir a la creación del
      // chat: antes se sembraban defaults y los follow-ups mandaban false.
      expect(
        result.current.toolsEnabledByChatId["temp-draft-tools"].retail_advisor,
      ).toBe(true);
      expect(result.current.toolsEnabled.retail_advisor).toBe(true);
    });

    it("setCurrentChatId inherits the ACTIVE tools for a chat without entry", () => {
      const { result } = renderHook(() => useChatStore());

      act(() => {
        result.current.updateCurrentTools({ retail_advisor: true });
        result.current.setCurrentChatId("temp-optimistic-1");
      });

      expect(
        result.current.toolsEnabledByChatId["temp-optimistic-1"].retail_advisor,
      ).toBe(true);
      expect(result.current.toolsEnabled.retail_advisor).toBe(true);
    });
  });

  describe("loadUnifiedHistory", () => {
    // Valid UUID for tests that need a persisted chat
    const TEST_UUID = "550e8400-e29b-41d4-a716-446655440001";
    const TEST_UUID_2 = "550e8400-e29b-41d4-a716-446655440002";
    const TEST_UUID_3 = "550e8400-e29b-41d4-a716-446655440003";
    const TEST_UUID_4 = "550e8400-e29b-41d4-a716-446655440004";
    const TEST_UUID_5 = "550e8400-e29b-41d4-a716-446655440005";
    const TEST_UUID_6 = "550e8400-e29b-41d4-a716-446655440006";

    it("loads chat history successfully", async () => {
      const mockHistory = {
        events: [
          {
            message_id: "msg-1",
            event_type: "chat_message",
            chat_data: {
              role: "user",
              content: "Test message",
              model: "turbo",
            },
            timestamp: new Date().toISOString(),
          },
          {
            message_id: "msg-2",
            event_type: "chat_message",
            chat_data: {
              role: "assistant",
              content: "Response",
              model: "turbo",
            },
            timestamp: new Date().toISOString(),
          },
        ],
      };

      (apiClient.getUnifiedChatHistory as jest.Mock).mockResolvedValueOnce(
        mockHistory,
      );

      const { result } = renderHook(() => useChatStore());

      await act(async () => {
        await result.current.loadUnifiedHistory(TEST_UUID);
      });

      expect(result.current.messages).toHaveLength(2);
      expect(result.current.messages[0].content).toBe("Test message");
      expect(result.current.messages[1].content).toBe("Response");
      expect(result.current.hydratedByChatId[TEST_UUID]).toBe(true);
      expect(result.current.isLoading).toBe(false);
    });

    it("skips load if already hydrated (SWR deduplication)", async () => {
      const { result } = renderHook(() => useChatStore());

      // Manually set as hydrated
      act(() => {
        useChatStore.setState((state) => ({
          hydratedByChatId: { ...state.hydratedByChatId, [TEST_UUID_2]: true },
        }));
      });

      await act(async () => {
        await result.current.loadUnifiedHistory(TEST_UUID_2);
      });

      expect(apiClient.getUnifiedChatHistory).not.toHaveBeenCalled();
      expect(result.current.isLoading).toBe(false);
    });

    it("skips load if currently hydrating", async () => {
      const { result } = renderHook(() => useChatStore());

      // Manually set as hydrating
      act(() => {
        useChatStore.setState((state) => ({
          isHydratingByChatId: {
            ...state.isHydratingByChatId,
            [TEST_UUID_3]: true,
          },
        }));
      });

      await act(async () => {
        await result.current.loadUnifiedHistory(TEST_UUID_3);
      });

      expect(apiClient.getUnifiedChatHistory).not.toHaveBeenCalled();
      expect(result.current.isLoading).toBe(false);
    });

    it("handles 404 error and sets chatNotFound flag", async () => {
      const error404 = {
        response: { status: 404 },
      };

      (apiClient.getUnifiedChatHistory as jest.Mock).mockRejectedValueOnce(
        error404,
      );

      const { result } = renderHook(() => useChatStore());

      await act(async () => {
        await result.current.loadUnifiedHistory(TEST_UUID_4);
      });

      expect(result.current.chatNotFound).toBe(true);
      expect(result.current.messages).toHaveLength(0);
      expect(result.current.currentChatId).toBe(null);
      expect(result.current.isLoading).toBe(false);
    });

    it("clears isLoading in finally block on error", async () => {
      const genericError = new Error("Network error");
      (apiClient.getUnifiedChatHistory as jest.Mock).mockRejectedValueOnce(
        genericError,
      );

      const { result } = renderHook(() => useChatStore());

      await act(async () => {
        await result.current.loadUnifiedHistory(TEST_UUID_5);
      });

      expect(result.current.isLoading).toBe(false);
    });

    it("includes metadata from backend in messages", async () => {
      const mockHistory = {
        events: [
          {
            message_id: "msg-with-meta",
            event_type: "chat_message",
            chat_data: {
              role: "user",
              content: "Message with files",
              model: "turbo",
              metadata: {
                file_ids: ["file-1", "file-2"],
                context: "test",
              },
            },
            timestamp: new Date().toISOString(),
          },
        ],
      };

      (apiClient.getUnifiedChatHistory as jest.Mock).mockResolvedValueOnce(
        mockHistory,
      );

      const { result } = renderHook(() => useChatStore());

      await act(async () => {
        await result.current.loadUnifiedHistory(TEST_UUID_6);
      });

      expect(result.current.messages[0].metadata).toEqual({
        file_ids: ["file-1", "file-2"],
        context: "test",
      });
    });
  });

  describe("setToolEnabled", () => {
    // Valid UUIDs for persisted chat tests
    const TOOL_UUID_1 = "550e8400-e29b-41d4-a716-446655440101";
    const TOOL_UUID_2 = "550e8400-e29b-41d4-a716-446655440102";
    const TOOL_UUID_3 = "550e8400-e29b-41d4-a716-446655440103";
    const TOOL_UUID_4 = "550e8400-e29b-41d4-a716-446655440104";

    it("enables tool optimistically", async () => {
      (apiClient.updateChatSession as jest.Mock).mockResolvedValueOnce({});

      const { result } = renderHook(() => useChatStore());

      act(() => {
        result.current.setCurrentChatId(TOOL_UUID_1);
      });

      await act(async () => {
        await result.current.setToolEnabled("web_search", true);
      });

      expect(result.current.toolsEnabled.web_search).toBe(true);
      expect(result.current.toolsEnabledByChatId[TOOL_UUID_1].web_search).toBe(
        true,
      );
    });

    it("calls API to persist tool state", async () => {
      (apiClient.updateChatSession as jest.Mock).mockResolvedValueOnce({});

      const { result } = renderHook(() => useChatStore());

      act(() => {
        result.current.setCurrentChatId(TOOL_UUID_2);
      });

      await act(async () => {
        await result.current.setToolEnabled("code_execution", true);
      });

      expect(apiClient.updateChatSession).toHaveBeenCalledWith(TOOL_UUID_2, {
        tools_enabled: expect.objectContaining({ code_execution: true }),
      });
    });

    it("skips API call for temp chats", async () => {
      const { result } = renderHook(() => useChatStore());

      act(() => {
        result.current.setCurrentChatId("temp-12345");
      });

      await act(async () => {
        await result.current.setToolEnabled("web_search", true);
      });

      expect(apiClient.updateChatSession).not.toHaveBeenCalled();
      expect(result.current.toolsEnabled.web_search).toBe(true);
    });

    it("rolls back on API error and shows toast", async () => {
      const apiError = new Error("Failed to update");
      (apiClient.updateChatSession as jest.Mock).mockRejectedValueOnce(
        apiError,
      );

      const { result } = renderHook(() => useChatStore());

      act(() => {
        result.current.setCurrentChatId(TOOL_UUID_3);
      });

      // Initial state: web_search is false
      expect(result.current.toolsEnabled.web_search).toBe(false);

      await act(async () => {
        await result.current.setToolEnabled("web_search", true);
      });

      // Should rollback to false
      expect(result.current.toolsEnabled.web_search).toBe(false);
      expect(toast.error).toHaveBeenCalledWith(
        "No se pudo actualizar la configuración de herramientas.",
      );
    });

    it("does nothing if tool already has desired value", async () => {
      const { result } = renderHook(() => useChatStore());

      act(() => {
        result.current.setCurrentChatId(TOOL_UUID_4);
      });

      // web_search starts as false
      expect(result.current.toolsEnabled.web_search).toBe(false);

      await act(async () => {
        await result.current.setToolEnabled("web_search", false);
      });

      // Should not call API
      expect(apiClient.updateChatSession).not.toHaveBeenCalled();
    });

    it("no apaga la herramienta de datos (feedback de QA, punto 10)", async () => {
      const { result } = renderHook(() => useChatStore());

      act(() => {
        result.current.setCurrentChatId(TOOL_UUID_4);
      });

      await act(async () => {
        await result.current.setToolEnabled("retail_advisor", false);
      });

      expect(result.current.toolsEnabled.retail_advisor).not.toBe(false);
      expect(apiClient.updateChatSession).not.toHaveBeenCalled();
    });
  });

  describe("Message Management", () => {
    it("adds messages sequentially", () => {
      const { result } = renderHook(() => useChatStore());

      act(() => {
        result.current.addMessage({
          id: "msg-1",
          role: "user",
          content: "First",
          timestamp: new Date().toISOString(),
        });
        result.current.addMessage({
          id: "msg-2",
          role: "assistant",
          content: "Second",
          timestamp: new Date().toISOString(),
        });
      });

      expect(result.current.messages).toHaveLength(2);
      expect(result.current.messages[0].id).toBe("msg-1");
      expect(result.current.messages[1].id).toBe("msg-2");
    });

    it("updates message by id", () => {
      const { result } = renderHook(() => useChatStore());

      act(() => {
        result.current.addMessage({
          id: "msg-update",
          role: "assistant",
          content: "Initial content",
          timestamp: new Date().toISOString(),
        });
      });

      act(() => {
        result.current.updateMessage("msg-update", {
          content: "Updated content",
          tokens: 150,
        });
      });

      const updatedMsg = result.current.messages.find(
        (m) => m.id === "msg-update",
      );
      expect(updatedMsg?.content).toBe("Updated content");
      expect(updatedMsg?.tokens).toBe(150);
    });

    it("does not update non-existent message", () => {
      const { result } = renderHook(() => useChatStore());

      act(() => {
        result.current.addMessage({
          id: "msg-exists",
          role: "user",
          content: "Hello",
          timestamp: new Date().toISOString(),
        });
      });

      act(() => {
        result.current.updateMessage("msg-does-not-exist", {
          content: "Should not apply",
        });
      });

      const msg = result.current.messages.find((m) => m.id === "msg-exists");
      expect(msg?.content).toBe("Hello");
      expect(result.current.messages).toHaveLength(1);
    });

    it("clears all messages", () => {
      const { result } = renderHook(() => useChatStore());

      act(() => {
        result.current.addMessage({
          id: "msg-1",
          role: "user",
          content: "Test",
          timestamp: new Date().toISOString(),
        });
        result.current.addMessage({
          id: "msg-2",
          role: "user",
          content: "Test 2",
          timestamp: new Date().toISOString(),
        });
      });

      expect(result.current.messages).toHaveLength(2);

      act(() => {
        result.current.clearMessages();
      });

      expect(result.current.messages).toHaveLength(0);
    });
  });

  describe("Model Management", () => {
    it("loads models from API", async () => {
      const mockModelsResponse = {
        default_model: "cortex",
        allowed_models: ["turbo", "cortex"],
      };

      (apiClient.getModels as jest.Mock).mockResolvedValueOnce(
        mockModelsResponse,
      );

      const { result } = renderHook(() => useChatStore());

      await act(async () => {
        await result.current.loadModels();
      });

      expect(result.current.models).toHaveLength(2);
      expect(result.current.selectedModel).toBe("cortex");
      expect(result.current.modelsLoading).toBe(false);
    });

    it("falls back to catalog models on error when no models loaded yet", async () => {
      // Sin lista previa: se muestra el catálogo local marcado NO disponible,
      // para que el selector no quede vacío.
      act(() => {
        useChatStore.setState({ models: [] });
      });
      (apiClient.getModels as jest.Mock).mockRejectedValueOnce(
        new Error("API error"),
      );

      const { result } = renderHook(() => useChatStore());

      await act(async () => {
        await result.current.loadModels();
      });

      expect(result.current.models).toHaveLength(2);
      expect(result.current.models[0].available).toBe(false);
      expect(result.current.models[1].available).toBe(false);
      expect(result.current.modelsLoading).toBe(false);
    });

    it("preserva la lista real del backend si una recarga falla", async () => {
      // Un error transitorio no debe reemplazar modelos REALES por el catálogo
      // local: mostraría modelos que quizá ya no existen en el gateway.
      (apiClient.getModels as jest.Mock).mockResolvedValueOnce({
        default_model: "cortex",
        allowed_models: ["turbo", "cortex"],
      });
      const { result } = renderHook(() => useChatStore());
      await act(async () => {
        await result.current.loadModels();
      });
      const previos = result.current.models;

      (apiClient.getModels as jest.Mock).mockRejectedValueOnce(
        new Error("API error"),
      );
      await act(async () => {
        await result.current.loadModels();
      });

      expect(result.current.models).toEqual(previos);
      expect(result.current.models.every((m) => m.available)).toBe(true);
      expect(result.current.modelsLoading).toBe(false);
    });

    it("respeta la selección del usuario si el gateway aún la ofrece", async () => {
      (apiClient.getModels as jest.Mock).mockResolvedValueOnce({
        default_model: "cortex",
        allowed_models: ["turbo", "cortex"],
      });
      const { result } = renderHook(() => useChatStore());
      await act(async () => {
        await result.current.loadModels();
      });

      act(() => {
        result.current.setSelectedModel("turbo");
      });

      (apiClient.getModels as jest.Mock).mockResolvedValueOnce({
        default_model: "cortex",
        allowed_models: ["turbo", "cortex"],
      });
      await act(async () => {
        await result.current.loadModels();
      });

      expect(result.current.selectedModel).toBe("turbo");
    });

    it("cae al default del backend si la selección ya no existe", async () => {
      act(() => {
        useChatStore.setState({ selectedModel: "modelo-que-ya-no-existe" });
      });
      (apiClient.getModels as jest.Mock).mockResolvedValueOnce({
        default_model: "cortex",
        allowed_models: ["turbo", "cortex"],
      });

      const { result } = renderHook(() => useChatStore());
      await act(async () => {
        await result.current.loadModels();
      });

      expect(result.current.selectedModel).toBe("cortex");
    });

    it("sets model selection", () => {
      const { result } = renderHook(() => useChatStore());

      act(() => {
        result.current.setSelectedModel("new-model");
      });

      expect(result.current.selectedModel).toBe("new-model");
    });
  });

  describe("Document Review Messages", () => {
    it("adds file review message", () => {
      const { result } = renderHook(() => useChatStore());

      const reviewMessage = {
        id: "review-1",
        role: "assistant" as const,
        kind: "file-review" as const,
        content: "File review",
        timestamp: new Date().toISOString(),
        review: {
          docId: "doc-123",
          filename: "test.pdf",
          status: "processing" as const,
          stages: [],
        },
      };

      act(() => {
        result.current.addFileReviewMessage(reviewMessage);
      });

      expect(result.current.messages).toHaveLength(1);
      expect(result.current.messages[0].review?.docId).toBe("doc-123");
    });

    it("updates file review message", () => {
      const { result } = renderHook(() => useChatStore());

      const reviewMessage = {
        id: "review-update",
        role: "assistant" as const,
        kind: "file-review" as const,
        content: "File review",
        timestamp: new Date().toISOString(),
        review: {
          docId: "doc-456",
          filename: "update.pdf",
          status: "processing" as const,
          stages: [],
        },
      };

      act(() => {
        result.current.addFileReviewMessage(reviewMessage);
      });

      act(() => {
        result.current.updateFileReviewMessage("review-update", {
          status: "completed",
          stages: [],
        });
      });

      const updatedMsg = result.current.messages[0];
      expect(updatedMsg.review?.status).toBe("completed");
      expect(updatedMsg.review?.stages).toEqual([]);
    });

    it("finds file review message by docId", () => {
      const { result } = renderHook(() => useChatStore());

      act(() => {
        result.current.addFileReviewMessage({
          id: "review-find",
          role: "assistant" as const,
          kind: "file-review" as const,
          content: "Review",
          timestamp: new Date().toISOString(),
          review: {
            docId: "doc-search",
            filename: "search.pdf",
            status: "processing" as const,
            stages: [],
          },
        });
      });

      const found = result.current.findFileReviewMessage("doc-search");
      expect(found).toBeDefined();
      expect(found?.id).toBe("review-find");
    });

    it("returns undefined if review message not found", () => {
      const { result } = renderHook(() => useChatStore());

      const found = result.current.findFileReviewMessage("non-existent-doc");
      expect(found).toBeUndefined();
    });
  });

  describe("State Management", () => {
    it("sets loading state", () => {
      const { result } = renderHook(() => useChatStore());

      act(() => {
        result.current.setLoading(true);
      });

      expect(result.current.isLoading).toBe(true);

      act(() => {
        result.current.setLoading(false);
      });

      expect(result.current.isLoading).toBe(false);
    });

    it("bumps selection epoch manually", () => {
      const { result } = renderHook(() => useChatStore());

      const initialEpoch = result.current.selectionEpoch;

      act(() => {
        result.current.bumpSelectionEpoch();
      });

      expect(result.current.selectionEpoch).toBe(initialEpoch + 1);
    });

    it("clears all data to initial state", () => {
      const { result } = renderHook(() => useChatStore());
      const STATE_UUID = "550e8400-e29b-41d4-a716-446655440200";

      // Populate state
      act(() => {
        result.current.setCurrentChatId(STATE_UUID);
        result.current.addMessage({
          id: "msg-clear",
          role: "user",
          content: "Test",
          timestamp: new Date().toISOString(),
        });
        result.current.setSelectedModel("custom-model");
        result.current.setLoading(true);
      });

      // Clear all
      act(() => {
        result.current.clearAllData();
      });

      expect(result.current.currentChatId).toBe(null);
      expect(result.current.messages).toHaveLength(0);
      expect(result.current.selectionEpoch).toBe(0);
      expect(result.current.isLoading).toBe(false);
      expect(result.current.selectedModel).toBe("turbo");
      expect(result.current.hydratedByChatId).toEqual({});
    });
  });

  describe("refreshChatStatus", () => {
    it("is a no-op and does not call legacy status endpoint", async () => {
      const { result } = renderHook(() => useChatStore());

      await act(async () => {
        await result.current.refreshChatStatus(
          "550e8400-e29b-41d4-a716-446655440401",
        );
      });

      expect(apiClient.getChatStatus).not.toHaveBeenCalled();
    });
  });

  describe("Tool State Management", () => {
    const TOOL_UPDATE_UUID = "550e8400-e29b-41d4-a716-446655440301";
    const TOOL_TOGGLE_UUID = "550e8400-e29b-41d4-a716-446655440302";

    it("updates tools for specific chat", () => {
      const { result } = renderHook(() => useChatStore());

      act(() => {
        result.current.updateToolsForChat(TOOL_UPDATE_UUID, {
          web_search: true,
          custom_tool: true,
        });
      });

      expect(result.current.toolsEnabledByChatId[TOOL_UPDATE_UUID]).toEqual(
        expect.objectContaining({
          web_search: true,
          custom_tool: true,
        }),
      );
    });

    it("updates current tools", () => {
      const { result } = renderHook(() => useChatStore());

      act(() => {
        result.current.updateCurrentTools({
          web_search: true,
          code_execution: true,
        });
      });

      expect(result.current.toolsEnabled).toEqual(
        expect.objectContaining({
          web_search: true,
          code_execution: true,
        }),
      );
    });

    it("toggles tool between enabled and disabled", async () => {
      (apiClient.updateChatSession as jest.Mock).mockResolvedValue({});

      const { result } = renderHook(() => useChatStore());

      act(() => {
        result.current.setCurrentChatId(TOOL_TOGGLE_UUID);
      });

      // Initially false
      expect(result.current.toolsEnabled.web_search).toBe(false);

      await act(async () => {
        await result.current.toggleTool("web_search");
      });

      expect(result.current.toolsEnabled.web_search).toBe(true);

      await act(async () => {
        await result.current.toggleTool("web_search");
      });

      expect(result.current.toolsEnabled.web_search).toBe(false);
    });
  });
});
