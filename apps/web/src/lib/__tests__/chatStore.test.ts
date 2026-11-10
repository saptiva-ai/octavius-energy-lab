import { useHistoryStore } from "../stores/history-store";
import { useDraftStore } from "../stores/draft-store";
import { createDefaultToolsState } from "../tool-mapping";
import type { ChatSession, ChatSessionOptimistic } from "../types";

const resetStore = () => {
  const historyState = useHistoryStore.getState();
  useHistoryStore.setState({
    ...historyState,
    chatSessions: [],
    pendingCreationId: null,
    isCreatingConversation: false,
  });

  const draftState = useDraftStore.getState();
  useDraftStore.setState({
    ...draftState,
    draftToolsEnabled: createDefaultToolsState(),
  });
};

describe("chat store – optimistic conversation flow", () => {
  beforeEach(() => {
    resetStore();
  });

  it("creates an optimistic conversation and marks creation state", () => {
    const createdAt = new Date().toISOString();
    const draftTools = useDraftStore.getState().draftToolsEnabled;

    const tempId = useHistoryStore
      .getState()
      .createConversationOptimistic(
        "temp-test",
        createdAt,
        "idempotent-key",
        undefined,
        draftTools,
      );
    const state = useHistoryStore.getState();

    expect(tempId).toBe("temp-test");
    expect(state.isCreatingConversation).toBe(true);
    expect(state.pendingCreationId).toBe("temp-test");
    const optimisticSession = state.chatSessions[0] as ChatSessionOptimistic;
    expect(optimisticSession).toMatchObject({
      id: "temp-test",
      pending: true,
      isOptimistic: true,
      state: "creating",
      idempotency_key: "idempotent-key",
    });
    expect(optimisticSession?.tools_enabled).toEqual(draftTools);
  });

  it("reconciles optimistic conversation with real session without duplicates", () => {
    const createdAt = new Date().toISOString();
    const tempId = useHistoryStore
      .getState()
      .createConversationOptimistic(undefined, createdAt, "reconcile-key");

    const realSession: ChatSession = {
      id: "real-session",
      title: "Chat real",
      created_at: createdAt,
      updated_at: createdAt,
      first_message_at: null,
      last_message_at: null,
      message_count: 0,
      model: "turbo",
      preview: "",
      pinned: false,
      state: "draft",
      idempotency_key: "reconcile-key",
    };

    useHistoryStore.getState().reconcileConversation(tempId, realSession);
    const reconciled = useHistoryStore.getState();

    expect(reconciled.chatSessions).toHaveLength(1);
    expect(reconciled.chatSessions[0].id).toBe("real-session");
    const reconciledSession = reconciled
      .chatSessions[0] as ChatSessionOptimistic;
    expect(reconciledSession.pending).toBe(false);
    expect(reconciled.pendingCreationId).toBeNull();
    expect(reconciled.isCreatingConversation).toBe(false);

    // Adding the same real session again should not create duplicates
    useHistoryStore.getState().addChatSession(realSession);
    const afterDuplicate = useHistoryStore.getState();
    expect(afterDuplicate.chatSessions).toHaveLength(1);
  });

  it("removes optimistic conversation on cancellation and clears creation state", () => {
    const tempId = useHistoryStore
      .getState()
      .createConversationOptimistic(
        undefined,
        new Date().toISOString(),
        "cancel-key",
      );
    useHistoryStore.getState().removeOptimisticConversation(tempId);

    const state = useHistoryStore.getState();
    expect(state.chatSessions).toHaveLength(0);
    expect(state.pendingCreationId).toBeNull();
    expect(state.isCreatingConversation).toBe(false);
  });
});
