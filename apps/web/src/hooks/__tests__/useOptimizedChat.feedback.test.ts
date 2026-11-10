/**
 * feedback round 1 (2026-10-16, punto 12): los pulgares y el cuadro
 * "¿Qué te gustó…?" no llegaban al backend. En un chat nuevo la URL se queda
 * en "/chat" (sin id) y `submitFeedback` regresaba en silencio mientras la UI
 * decía "Gracias por tu feedback": producción no tenía ni un POST /api/feedback
 * en siete días (logs del 19 de octubre).
 */
import { renderHook } from "@testing-library/react";
import toast from "react-hot-toast";

import { apiClient } from "../../lib/api-client";
import { useChatStore } from "../../lib/stores/chat-store";
import { useOptimizedChat } from "../useOptimizedChat";

jest.mock("../../lib/api-client", () => ({
  apiClient: { submitMessageFeedback: jest.fn() },
}));
jest.mock("react-hot-toast", () => {
  const toastFn = Object.assign(jest.fn(), {
    error: jest.fn(),
    success: jest.fn(),
  });
  return { __esModule: true, default: toastFn };
});
jest.mock("../../lib/store", () => ({
  useAppStore: () => ({ addMessage: jest.fn(), updateMessage: jest.fn() }),
}));

const submit = apiClient.submitMessageFeedback as jest.Mock;

describe("useOptimizedChat · submitFeedback", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    window.history.pushState({}, "", "/chat");
    useChatStore.setState({ currentChatId: null });
  });

  it("en un chat nuevo sin id en la URL usa el chat activo del store", async () => {
    useChatStore.setState({
      currentChatId: "9b2f6c1e-4a3d-4b8e-9f1a-2c3d4e5f6a7b",
    });
    submit.mockResolvedValue({ id: "f1", createdAt: "x" });
    const { result } = renderHook(() => useOptimizedChat({ chatId: null }));

    await result.current.submitFeedback("msg-1", "up", "Datos claros");

    expect(submit).toHaveBeenCalledWith({
      messageId: "msg-1",
      conversationId: "9b2f6c1e-4a3d-4b8e-9f1a-2c3d4e5f6a7b",
      rating: "up",
      reason: "Datos claros",
    });
  });

  it("sin conversación guardada falla con aviso en vez de fingir que envió", async () => {
    const { result } = renderHook(() => useOptimizedChat({ chatId: null }));

    await expect(
      result.current.submitFeedback("msg-1", "down"),
    ).rejects.toThrow();
    expect(submit).not.toHaveBeenCalled();
    expect(toast.error).toHaveBeenCalled();
  });

  it("si el backend rechaza, avisa al usuario", async () => {
    useChatStore.setState({
      currentChatId: "9b2f6c1e-4a3d-4b8e-9f1a-2c3d4e5f6a7b",
    });
    submit.mockRejectedValue(new Error("403"));
    const { result } = renderHook(() => useOptimizedChat({ chatId: null }));

    await expect(
      result.current.submitFeedback("msg-1", "down"),
    ).rejects.toThrow();
    expect(toast.error).toHaveBeenCalled();
  });
});
