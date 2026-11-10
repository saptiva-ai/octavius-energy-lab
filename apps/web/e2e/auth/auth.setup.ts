/**
 * Auth setup project — runs before chromium/firefox projects.
 *
 * Tries real login if E2E_USER_EMAIL + E2E_USER_PASSWORD are set.
 * Falls back to injecting a mock auth state in localStorage so tests
 * can run fully offline without a backend.
 */
import { test as setup } from "@playwright/test";

import { testUser } from "../utils/test-data";
import {
  mockAllChatApis,
  mockLogin,
  mockMe,
  mockConversations,
} from "../utils/mock-api";

const authFile = "e2e/.auth/user.json";
setup.setTimeout(90_000);

setup("authenticate", async ({ page }) => {
  const email = process.env.E2E_USER_EMAIL;
  const password = process.env.E2E_USER_PASSWORD;

  if (email && password) {
    // ── Real login path ──────────────────────────────────────────
    await page.goto("/login", {
      waitUntil: "domcontentloaded",
      timeout: 60_000,
    });
    await page.getByLabel("Correo electrónico o usuario").fill(email);
    await page.getByLabel("Contraseña").fill(password);
    await page.getByRole("button", { name: /Iniciar sesión/i }).click();
    await page.waitForURL("**/chat*", { timeout: 60_000 });
  } else {
    // ── Mock login fallback (no backend required) ────────────────
    // Set up route mocks before navigating
    await mockAllChatApis(page);
    await mockLogin(page);
    await mockMe(page);
    await mockConversations(page);

    // Navigate to any page to initialize the browser context
    await page.goto("/", { waitUntil: "domcontentloaded", timeout: 60_000 });

    // Inject auth state with browser-time expiresAt (always fresh)
    await page.evaluate((user) => {
      const authState = {
        state: {
          user,
          accessToken: "e2e-mock-access-token-abc123",
          refreshToken: "e2e-mock-refresh-token-xyz789",
          expiresAt: Date.now() + 3600 * 1000,
        },
        version: 1,
      };
      window.localStorage.setItem(
        "copilotos-auth-state",
        JSON.stringify(authState),
      );
    }, testUser);

    // Navigate to chat to confirm auth is active
    await page.goto("/chat", {
      waitUntil: "domcontentloaded",
      timeout: 60_000,
    });
  }

  // Persist the storage state (cookies + localStorage) for dependent projects
  await page.context().storageState({ path: authFile });
});
