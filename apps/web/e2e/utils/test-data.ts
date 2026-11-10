/**
 * Test data for E2E tests — mock objects matching backend API shapes.
 */

export const testUser = {
  id: "e2e-user-001",
  username: "testuser",
  email: "test@example.com",
  isActive: true,
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-02-01T00:00:00Z",
  lastLogin: "2026-02-08T10:00:00Z",
  preferences: {
    theme: "auto",
    language: "es",
    defaultModel: "gpt-4o-mini",
    chatSettings: {},
  },
};

export const testTokens = {
  access_token: "e2e-mock-access-token-abc123",
  refresh_token: "e2e-mock-refresh-token-xyz789",
  expires_in: 3600,
};

/** Shape stored in localStorage under "copilotos-auth-state" */
export const testAuthState = {
  state: {
    user: testUser,
    accessToken: testTokens.access_token,
    refreshToken: testTokens.refresh_token,
    expiresAt: Date.now() + testTokens.expires_in * 1000,
  },
  version: 1,
};

export const testMessages = [
  {
    id: "msg-001",
    role: "user",
    content: "Hola, necesito consultar la venta por hora de Mundo E",
    created_at: "2026-02-08T10:00:00Z",
  },
  {
    id: "msg-002",
    role: "assistant",
    content:
      "Claro, puedo ayudarte con la venta por hora de Mundo E. ¿Qué periodo necesitas consultar?",
    created_at: "2026-02-08T10:00:05Z",
  },
];

export const testConversations = [
  {
    id: "conv-001",
    title: "Venta por hora Mundo E",
    created_at: "2026-02-08T09:00:00Z",
    updated_at: "2026-02-08T10:00:05Z",
    message_count: 2,
  },
  {
    id: "conv-002",
    title: "Comparativa Mundo E vs tienda control",
    created_at: "2026-02-07T14:00:00Z",
    updated_at: "2026-02-07T15:30:00Z",
    message_count: 6,
  },
  {
    id: "conv-003",
    title: "Faltantes de refrescos del día",
    created_at: "2026-02-06T11:00:00Z",
    updated_at: "2026-02-06T12:00:00Z",
    message_count: 4,
  },
];

/** SSE chunk sequence for a simple assistant response */
export const testSSEChunks = [
  {
    event: "meta",
    data: {
      chat_id: "conv-new-001",
      user_message_id: "msg-u-001",
      model: "gpt-4o-mini",
    },
  },
  { event: "chunk", data: { content: "Esta es " } },
  { event: "chunk", data: { content: "una respuesta " } },
  { event: "chunk", data: { content: "de prueba." } },
  {
    event: "done",
    data: {
      id: "msg-a-001",
      role: "assistant",
      content: "Esta es una respuesta de prueba.",
      chat_id: "conv-new-001",
      created_at: "2026-02-08T10:01:00Z",
    },
  },
];
