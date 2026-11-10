/**
 * Critical tests for ModelSelector.tsx
 *
 * Coverage goals:
 * - Model selection: User clicks, state updates, callback fires
 * - Disabled state: Button disabled, no selection possible
 * - Unavailable models: Cannot be selected, visual indicator
 * - Click outside: Dropdown closes
 * - Accessibility: ARIA attributes, roles
 * - Display: Current model label, dropdown open/close
 */

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ModelSelector, type ChatModel } from "../ModelSelector";

describe("ModelSelector", () => {
  const mockModels: ChatModel[] = [
    {
      id: "turbo",
      value: "SAPTIVA_TURBO",
      label: "Saptiva Turbo",
      description: "Fast and efficient model",
      tags: ["fast", "recommended"],
      available: true,
      backendId: "SAPTIVA_TURBO",
    },
    {
      id: "cortex",
      value: "SAPTIVA_CORTEX",
      label: "Saptiva Cortex",
      description: "Advanced reasoning model",
      tags: ["advanced"],
      available: true,
      backendId: "SAPTIVA_CORTEX",
    },
    {
      id: "premium",
      value: "SAPTIVA_PREMIUM",
      label: "Saptiva Premium",
      description: "Premium model (requires upgrade)",
      tags: ["premium"],
      available: false,
      backendId: null,
    },
  ];

  const mockOnModelChange = jest.fn();

  beforeEach(() => {
    mockOnModelChange.mockClear();
  });

  describe("Display", () => {
    it("renders with current model label", () => {
      render(
        <ModelSelector
          models={mockModels}
          selectedModel="turbo"
          onModelChange={mockOnModelChange}
        />,
      );

      expect(screen.getByText("Saptiva Turbo")).toBeInTheDocument();
    });

    it("falls back to first model if selected model not found", () => {
      render(
        <ModelSelector
          models={mockModels}
          selectedModel="non-existent"
          onModelChange={mockOnModelChange}
        />,
      );

      // Should fallback to first model
      expect(screen.getByText("Saptiva Turbo")).toBeInTheDocument();
    });

    it("updates display when selectedModel prop changes", () => {
      const { rerender } = render(
        <ModelSelector
          models={mockModels}
          selectedModel="turbo"
          onModelChange={mockOnModelChange}
        />,
      );

      expect(screen.getByText("Saptiva Turbo")).toBeInTheDocument();

      rerender(
        <ModelSelector
          models={mockModels}
          selectedModel="cortex"
          onModelChange={mockOnModelChange}
        />,
      );

      expect(screen.getByText("Saptiva Cortex")).toBeInTheDocument();
    });
  });

  describe("Dropdown Interaction", () => {
    it("opens dropdown when button is clicked", () => {
      render(
        <ModelSelector
          models={mockModels}
          selectedModel="turbo"
          onModelChange={mockOnModelChange}
        />,
      );

      const button = screen.getByRole("button");
      fireEvent.click(button);

      // Check for dropdown content
      expect(screen.getByRole("listbox")).toBeInTheDocument();
      expect(screen.getByText("Modelos de chat")).toBeInTheDocument();
    });

    it("closes dropdown when button is clicked again", () => {
      render(
        <ModelSelector
          models={mockModels}
          selectedModel="turbo"
          onModelChange={mockOnModelChange}
        />,
      );

      const button = screen.getByRole("button");

      // Open
      fireEvent.click(button);
      expect(screen.getByRole("listbox")).toBeInTheDocument();

      // Close
      fireEvent.click(button);
      expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    });

    it("closes dropdown when clicking outside", async () => {
      render(
        <div>
          <ModelSelector
            models={mockModels}
            selectedModel="turbo"
            onModelChange={mockOnModelChange}
          />
          <div data-testid="outside">Outside element</div>
        </div>,
      );

      const button = screen.getByRole("button");
      fireEvent.click(button);

      expect(screen.getByRole("listbox")).toBeInTheDocument();

      // Click outside
      const outsideElement = screen.getByTestId("outside");
      fireEvent.mouseDown(outsideElement);

      await waitFor(() => {
        expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
      });
    });
  });

  describe("Model Selection", () => {
    it("selects model when clicked", () => {
      render(
        <ModelSelector
          models={mockModels}
          selectedModel="turbo"
          onModelChange={mockOnModelChange}
        />,
      );

      const button = screen.getByRole("button");
      fireEvent.click(button);

      // Click on Cortex model
      const cortexOption = screen.getByText("Saptiva Cortex");
      fireEvent.click(cortexOption);

      expect(mockOnModelChange).toHaveBeenCalledWith("cortex");
    });

    it("closes dropdown after selection", () => {
      render(
        <ModelSelector
          models={mockModels}
          selectedModel="turbo"
          onModelChange={mockOnModelChange}
        />,
      );

      const button = screen.getByRole("button");
      fireEvent.click(button);

      const cortexOption = screen.getByText("Saptiva Cortex");
      fireEvent.click(cortexOption);

      expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    });

    it("does not select unavailable models", () => {
      render(
        <ModelSelector
          models={mockModels}
          selectedModel="turbo"
          onModelChange={mockOnModelChange}
        />,
      );

      const button = screen.getByRole("button");
      fireEvent.click(button);

      // Try to click premium (unavailable) model
      const premiumOption = screen.getByText("Saptiva Premium");
      fireEvent.click(premiumOption);

      expect(mockOnModelChange).not.toHaveBeenCalled();
    });

    it("shows unavailable indicator for unavailable models", () => {
      render(
        <ModelSelector
          models={mockModels}
          selectedModel="turbo"
          onModelChange={mockOnModelChange}
        />,
      );

      const button = screen.getByRole("button");
      fireEvent.click(button);

      expect(screen.getByText("No disponible")).toBeInTheDocument();
    });
  });

  describe("Disabled State", () => {
    it("disables button when disabled prop is true", () => {
      render(
        <ModelSelector
          models={mockModels}
          selectedModel="turbo"
          onModelChange={mockOnModelChange}
          disabled={true}
        />,
      );

      const button = screen.getByRole("button");
      expect(button).toBeDisabled();
    });

    it("does not open dropdown when disabled", () => {
      render(
        <ModelSelector
          models={mockModels}
          selectedModel="turbo"
          onModelChange={mockOnModelChange}
          disabled={true}
        />,
      );

      const button = screen.getByRole("button");
      fireEvent.click(button);

      expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    });
  });

  describe("Accessibility", () => {
    it("has correct ARIA attributes on button", () => {
      render(
        <ModelSelector
          models={mockModels}
          selectedModel="turbo"
          onModelChange={mockOnModelChange}
        />,
      );

      const button = screen.getByRole("button");
      expect(button).toHaveAttribute("aria-haspopup", "listbox");
      expect(button).toHaveAttribute("aria-expanded", "false");
    });

    it("updates aria-expanded when dropdown opens", () => {
      render(
        <ModelSelector
          models={mockModels}
          selectedModel="turbo"
          onModelChange={mockOnModelChange}
        />,
      );

      const button = screen.getByRole("button");
      fireEvent.click(button);

      expect(button).toHaveAttribute("aria-expanded", "true");
    });

    it("has correct role on dropdown", () => {
      render(
        <ModelSelector
          models={mockModels}
          selectedModel="turbo"
          onModelChange={mockOnModelChange}
        />,
      );

      const button = screen.getByRole("button");
      fireEvent.click(button);

      const listbox = screen.getByRole("listbox");
      expect(listbox).toBeInTheDocument();
    });

    it("marks options with role=option", () => {
      render(
        <ModelSelector
          models={mockModels}
          selectedModel="turbo"
          onModelChange={mockOnModelChange}
        />,
      );

      const button = screen.getByRole("button");
      fireEvent.click(button);

      const options = screen.getAllByRole("option");
      expect(options).toHaveLength(3);
    });

    it("marks selected option with aria-selected", () => {
      render(
        <ModelSelector
          models={mockModels}
          selectedModel="turbo"
          onModelChange={mockOnModelChange}
        />,
      );

      const button = screen.getByRole("button");
      fireEvent.click(button);

      const options = screen.getAllByRole("option");
      const turboOption = options.find(
        (opt) =>
          opt.querySelector('[class*="text-text"]')?.textContent ===
          "Saptiva Turbo",
      );

      expect(turboOption).toHaveAttribute("aria-selected", "true");
    });
  });

  describe("Visual Indicators", () => {
    it("shows selected indicator for current model", () => {
      render(
        <ModelSelector
          models={mockModels}
          selectedModel="turbo"
          onModelChange={mockOnModelChange}
        />,
      );

      const button = screen.getByRole("button");
      fireEvent.click(button);

      const selectedIndicator = screen.getByLabelText("Modelo seleccionado");
      expect(selectedIndicator).toBeInTheDocument();
    });

    it("shows chevron icon that rotates when open", () => {
      const { container } = render(
        <ModelSelector
          models={mockModels}
          selectedModel="turbo"
          onModelChange={mockOnModelChange}
        />,
      );

      const button = screen.getByRole("button");
      const svg = button.querySelector("svg");

      expect(svg).toBeInTheDocument();

      // Open dropdown
      fireEvent.click(button);

      // Check if rotation class is applied (implementation detail)
      expect(svg).toHaveClass("rotate-180");
    });
  });

  describe("Model Descriptions", () => {
    it("displays model descriptions in dropdown", () => {
      render(
        <ModelSelector
          models={mockModels}
          selectedModel="turbo"
          onModelChange={mockOnModelChange}
        />,
      );

      const button = screen.getByRole("button");
      fireEvent.click(button);

      expect(screen.getByText("Fast and efficient model")).toBeInTheDocument();
      expect(screen.getByText("Advanced reasoning model")).toBeInTheDocument();
      expect(
        screen.getByText("Premium model (requires upgrade)"),
      ).toBeInTheDocument();
    });
  });

  describe("Edge Cases", () => {
    it("handles empty models array gracefully", () => {
      render(
        <ModelSelector
          models={[]}
          selectedModel="turbo"
          onModelChange={mockOnModelChange}
        />,
      );

      // Should not crash
      expect(screen.getByRole("button")).toBeInTheDocument();
    });

    it("handles single model", () => {
      const singleModel = [mockModels[0]];

      render(
        <ModelSelector
          models={singleModel}
          selectedModel="turbo"
          onModelChange={mockOnModelChange}
        />,
      );

      const button = screen.getByRole("button");
      fireEvent.click(button);

      const options = screen.getAllByRole("option");
      expect(options).toHaveLength(1);
    });

    it("applies custom className", () => {
      const { container } = render(
        <ModelSelector
          models={mockModels}
          selectedModel="turbo"
          onModelChange={mockOnModelChange}
          className="custom-class"
        />,
      );

      const wrapper = container.firstChild as HTMLElement;
      expect(wrapper).toHaveClass("custom-class");
    });
  });
});
