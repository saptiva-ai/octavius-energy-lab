import type { Locator, Page } from "@playwright/test";

export class SidebarPage {
  readonly page: Page;
  readonly newChatButton: Locator;
  readonly conversationList: Locator;
  readonly historyLink: Locator;
  readonly reportsLink: Locator;
  readonly researchLink: Locator;

  constructor(page: Page) {
    this.page = page;
    this.newChatButton = page.getByRole("button", {
      name: /Nuevo chat|Nueva conversación/i,
    });
    this.conversationList = page.locator(
      '[class*="conversation-list"], [class*="ConversationList"]',
    );
    this.historyLink = page.getByRole("link", { name: /Historial|History/i });
    this.reportsLink = page.getByRole("link", { name: /Reportes|Reports/i });
    this.researchLink = page.getByRole("link", {
      name: /Research|Investigación/i,
    });
  }

  async openConversation(title: string): Promise<void> {
    await this.page.getByText(title).click();
  }

  async getConversationList(): Promise<string[]> {
    const items = this.conversationList.locator("a, button, [role='listitem']");
    const count = await items.count();
    const titles: string[] = [];
    for (let i = 0; i < count; i++) {
      titles.push(await items.nth(i).innerText());
    }
    return titles;
  }

  async createNewChat(): Promise<void> {
    await this.newChatButton.click();
  }

  async goToHistory(): Promise<void> {
    await this.historyLink.click();
    await this.page.waitForURL("**/history*");
  }

  async goToReports(): Promise<void> {
    await this.reportsLink.click();
    await this.page.waitForURL("**/reports*");
  }

  async goToResearch(): Promise<void> {
    await this.researchLink.click();
    await this.page.waitForURL("**/research*");
  }
}
