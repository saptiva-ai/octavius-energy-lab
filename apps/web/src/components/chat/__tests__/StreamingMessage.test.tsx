/**
 * Unit tests for StreamingMessage component
 *
 * Tests throttled markdown rendering during SSE streaming
 */

import { render, screen, waitFor } from "@testing-library/react";
import { StreamingMessage } from "../StreamingMessage";

// Mock MarkdownMessage component
jest.mock("../MarkdownMessage", () => ({
  MarkdownMessage: ({ content, highlightCode }: any) => (
    <div data-testid="markdown-message" data-highlight-code={highlightCode}>
      {content}
    </div>
  ),
}));

// Mock TypingIndicator component
jest.mock("../../ui/TypingIndicator", () => ({
  TypingIndicator: ({ size }: any) => (
    <div data-testid="typing-indicator" data-size={size}>
      Typing...
    </div>
  ),
  StreamingCursor: () => <div data-testid="streaming-cursor">|</div>,
}));

describe("StreamingMessage", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.runOnlyPendingTimers();
    jest.useRealTimers();
  });

  describe("Initial rendering", () => {
    it("shows typing indicator when streaming with empty content", () => {
      render(
        <StreamingMessage content="" isStreaming={true} isComplete={false} />,
      );

      expect(screen.getByTestId("typing-indicator")).toBeInTheDocument();
      expect(screen.getByTestId("typing-indicator")).toHaveAttribute(
        "data-size",
        "md",
      );
    });

    it("renders markdown immediately when not streaming", () => {
      render(
        <StreamingMessage
          content="# Hello World"
          isStreaming={false}
          isComplete={true}
        />,
      );

      const markdown = screen.getByTestId("markdown-message");
      expect(markdown).toHaveTextContent("# Hello World");
      expect(markdown).toHaveAttribute("data-highlight-code", "true");
    });

    it("renders markdown immediately when complete", () => {
      render(
        <StreamingMessage
          content="Final content"
          isStreaming={false}
          isComplete={true}
        />,
      );

      expect(screen.getByTestId("markdown-message")).toHaveTextContent(
        "Final content",
      );
    });
  });

  describe("Streaming behavior", () => {
    it("shows streaming cursor during active streaming", () => {
      render(
        <StreamingMessage
          content="Streaming text"
          isStreaming={true}
          isComplete={false}
        />,
      );

      expect(screen.getByTestId("streaming-cursor")).toBeInTheDocument();
    });

    it("hides streaming cursor when streaming is complete", () => {
      render(
        <StreamingMessage
          content="Complete text"
          isStreaming={false}
          isComplete={true}
        />,
      );

      expect(screen.queryByTestId("streaming-cursor")).not.toBeInTheDocument();
    });

    it("disables code highlighting during streaming", () => {
      render(
        <StreamingMessage
          content="```python\nprint('hello')\n```"
          isStreaming={true}
          isComplete={false}
        />,
      );

      const markdown = screen.getByTestId("markdown-message");
      expect(markdown).toHaveAttribute("data-highlight-code", "false");
    });

    it("enables code highlighting when streaming completes", async () => {
      const { rerender } = render(
        <StreamingMessage
          content="```python\nprint('hello')\n```"
          isStreaming={true}
          isComplete={false}
        />,
      );

      // Complete streaming
      rerender(
        <StreamingMessage
          content="```python\nprint('hello')\n```"
          isStreaming={false}
          isComplete={true}
        />,
      );

      await waitFor(() => {
        const markdown = screen.getByTestId("markdown-message");
        expect(markdown).toHaveAttribute("data-highlight-code", "true");
      });
    });
  });

  describe("Throttled rendering", () => {
    it("throttles markdown updates during streaming (150ms)", async () => {
      const { rerender } = render(
        <StreamingMessage
          content="Initial"
          isStreaming={true}
          isComplete={false}
        />,
      );

      // Update content rapidly (simulating SSE chunks)
      rerender(
        <StreamingMessage
          content="Initial text"
          isStreaming={true}
          isComplete={false}
        />,
      );

      // Content should still be throttled (not updated immediately)
      expect(screen.getByTestId("markdown-message")).toHaveTextContent(
        "Initial",
      );

      // Advance timers by 150ms
      jest.advanceTimersByTime(150);

      // Now content should be updated
      await waitFor(() => {
        expect(screen.getByTestId("markdown-message")).toHaveTextContent(
          "Initial text",
        );
      });
    });

    it("updates immediately when throttle interval has passed", () => {
      const { rerender } = render(
        <StreamingMessage
          content="First"
          isStreaming={true}
          isComplete={false}
        />,
      );

      // Advance time by 150ms
      jest.advanceTimersByTime(150);

      // Update content (should be immediate since 150ms passed)
      rerender(
        <StreamingMessage
          content="Second"
          isStreaming={true}
          isComplete={false}
        />,
      );

      // Should update immediately
      expect(screen.getByTestId("markdown-message")).toHaveTextContent(
        "Second",
      );
    });

    it("shows final content immediately when streaming ends", async () => {
      const { rerender } = render(
        <StreamingMessage
          content="Initial"
          isStreaming={true}
          isComplete={false}
        />,
      );

      // Update to final content and end streaming
      rerender(
        <StreamingMessage
          content="Final complete content"
          isStreaming={false}
          isComplete={true}
        />,
      );

      // Should update immediately without waiting for throttle
      await waitFor(() => {
        expect(screen.getByTestId("markdown-message")).toHaveTextContent(
          "Final complete content",
        );
      });
    });

    it("handles rapid content updates with throttling", async () => {
      const { rerender } = render(
        <StreamingMessage content="A" isStreaming={true} isComplete={false} />,
      );

      // Simulate rapid SSE chunks
      rerender(
        <StreamingMessage
          content="A B"
          isStreaming={true}
          isComplete={false}
        />,
      );
      rerender(
        <StreamingMessage
          content="A B C"
          isStreaming={true}
          isComplete={false}
        />,
      );
      rerender(
        <StreamingMessage
          content="A B C D"
          isStreaming={true}
          isComplete={false}
        />,
      );

      // Should still show initial content (throttled)
      expect(screen.getByTestId("markdown-message")).toHaveTextContent("A");

      // After 150ms, should show latest content
      jest.advanceTimersByTime(150);
      await waitFor(() => {
        expect(screen.getByTestId("markdown-message")).toHaveTextContent(
          "A B C D",
        );
      });
    });
  });

  describe("Edge cases", () => {
    it("handles empty content gracefully", () => {
      render(
        <StreamingMessage content="" isStreaming={false} isComplete={true} />,
      );

      expect(screen.getByTestId("markdown-message")).toHaveTextContent("");
    });

    it("handles very long content without performance issues", () => {
      const longContent = "Lorem ipsum ".repeat(1000);

      render(
        <StreamingMessage
          content={longContent}
          isStreaming={true}
          isComplete={false}
        />,
      );

      expect(screen.getByTestId("markdown-message")).toBeInTheDocument();
    });

    it("applies custom className", () => {
      const { container } = render(
        <StreamingMessage
          content="Test"
          isStreaming={false}
          isComplete={true}
          className="custom-class"
        />,
      );

      expect(container.firstChild).toHaveClass("custom-class");
    });

    it("transitions from streaming to complete state", async () => {
      const { rerender } = render(
        <StreamingMessage
          content="Streaming..."
          isStreaming={true}
          isComplete={false}
        />,
      );

      expect(screen.getByTestId("streaming-cursor")).toBeInTheDocument();

      // Complete streaming
      rerender(
        <StreamingMessage
          content="Streaming... Done!"
          isStreaming={false}
          isComplete={true}
        />,
      );

      await waitFor(() => {
        expect(
          screen.queryByTestId("streaming-cursor"),
        ).not.toBeInTheDocument();
        expect(screen.getByTestId("markdown-message")).toHaveTextContent(
          "Streaming... Done!",
        );
      });
    });
  });

  describe("Markdown rendering during streaming", () => {
    it("progressively renders markdown with headings", async () => {
      const { rerender } = render(
        <StreamingMessage content="# " isStreaming={true} isComplete={false} />,
      );

      jest.advanceTimersByTime(150);

      rerender(
        <StreamingMessage
          content="# Title"
          isStreaming={true}
          isComplete={false}
        />,
      );

      jest.advanceTimersByTime(150);

      await waitFor(() => {
        expect(screen.getByTestId("markdown-message")).toHaveTextContent(
          "# Title",
        );
      });
    });

    it("progressively renders markdown with lists", async () => {
      const { rerender } = render(
        <StreamingMessage
          content="- Item 1"
          isStreaming={true}
          isComplete={false}
        />,
      );

      jest.advanceTimersByTime(150);

      const listContent = "- Item 1\n- Item 2";
      rerender(
        <StreamingMessage
          content={listContent}
          isStreaming={true}
          isComplete={false}
        />,
      );

      jest.advanceTimersByTime(150);

      await waitFor(() => {
        const markdown = screen.getByTestId("markdown-message");
        expect(markdown.textContent).toContain("Item 1");
        expect(markdown.textContent).toContain("Item 2");
      });
    });

    it("progressively renders markdown with code blocks", async () => {
      const { rerender } = render(
        <StreamingMessage
          content="```python\n"
          isStreaming={true}
          isComplete={false}
        />,
      );

      jest.advanceTimersByTime(150);

      const codeContent = "```python\nprint('hello')";
      rerender(
        <StreamingMessage
          content={codeContent}
          isStreaming={true}
          isComplete={false}
        />,
      );

      jest.advanceTimersByTime(150);

      await waitFor(() => {
        const markdown = screen.getByTestId("markdown-message");
        expect(markdown.textContent).toContain("python");
        expect(markdown.textContent).toContain("print('hello')");
      });
    });
  });
});
