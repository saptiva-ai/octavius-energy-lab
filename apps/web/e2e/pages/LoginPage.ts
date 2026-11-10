import type { Locator, Page } from "@playwright/test";

export class LoginPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly identifierInput: Locator;
  readonly passwordInput: Locator;
  readonly submitButton: Locator;
  readonly forgotPasswordLink: Locator;
  readonly errorMessage: Locator;
  readonly sessionExpiredBanner: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.getByRole("heading", { name: /Iniciar sesión/i });
    this.identifierInput = page.getByLabel("Correo electrónico o usuario");
    this.passwordInput = page.getByLabel("Contraseña");
    this.submitButton = page.getByRole("button", { name: /Iniciar sesión/i });
    this.forgotPasswordLink = page.getByRole("link", {
      name: /¿Olvidaste tu contraseña/i,
    });
    this.errorMessage = page.locator('[role="alert"]');
    this.sessionExpiredBanner = page.getByText(/sesión ha expirado/i);
  }

  async navigate(): Promise<void> {
    await this.page.goto("/login");
  }

  async fillEmail(email: string): Promise<void> {
    await this.identifierInput.fill(email);
  }

  async fillPassword(password: string): Promise<void> {
    await this.passwordInput.fill(password);
  }

  async submit(): Promise<void> {
    await this.submitButton.click();
  }

  async login(email: string, password: string): Promise<void> {
    await this.fillEmail(email);
    await this.fillPassword(password);
    await this.submit();
  }

  async waitForRedirect(path = "/chat"): Promise<void> {
    await this.page.waitForURL(`**${path}*`, { timeout: 15_000 });
  }
}
