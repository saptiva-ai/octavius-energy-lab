import React from "react";
import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CanvasPanel } from "../canvas-panel";
import { useCanvasStore } from "@/lib/stores/canvas-store";

// Mock all dependencies
jest.mock("@/lib/stores/canvas-store");
jest.mock("@/lib/api-client");
jest.mock("../markdown-renderer", () => ({
  MarkdownRenderer: () => <div>Mocked Markdown</div>,
}));
jest.mock("../mermaid-graph", () => ({
  MermaidGraph: () => <div>Mocked Mermaid</div>,
}));
jest.mock("../views/AuditDetailView", () => ({
  AuditDetailView: () => <div>Mocked Audit</div>,
}));
jest.mock("../CanvasErrorBoundary", () => ({
  CanvasErrorBoundary: ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  ),
}));
// react-markdown@10 es ESM puro (Jest no lo transforma, ver
// transformIgnorePatterns en jest.config.js); PlotlyChartView lo importa
// para narrar el chart, así que se mockea en el mismo punto que
// markdown-renderer arriba.
jest.mock("../charts/canvas-chart-registry", () => ({
  renderCanvasChart: () => <div>Mocked Chart</div>,
}));

describe("CanvasPanel - Keyboard Shortcuts", () => {
  const mockToggleSidebar = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
    (useCanvasStore as unknown as jest.Mock).mockImplementation((selector) =>
      selector({
        activeArtifactId: null,
        isSidebarOpen: false,
        toggleSidebar: mockToggleSidebar,
        activeArtifactData: null,
        activeChart: null,
      }),
    );
  });

  it("should ignore Cmd+Shift+K on Mac (shortcuts removed)", async () => {
    const user = userEvent.setup();
    render(<CanvasPanel />);

    // Simulate Cmd+Shift+K (metaKey + shiftKey)
    await user.keyboard("{Meta>}{Shift>}k{/Shift}{/Meta}");

    // Keyboard shortcuts are disabled; should NOT toggle
    expect(mockToggleSidebar).not.toHaveBeenCalled();
  });

  it("should ignore Ctrl+Shift+K on Windows/Linux (shortcuts removed)", async () => {
    const user = userEvent.setup();
    render(<CanvasPanel />);

    // Simulate Ctrl+Shift+K (ctrlKey + shiftKey)
    await user.keyboard("{Control>}{Shift>}k{/Shift}{/Control}");

    // Keyboard shortcuts are disabled; should NOT toggle
    expect(mockToggleSidebar).not.toHaveBeenCalled();
  });

  it("should not close canvas with Escape when sidebar is open", async () => {
    (useCanvasStore as unknown as jest.Mock).mockImplementation((selector) =>
      selector({
        activeArtifactId: null,
        isSidebarOpen: true, // Canvas is open
        toggleSidebar: mockToggleSidebar,
        activeArtifactData: null,
        activeChart: null,
      }),
    );

    const user = userEvent.setup();
    render(<CanvasPanel />);

    await user.keyboard("{Escape}");

    expect(mockToggleSidebar).not.toHaveBeenCalled();
  });

  it("should ignore Escape when sidebar is closed", async () => {
    (useCanvasStore as unknown as jest.Mock).mockImplementation((selector) =>
      selector({
        activeArtifactId: null,
        isSidebarOpen: false, // Canvas is closed
        toggleSidebar: mockToggleSidebar,
        activeArtifactData: null,
        activeChart: null,
      }),
    );

    const user = userEvent.setup();
    render(<CanvasPanel />);

    await user.keyboard("{Escape}");

    // Should not toggle when already closed
    expect(mockToggleSidebar).not.toHaveBeenCalled();
  });

  it("should prevent default behavior for keyboard shortcuts", async () => {
    render(<CanvasPanel />);

    const preventDefaultSpy = jest.fn();

    // Create a custom keyboard event
    const event = new KeyboardEvent("keydown", {
      key: "k",
      metaKey: true,
      shiftKey: true,
      bubbles: true,
      cancelable: true,
    });

    Object.defineProperty(event, "preventDefault", {
      value: preventDefaultSpy,
    });

    window.dispatchEvent(event);

    // No keyboard handlers registered; preventDefault not called
    expect(preventDefaultSpy).not.toHaveBeenCalled();
  });
});
