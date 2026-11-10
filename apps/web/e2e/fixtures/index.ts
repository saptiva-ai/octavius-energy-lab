/**
 * Custom Playwright fixtures extending the base test.
 *
 * Provides:
 *   - authenticatedPage: Page with auth storage state pre-loaded
 *   - chatPage:          Page navigated to /chat, ready to interact
 *   - mockApi:           Helper object to mock backend endpoints
 */
import { test as base, type Page } from "@playwright/test";

import {
  mockAllChatApis,
  mockBankData,
  mockCanvasState,
  mockChatHistory,
  mockChatStatus,
  mockChatStream,
  mockChatStreamByQuery,
  mockConversations,
  mockCreateConversation,
  mockFeatureFlags,
  mockHealth,
  mockLogin,
  mockLoginFailure,
  mockLogout,
  mockMe,
  mockModels,
  mockRefresh,
  mockUpload,
  mockFileEvents,
  injectAuthState,
} from "../utils/mock-api";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface MockApi {
  mockChatStream: typeof mockChatStream;
  mockBankData: typeof mockBankData;
  mockConversations: typeof mockConversations;
  mockCreateConversation: typeof mockCreateConversation;
  mockModels: typeof mockModels;
  mockFeatureFlags: typeof mockFeatureFlags;
  mockHealth: typeof mockHealth;
  mockChatStatus: typeof mockChatStatus;
  mockCanvasState: typeof mockCanvasState;
  mockLogin: typeof mockLogin;
  mockLoginFailure: typeof mockLoginFailure;
  mockUpload: typeof mockUpload;
  mockMe: typeof mockMe;
  mockLogout: typeof mockLogout;
  mockRefresh: typeof mockRefresh;
  mockChatHistory: typeof mockChatHistory;
  mockChatStreamByQuery: typeof mockChatStreamByQuery;
  mockFileEvents: typeof mockFileEvents;
  mockAllChatApis: typeof mockAllChatApis;
  injectAuthState: typeof injectAuthState;
}

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

export const test = base.extend<{
  authenticatedPage: Page;
  chatPage: Page;
  mockApi: MockApi;
  useApiMocks: boolean;
}>({
  /** Toggle API route mocks; set false for real-backend E2E flows. */
  useApiMocks: [process.env.E2E_USE_API_MOCKS !== "0", { option: true }],

  /** Page with auth state already injected via storageState. */
  authenticatedPage: async ({ page, useApiMocks }, use) => {
    // storageState is loaded automatically via project config,
    // but we also set up common API mocks and refresh the auth state
    // with a browser-time expiresAt to prevent stale-token redirects.
    if (useApiMocks) {
      await mockAllChatApis(page);
      await injectAuthState(page);
    }
    await use(page);
  },

  /** Page navigated to /chat with all mocks ready. */
  chatPage: async ({ page, useApiMocks }, use) => {
    if (useApiMocks) {
      await mockAllChatApis(page);
    }
    await page.goto("/chat");
    await use(page);
  },

  /** Helper object exposing all mock functions. */
  mockApi: async ({}, use) => {
    await use({
      mockChatStream,
      mockBankData,
      mockConversations,
      mockCreateConversation,
      mockModels,
      mockFeatureFlags,
      mockHealth,
      mockChatStatus,
      mockCanvasState,
      mockLogin,
      mockLoginFailure,
      mockUpload,
      mockMe,
      mockLogout,
      mockRefresh,
      mockChatHistory,
      mockChatStreamByQuery,
      mockFileEvents,
      mockAllChatApis,
      injectAuthState,
    });
  },
});

export { expect } from "@playwright/test";
