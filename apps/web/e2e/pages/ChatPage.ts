import type { Locator, Page } from "@playwright/test";
import { expect } from "@playwright/test";

export class ChatPage {
  readonly page: Page;
  readonly composerInput: Locator;
  readonly sendButton: Locator;
  readonly toolsButton: Locator;
  readonly welcomeBanner: Locator;
  readonly helpOnboardingTrigger: Locator;
  readonly helpOnboardingMenu: Locator;
  readonly helpOnboardingUsePrompt: Locator;
  readonly helpOnboardingNext: Locator;
  readonly helpOnboardingStepTitle: Locator;
  readonly helpOnboardingStepPrompt: Locator;
  readonly quickPrompts: Locator;
  readonly assistantMessages: Locator;
  readonly userMessages: Locator;
  readonly chartButtons: Locator;

  constructor(page: Page) {
    this.page = page;
    // Support CompactChatComposer first, then legacy composer variants.
    this.composerInput = page
      .locator(
        [
          '[role="form"][aria-label="Compositor de mensajes"] textarea[aria-label="Escribe tu mensaje"]',
          '[role="form"][aria-label="Compositor de mensajes"] textarea[aria-multiline="true"]',
          '[aria-label="Chat composer"] textarea',
          'textarea[aria-label="Escribe tu mensaje"]',
          'textarea[placeholder*="Pregúntame algo"]',
          'textarea[placeholder*="Preguntame algo"]',
          'textarea[placeholder*="Escribe tu mensaje"]',
        ].join(", "),
      )
      .first();
    this.sendButton = page.getByRole("button", { name: /Enviar/i });
    this.toolsButton = page.getByLabel("Herramientas");
    this.welcomeBanner = page.locator(
      '[class*="hero"], [class*="welcome"], [class*="Welcome"]',
    );
    this.helpOnboardingTrigger = page.getByTestId("help-onboarding-trigger");
    this.helpOnboardingMenu = page.getByTestId("help-onboarding-menu");
    this.helpOnboardingUsePrompt = page.getByTestId(
      "help-onboarding-use-prompt",
    );
    this.helpOnboardingNext = page.getByTestId("help-onboarding-next");
    this.helpOnboardingStepTitle = page.getByTestId(
      "help-onboarding-step-title",
    );
    this.helpOnboardingStepPrompt = page.getByTestId(
      "help-onboarding-step-prompt",
    );
    this.quickPrompts = page.locator(
      '[class*="quick-prompt"], [class*="QuickPrompt"]',
    );
    this.assistantMessages = page.getByRole("article", {
      name: /Respuesta del asistente/i,
    });
    this.userMessages = page.getByRole("article", {
      name: /Tu mensaje/i,
    });
    this.chartButtons = page.getByRole("button", {
      name: /Abrir grafica de .* en canvas|Abrir gráfica de .* en canvas/i,
    });
  }

  async navigate(chatId?: string): Promise<void> {
    const path = chatId ? `/chat/${chatId}` : "/chat";
    await this.page.goto(path);
  }

  async sendMessage(text: string): Promise<void> {
    await this.waitForComposerReady();
    await this.composerInput.fill(text);
    await this.sendButton.click();
  }

  async waitForComposerReady(timeout = 30_000): Promise<void> {
    await expect(this.composerInput).toBeVisible({ timeout });
    await expect(this.composerInput).toBeEditable({ timeout });
  }

  async waitForResponse(timeout = 30_000): Promise<void> {
    await expect(this.assistantMessages.first()).toBeVisible({
      timeout,
    });
  }

  async waitForStreamComplete(timeout = 30_000): Promise<void> {
    // Wait for the streaming indicator to disappear
    await this.page
      .locator('[class*="streaming"], [class*="typing"]')
      .waitFor({ state: "hidden", timeout });
  }

  async getLastMessage(): Promise<string> {
    const messages = this.assistantMessages;
    const count = await messages.count();
    if (count === 0) return "";
    return messages.nth(count - 1).innerText();
  }

  async getMessages(): Promise<string[]> {
    const count = await this.assistantMessages.count();
    const texts: string[] = [];
    for (let i = 0; i < count; i++) {
      texts.push(await this.assistantMessages.nth(i).innerText());
    }
    return texts;
  }

  async clickQuickPrompt(index = 0): Promise<void> {
    await this.quickPrompts.nth(index).click();
  }

  async openHelpOnboarding(): Promise<void> {
    await expect(this.helpOnboardingTrigger).toBeVisible();
    await this.helpOnboardingTrigger.click();
    await expect(this.helpOnboardingMenu).toBeVisible();
  }

  async selectModel(modelName: string): Promise<void> {
    const selector = this.page.locator(
      '[class*="model-selector"], [class*="ModelSelector"]',
    );
    await selector.click();
    await this.page.getByText(modelName).click();
  }

  async openToolMenu(): Promise<void> {
    await this.toolsButton.click();
  }

  async waitForChartButtonsCount(
    count: number,
    timeout = 30_000,
  ): Promise<void> {
    await expect(this.chartButtons).toHaveCount(count, { timeout });
  }

  async openLastChartButton(): Promise<void> {
    const chartButton = this.chartButtons.last();
    await expect(chartButton).toBeVisible();
    await chartButton.click();

    const dataTab = this.page.getByRole("button", { name: /^Datos$/i });
    const hasOpened = await dataTab
      .first()
      .isVisible({ timeout: 2_000 })
      .catch(() => false);

    // Retry once for intermittent first-click misses in canvas activation.
    if (!hasOpened) {
      const handle = await chartButton.elementHandle();
      if (handle) {
        await handle.evaluate((node) => {
          (node as HTMLButtonElement).click();
        });
      } else {
        await chartButton.click();
      }
    }
  }
}
