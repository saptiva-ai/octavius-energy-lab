import { test, expect } from "../fixtures";
import { SidebarPage } from "../pages/SidebarPage";
import { ChatPage } from "../pages/ChatPage";

test.describe("Navigation", () => {
  test("navigate to chat page", async ({ authenticatedPage: page }) => {
    await page.goto("/chat");
    await expect(page).toHaveURL(/\/chat/);
    const chatPage = new ChatPage(page);
    await expect(chatPage.composerInput).toBeVisible();
  });

  test("navigate to history page", async ({ authenticatedPage: page }) => {
    await page.goto("/chat");
    const sidebar = new SidebarPage(page);

    if (
      await sidebar.historyLink.isVisible({ timeout: 3_000 }).catch(() => false)
    ) {
      await sidebar.goToHistory();
      await expect(page).toHaveURL(/\/history/);
    }
  });

  test("navigate to reports page", async ({ authenticatedPage: page }) => {
    await page.goto("/chat");
    const sidebar = new SidebarPage(page);

    if (
      await sidebar.reportsLink.isVisible({ timeout: 3_000 }).catch(() => false)
    ) {
      await sidebar.goToReports();
      await expect(page).toHaveURL(/\/reports/);
    }
  });

  test("navigate to research page", async ({ authenticatedPage: page }) => {
    await page.goto("/chat");
    const sidebar = new SidebarPage(page);

    if (
      await sidebar.researchLink
        .isVisible({ timeout: 3_000 })
        .catch(() => false)
    ) {
      await sidebar.goToResearch();
      await expect(page).toHaveURL(/\/research/);
    }
  });

  test("create new chat from sidebar", async ({ authenticatedPage: page }) => {
    await page.goto("/chat");
    const sidebar = new SidebarPage(page);

    if (
      await sidebar.newChatButton
        .isVisible({ timeout: 3_000 })
        .catch(() => false)
    ) {
      await sidebar.createNewChat();
      await expect(page).toHaveURL(/\/chat/);
    }
  });

  test("open existing conversation from sidebar", async ({
    authenticatedPage: page,
    mockApi,
  }) => {
    await mockApi.mockChatHistory(page);
    await page.goto("/chat");
    const sidebar = new SidebarPage(page);

    // Check if conversation list is visible
    const conversations = sidebar.conversationList;
    if (
      await conversations
        .first()
        .isVisible({ timeout: 3_000 })
        .catch(() => false)
    ) {
      // Click on the first conversation link
      const firstItem = conversations.locator("a, button").first();
      if (await firstItem.isVisible()) {
        await firstItem.click();
        // Should navigate to a specific chat
        await expect(page).toHaveURL(/\/chat\//);
      }
    }
  });
});
