import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MessageFeedback } from "../MessageFeedback";

describe("MessageFeedback", () => {
  const mockOnFeedback = jest.fn();
  const defaultProps = {
    messageId: "msg_123",
    conversationId: "conv_456",
    onFeedback: mockOnFeedback,
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe("Initial Rendering", () => {
    it("should render thumbs up and thumbs down buttons", () => {
      render(<MessageFeedback {...defaultProps} />);

      const thumbsUpButton = screen.getByLabelText("Respuesta útil");
      const thumbsDownButton = screen.getByLabelText("Respuesta no útil");

      expect(thumbsUpButton).toBeInTheDocument();
      expect(thumbsDownButton).toBeInTheDocument();
    });

    it("should not show comment textarea initially", () => {
      render(<MessageFeedback {...defaultProps} />);

      const textarea = screen.queryByRole("textbox");
      expect(textarea).not.toBeInTheDocument();
    });
  });

  describe("Thumbs Up Flow", () => {
    it("should show comment textarea when thumbs up is clicked", async () => {
      render(<MessageFeedback {...defaultProps} />);

      const thumbsUpButton = screen.getByLabelText("Respuesta útil");
      fireEvent.click(thumbsUpButton);

      await waitFor(() => {
        const textarea = screen.getByPlaceholderText(
          "¿Qué te gustó de esta respuesta? (opcional)",
        );
        expect(textarea).toBeInTheDocument();
      });
    });

    it("should submit thumbs up without comment", async () => {
      mockOnFeedback.mockResolvedValue(undefined);
      render(<MessageFeedback {...defaultProps} />);

      // Click thumbs up
      const thumbsUpButton = screen.getByLabelText("Respuesta útil");
      fireEvent.click(thumbsUpButton);

      // Submit without comment
      await waitFor(() => {
        const submitButton = screen.getByText("Enviar");
        fireEvent.click(submitButton);
      });

      await waitFor(() => {
        expect(mockOnFeedback).toHaveBeenCalledWith("msg_123", "up", undefined);
      });
    });

    it("should submit thumbs up with comment", async () => {
      mockOnFeedback.mockResolvedValue(undefined);
      render(<MessageFeedback {...defaultProps} />);

      // Click thumbs up
      const thumbsUpButton = screen.getByLabelText("Respuesta útil");
      fireEvent.click(thumbsUpButton);

      // Enter comment
      await waitFor(() => {
        const textarea = screen.getByPlaceholderText(
          "¿Qué te gustó de esta respuesta? (opcional)",
        );
        fireEvent.change(textarea, {
          target: { value: "Datos precisos y rápidos" },
        });
      });

      // Submit
      const submitButton = screen.getByText("Enviar");
      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(mockOnFeedback).toHaveBeenCalledWith(
          "msg_123",
          "up",
          "Datos precisos y rápidos",
        );
      });
    });

    it("should show confirmation message after successful submission", async () => {
      mockOnFeedback.mockResolvedValue(undefined);
      render(<MessageFeedback {...defaultProps} />);

      // Submit feedback
      const thumbsUpButton = screen.getByLabelText("Respuesta útil");
      fireEvent.click(thumbsUpButton);

      await waitFor(() => {
        const submitButton = screen.getByText("Enviar");
        fireEvent.click(submitButton);
      });

      // Check for confirmation
      await waitFor(() => {
        expect(screen.getByText("Gracias por tu feedback")).toBeInTheDocument();
      });
    });
  });

  describe("Thumbs Down Flow", () => {
    it("should show comment textarea when thumbs down is clicked", async () => {
      render(<MessageFeedback {...defaultProps} />);

      const thumbsDownButton = screen.getByLabelText("Respuesta no útil");
      fireEvent.click(thumbsDownButton);

      await waitFor(() => {
        const textarea = screen.getByPlaceholderText(
          "¿Qué podría mejorar? (opcional)",
        );
        expect(textarea).toBeInTheDocument();
      });
    });

    it("should submit thumbs down without comment", async () => {
      mockOnFeedback.mockResolvedValue(undefined);
      render(<MessageFeedback {...defaultProps} />);

      // Click thumbs down
      const thumbsDownButton = screen.getByLabelText("Respuesta no útil");
      fireEvent.click(thumbsDownButton);

      // Submit without comment
      await waitFor(() => {
        const submitButton = screen.getByText("Enviar");
        fireEvent.click(submitButton);
      });

      await waitFor(() => {
        expect(mockOnFeedback).toHaveBeenCalledWith(
          "msg_123",
          "down",
          undefined,
        );
      });
    });

    it("should submit thumbs down with reason", async () => {
      mockOnFeedback.mockResolvedValue(undefined);
      render(<MessageFeedback {...defaultProps} />);

      // Click thumbs down
      const thumbsDownButton = screen.getByLabelText("Respuesta no útil");
      fireEvent.click(thumbsDownButton);

      // Enter reason
      await waitFor(() => {
        const textarea = screen.getByPlaceholderText(
          "¿Qué podría mejorar? (opcional)",
        );
        fireEvent.change(textarea, {
          target: { value: "El dato no coincide con mi reporte" },
        });
      });

      // Submit
      const submitButton = screen.getByText("Enviar");
      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(mockOnFeedback).toHaveBeenCalledWith(
          "msg_123",
          "down",
          "El dato no coincide con mi reporte",
        );
      });
    });
  });

  describe("Cancel Flow", () => {
    it("should hide comment box when cancel is clicked", async () => {
      render(<MessageFeedback {...defaultProps} />);

      // Click thumbs up
      const thumbsUpButton = screen.getByLabelText("Respuesta útil");
      fireEvent.click(thumbsUpButton);

      // Wait for textarea to appear
      await waitFor(() => {
        expect(screen.getByRole("textbox")).toBeInTheDocument();
      });

      // Click cancel
      const cancelButton = screen.getByText("Cancelar");
      fireEvent.click(cancelButton);

      // Textarea should disappear
      await waitFor(() => {
        expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
      });
    });

    it("should reset rating when cancel is clicked", async () => {
      render(<MessageFeedback {...defaultProps} />);

      // Click thumbs down
      const thumbsDownButton = screen.getByLabelText("Respuesta no útil");
      fireEvent.click(thumbsDownButton);

      // Enter text
      await waitFor(() => {
        const textarea = screen.getByRole("textbox");
        fireEvent.change(textarea, { target: { value: "Test reason" } });
      });

      // Click cancel
      const cancelButton = screen.getByText("Cancelar");
      fireEvent.click(cancelButton);

      // Click thumbs up again - should show thumbs up placeholder
      const thumbsUpButton = screen.getByLabelText("Respuesta útil");
      fireEvent.click(thumbsUpButton);

      await waitFor(() => {
        const textarea = screen.getByPlaceholderText(
          "¿Qué te gustó de esta respuesta? (opcional)",
        );
        expect(textarea).toBeInTheDocument();
        expect(textarea).toHaveValue("");
      });
    });
  });

  describe("Error Handling", () => {
    it("should handle submission error gracefully", async () => {
      const consoleErrorSpy = jest
        .spyOn(console, "error")
        .mockImplementation(() => {});
      mockOnFeedback.mockRejectedValue(new Error("Network error"));

      render(<MessageFeedback {...defaultProps} />);

      // Submit feedback
      const thumbsUpButton = screen.getByLabelText("Respuesta útil");
      fireEvent.click(thumbsUpButton);

      await waitFor(() => {
        const submitButton = screen.getByText("Enviar");
        fireEvent.click(submitButton);
      });

      // Should log error
      await waitFor(() => {
        expect(consoleErrorSpy).toHaveBeenCalled();
      });

      // Should stay in collecting state (not show confirmation)
      expect(
        screen.queryByText("Gracias por tu feedback"),
      ).not.toBeInTheDocument();
      expect(screen.getByRole("textbox")).toBeInTheDocument();

      consoleErrorSpy.mockRestore();
    });

    it("should disable buttons during submission", async () => {
      mockOnFeedback.mockImplementation(
        () => new Promise((resolve) => setTimeout(resolve, 100)),
      );

      render(<MessageFeedback {...defaultProps} />);

      // Click thumbs up
      const thumbsUpButton = screen.getByLabelText("Respuesta útil");
      fireEvent.click(thumbsUpButton);

      // Click submit
      await waitFor(() => {
        const submitButton = screen.getByText("Enviar");
        fireEvent.click(submitButton);
      });

      // Buttons should be disabled during submission (button text changes to "Loading...")
      await waitFor(() => {
        const loadingButton = screen.getByText("Loading...");
        const cancelButton = screen.getByText("Cancelar");

        expect(loadingButton).toHaveAttribute("disabled");
        expect(cancelButton).toHaveAttribute("disabled");
      });
    });
  });

  describe("Accessibility", () => {
    it("should have aria-labels on buttons", () => {
      render(<MessageFeedback {...defaultProps} />);

      expect(screen.getByLabelText("Respuesta útil")).toBeInTheDocument();
      expect(screen.getByLabelText("Respuesta no útil")).toBeInTheDocument();
    });

    it("should autofocus textarea when opened", async () => {
      render(<MessageFeedback {...defaultProps} />);

      const thumbsUpButton = screen.getByLabelText("Respuesta útil");
      fireEvent.click(thumbsUpButton);

      await waitFor(() => {
        const textarea = screen.getByRole("textbox");
        expect(textarea).toHaveFocus();
      });
    });

    it("should limit comment length to 500 characters", async () => {
      render(<MessageFeedback {...defaultProps} />);

      const thumbsDownButton = screen.getByLabelText("Respuesta no útil");
      fireEvent.click(thumbsDownButton);

      await waitFor(() => {
        const textarea = screen.getByRole("textbox");
        expect(textarea).toHaveAttribute("maxLength", "500");
      });
    });
  });
});
