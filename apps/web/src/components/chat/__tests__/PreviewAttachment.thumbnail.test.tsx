/**
 * Tests for PreviewAttachment thumbnail fallback behavior.
 *
 * Verifies that when ThumbnailImage fails to load, the fallback SVG
 * icon is shown instead of an empty space.
 */

import { render, screen, act } from "@testing-library/react";
import { PreviewAttachment } from "../PreviewAttachment";
import type { FileAttachment } from "@/types/files";

// Track the onError callback passed to ThumbnailImage
let capturedOnError: (() => void) | undefined;

jest.mock("../ThumbnailImage", () => ({
  ThumbnailImage: ({
    onError,
  }: {
    fileId: string;
    alt: string;
    className?: string;
    onError?: () => void;
  }) => {
    capturedOnError = onError;
    return <div data-testid="thumbnail-image">Thumbnail</div>;
  },
}));

jest.mock("@/lib/logger", () => ({
  logDebug: jest.fn(),
  logError: jest.fn(),
}));

const makePdfAttachment = (
  overrides?: Partial<FileAttachment>,
): FileAttachment => ({
  file_id: "abc123",
  filename: "report.pdf",
  status: "READY",
  bytes: 1024,
  mimetype: "application/pdf",
  ...overrides,
});

describe("PreviewAttachment thumbnail fallback", () => {
  beforeEach(() => {
    capturedOnError = undefined;
  });

  it("shows ThumbnailImage when status is READY and mimetype is pdf", () => {
    render(<PreviewAttachment attachment={makePdfAttachment()} />);
    expect(screen.getByTestId("thumbnail-image")).toBeInTheDocument();
  });

  it("shows fallback when ThumbnailImage invokes onError", () => {
    render(<PreviewAttachment attachment={makePdfAttachment()} />);

    // ThumbnailImage should be visible initially
    expect(screen.getByTestId("thumbnail-image")).toBeInTheDocument();

    // Simulate thumbnail load failure
    act(() => {
      capturedOnError?.();
    });

    // After error, ThumbnailImage should be replaced by fallback (PDF icon)
    expect(screen.queryByTestId("thumbnail-image")).not.toBeInTheDocument();
    // The fallback renders the PDF document icon with "PDF" text
    expect(screen.getByText("PDF")).toBeInTheDocument();
  });

  it("shows fallback for image mimetype when ThumbnailImage fails", () => {
    render(
      <PreviewAttachment
        attachment={makePdfAttachment({
          mimetype: "image/png",
          filename: "photo.png",
        })}
      />,
    );

    expect(screen.getByTestId("thumbnail-image")).toBeInTheDocument();

    act(() => {
      capturedOnError?.();
    });

    // Image fallback shows the image SVG icon
    expect(screen.queryByTestId("thumbnail-image")).not.toBeInTheDocument();
  });

  it("resets thumbnailFailed when file_id changes", () => {
    const { rerender } = render(
      <PreviewAttachment attachment={makePdfAttachment()} />,
    );

    // Trigger error
    act(() => {
      capturedOnError?.();
    });

    // Fallback is showing
    expect(screen.queryByTestId("thumbnail-image")).not.toBeInTheDocument();

    // Rerender with new file_id — should reset and try thumbnail again
    rerender(
      <PreviewAttachment
        attachment={makePdfAttachment({ file_id: "new-file-456" })}
      />,
    );

    expect(screen.getByTestId("thumbnail-image")).toBeInTheDocument();
  });

  it("shows fallback when status is PROCESSING regardless of mimetype", () => {
    render(
      <PreviewAttachment
        attachment={makePdfAttachment({ status: "PROCESSING" })}
      />,
    );

    // Should show fallback, not ThumbnailImage
    expect(screen.queryByTestId("thumbnail-image")).not.toBeInTheDocument();
  });

  it("shows fallback when status is FAILED", () => {
    render(
      <PreviewAttachment
        attachment={makePdfAttachment({ status: "FAILED" })}
      />,
    );

    expect(screen.queryByTestId("thumbnail-image")).not.toBeInTheDocument();
    expect(screen.getByTestId("attachment-error")).toBeInTheDocument();
  });
});
