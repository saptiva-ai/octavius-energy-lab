/**
 * CompactChatComposer - Files Only Flow Test
 *
 * MINIMALISMO FUNCIONAL: Verifies that the Send button is enabled when:
 * - There are READY file attachments
 * - No text is entered (empty input)
 * - Files are automatically used when ready (no toggle needed)
 *
 * This tests the core "files-only" UX feature (FE-UX-1).
 */

import * as React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { CompactChatComposer } from "../ChatComposer/CompactChatComposer";
import type { FileAttachment } from "../../../types/files";

// Mock dependencies
jest.mock("next/navigation", () => ({
  useRouter: () => ({
    push: jest.fn(),
    replace: jest.fn(),
  }),
}));

jest.mock("../../../lib/store", () => ({
  useChat: () => ({
    currentChatId: "test-chat-123",
    finalizeCreation: jest.fn(),
  }),
}));

jest.mock("../../../hooks/useDocumentReview", () => ({
  useDocumentReview: () => ({
    uploadFile: jest.fn(),
  }),
}));

jest.mock("../../../lib/logger", () => ({
  logDebug: jest.fn(),
  logError: jest.fn(),
}));

describe("CompactChatComposer - Files Only Flow", () => {
  const mockOnSubmit = jest.fn(async () => {});
  const mockOnChange = jest.fn();

  beforeEach(() => {
    mockOnSubmit.mockClear();
    mockOnChange.mockClear();
  });

  it("enables Send button when READY files exist (no text required - minimalismo funcional)", () => {
    const readyFiles: FileAttachment[] = [
      {
        file_id: "doc-123",
        filename: "test.pdf",
        status: "READY",
        bytes: 102400,
        pages: 5,
        mimetype: "application/pdf",
      },
    ];

    render(
      <CompactChatComposer
        value=""
        onChange={mockOnChange}
        onSubmit={mockOnSubmit}
        filesV1Attachments={readyFiles}
      />,
    );

    const sendButton = screen.getByRole("button", {
      name: /Enviar archivos para análisis|Enviar mensaje/i,
    });

    expect(sendButton).toBeEnabled();
    expect(sendButton).not.toHaveAttribute("disabled");
  });

  it("disables Send button when files are PROCESSING (not READY)", () => {
    const processingFiles: FileAttachment[] = [
      {
        file_id: "doc-456",
        filename: "processing.pdf",
        status: "PROCESSING",
        bytes: 204800,
        pages: 10,
        mimetype: "application/pdf",
      },
    ];

    render(
      <CompactChatComposer
        value=""
        onChange={mockOnChange}
        onSubmit={mockOnSubmit}
        filesV1Attachments={processingFiles}
      />,
    );

    const sendButton = screen.getByRole("button", {
      name: /Enviar mensaje|Subiendo archivos/i,
    });

    expect(sendButton).toBeDisabled();
  });

  it("disables Send button when no text and no files are present", () => {
    render(
      <CompactChatComposer
        value=""
        onChange={mockOnChange}
        onSubmit={mockOnSubmit}
        filesV1Attachments={[]}
      />,
    );

    const sendButton = screen.getByRole("button", { name: /Enviar mensaje/i });

    expect(sendButton).toBeDisabled();
  });

  it("allows submit when READY files exist (simulates click - minimalismo funcional)", async () => {
    const readyFiles: FileAttachment[] = [
      {
        file_id: "doc-submit-123",
        filename: "submit-test.pdf",
        status: "READY",
        bytes: 153600,
        pages: 8,
        mimetype: "application/pdf",
      },
    ];

    render(
      <CompactChatComposer
        value=""
        onChange={mockOnChange}
        onSubmit={mockOnSubmit}
        filesV1Attachments={readyFiles}
      />,
    );

    const sendButton = screen.getByRole("button", {
      name: /Enviar archivos para análisis|Enviar mensaje/i,
    });

    fireEvent.click(sendButton);

    // Wait for the submit animation delay (120ms)
    await waitFor(
      () => {
        expect(mockOnSubmit).toHaveBeenCalledTimes(1);
      },
      { timeout: 500 },
    );
  });

  it("shows correct aria-label when files are ready but no text is entered", () => {
    const readyFiles: FileAttachment[] = [
      {
        file_id: "doc-aria-123",
        filename: "aria-test.pdf",
        status: "READY",
        bytes: 76800,
        pages: 4,
        mimetype: "application/pdf",
      },
    ];

    render(
      <CompactChatComposer
        value=""
        onChange={mockOnChange}
        onSubmit={mockOnSubmit}
        filesV1Attachments={readyFiles}
      />,
    );

    const sendButton = screen.getByRole("button", {
      name: /Enviar archivos para análisis/i,
    });

    expect(sendButton).toHaveAttribute(
      "aria-label",
      "Enviar archivos para análisis",
    );
  });

  it("enables Send when both text AND ready files exist", () => {
    const readyFiles: FileAttachment[] = [
      {
        file_id: "doc-both-123",
        filename: "both.pdf",
        status: "READY",
        bytes: 102400,
        pages: 5,
        mimetype: "application/pdf",
      },
    ];

    render(
      <CompactChatComposer
        value="Analiza este documento"
        onChange={mockOnChange}
        onSubmit={mockOnSubmit}
        filesV1Attachments={readyFiles}
      />,
    );

    const sendButton = screen.getByRole("button", { name: /Enviar mensaje/i });

    expect(sendButton).toBeEnabled();
  });
});
