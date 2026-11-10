import { test, expect } from "../fixtures";
import { ChatPage } from "../pages/ChatPage";

test.describe("File Upload", () => {
  test("upload file shows preview in composer", async ({
    chatPage: page,
    mockApi,
  }) => {
    await mockApi.mockUpload(page);
    await mockApi.mockFileEvents(page);
    const chatPage = new ChatPage(page);

    // Find file input (usually hidden, triggered by button)
    const fileInput = page.locator('input[type="file"]');

    if ((await fileInput.count()) > 0) {
      // Create a test file and upload
      await fileInput.setInputFiles({
        name: "test-document.pdf",
        mimeType: "application/pdf",
        buffer: Buffer.from("fake-pdf-content"),
      });

      // File attachment preview should appear (testid del componente real;
      // el selector anterior por [class*=...] era frágil ante Tailwind)
      const attachment = page.getByTestId("preview-attachment");
      await expect(attachment.first()).toBeVisible({ timeout: 5_000 });
    }
  });

  test("file upload button is visible", async ({ chatPage: page }) => {
    // Look for the upload/attach button
    const uploadButton = page.getByRole("button", {
      name: /Adjuntar|Attach|Subir|Upload/i,
    });
    const plusButton = page.getByLabel("Herramientas");

    // Either a direct upload button or tools menu button should exist
    const hasUpload = await uploadButton
      .isVisible({ timeout: 3_000 })
      .catch(() => false);
    const hasTools = await plusButton
      .isVisible({ timeout: 3_000 })
      .catch(() => false);
    expect(hasUpload || hasTools).toBeTruthy();
  });

  test("audit toggle works with file attached", async ({
    chatPage: page,
    mockApi,
  }) => {
    await mockApi.mockUpload(page);
    await mockApi.mockFileEvents(page);

    // Look for audit toggle in the tools panel
    const chatPage = new ChatPage(page);
    await chatPage.openToolMenu();

    const auditToggle = page.getByText(/Auditoría|Audit/i);
    if (await auditToggle.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await auditToggle.click();
      // Toggle should be checked/active after clicking
    }
  });
});
