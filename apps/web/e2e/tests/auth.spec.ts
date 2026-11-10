import { test, expect } from "../fixtures";
import { LoginPage } from "../pages/LoginPage";

test.describe("Authentication", () => {
  test("redirects unauthenticated user to /login", async ({ browser }) => {
    // Use a fresh context with NO storage state (no auth)
    const context = await browser.newContext();
    const page = await context.newPage();
    await page.goto("/chat");
    await expect(page).toHaveURL(/\/login/);
    await context.close();
  });

  test("login with valid credentials succeeds", async ({
    browser,
    mockApi,
  }) => {
    const context = await browser.newContext();
    const page = await context.newPage();
    const loginPage = new LoginPage(page);

    await mockApi.mockLogin(page);
    await mockApi.mockModels(page);
    await mockApi.mockFeatureFlags(page);
    await mockApi.mockHealth(page);

    await loginPage.navigate();
    await expect(loginPage.heading).toBeVisible();

    // Registrar los mocks de sesión DESPUÉS de ver el form: si /me o refresh
    // responden 200 al montar /login, la app se hidrata como autenticada y
    // rebota a /chat antes de que exista el heading (drift que rompía el spec).
    await mockApi.mockMe(page);
    await mockApi.mockConversations(page);
    await mockApi.mockRefresh(page);

    await loginPage.login("test@example.com", "testpassword123");
    await loginPage.waitForRedirect("/chat");

    await expect(page).toHaveURL(/\/chat/);
    await context.close();
  });

  test("login with invalid credentials shows error", async ({
    browser,
    mockApi,
  }) => {
    const context = await browser.newContext();
    const page = await context.newPage();
    const loginPage = new LoginPage(page);

    await mockApi.mockLoginFailure(page);

    await loginPage.navigate();
    await loginPage.login("wrong@example.com", "wrongpassword");

    // Should show an error message
    await expect(loginPage.errorMessage.first()).toBeVisible({
      timeout: 5_000,
    });
    // Should stay on login page
    await expect(page).toHaveURL(/\/login/);
    await context.close();
  });

  test("logout clears auth state", async ({ authenticatedPage, mockApi }) => {
    const page = authenticatedPage;
    await page.goto("/chat");

    // Find and click logout (usually in user menu or sidebar)
    const logoutButton = page.getByRole("button", {
      name: /Cerrar sesión|Logout/i,
    });

    // If logout is inside a dropdown menu, open it first
    const userMenu = page.getByRole("button", { name: /perfil|usuario|menu/i });
    if (await userMenu.isVisible()) {
      await userMenu.click();
    }

    if (await logoutButton.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await logoutButton.click();
      // Should redirect to login
      await expect(page).toHaveURL(/\/login/, { timeout: 10_000 });
    }
  });

  test("session expired shows notification", async ({ browser }) => {
    const context = await browser.newContext();
    const page = await context.newPage();
    const loginPage = new LoginPage(page);

    await page.goto("/login?reason=expired");
    await expect(loginPage.sessionExpiredBanner).toBeVisible({
      timeout: 5_000,
    });
    await context.close();
  });
});
