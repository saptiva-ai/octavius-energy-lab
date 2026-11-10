/**
 * Tests for CanvasErrorBoundary Component
 */

import { render, screen, fireEvent } from "@testing-library/react";
import { CanvasErrorBoundary } from "../CanvasErrorBoundary";

// Component that throws an error
const ThrowError = ({ shouldThrow }: { shouldThrow: boolean }) => {
  if (shouldThrow) {
    throw new Error("Test error message");
  }
  return <div>Content loaded successfully</div>;
};

describe("CanvasErrorBoundary", () => {
  // Suppress console.error for these tests
  const originalError = console.error;
  beforeAll(() => {
    console.error = jest.fn();
  });

  afterAll(() => {
    console.error = originalError;
  });

  it("should render children when there is no error", () => {
    render(
      <CanvasErrorBoundary>
        <div>Test content</div>
      </CanvasErrorBoundary>,
    );

    expect(screen.getByText("Test content")).toBeInTheDocument();
  });

  it("should render error UI when child component throws", () => {
    render(
      <CanvasErrorBoundary>
        <ThrowError shouldThrow={true} />
      </CanvasErrorBoundary>,
    );

    expect(
      screen.getByText("Error al cargar el contenido"),
    ).toBeInTheDocument();
  });

  it("should display error message", () => {
    render(
      <CanvasErrorBoundary>
        <ThrowError shouldThrow={true} />
      </CanvasErrorBoundary>,
    );

    expect(
      screen.getByText(/Ocurrió un error al intentar mostrar este contenido/i),
    ).toBeInTheDocument();
  });

  it("should show technical details in a collapsible section", () => {
    render(
      <CanvasErrorBoundary>
        <ThrowError shouldThrow={true} />
      </CanvasErrorBoundary>,
    );

    const details = screen.getByText("Detalles técnicos");
    expect(details).toBeInTheDocument();

    // Error message should be in the details
    expect(screen.getByText("Test error message")).toBeInTheDocument();
  });

  it("should render retry button", () => {
    render(
      <CanvasErrorBoundary>
        <ThrowError shouldThrow={true} />
      </CanvasErrorBoundary>,
    );

    const retryButton = screen.getByRole("button", { name: /reintentar/i });
    expect(retryButton).toBeInTheDocument();
  });

  it("should allow retry when button is clicked", () => {
    render(
      <CanvasErrorBoundary>
        <ThrowError shouldThrow={true} />
      </CanvasErrorBoundary>,
    );

    // Error UI should be visible
    expect(
      screen.getByText("Error al cargar el contenido"),
    ).toBeInTheDocument();

    const retryButton = screen.getByRole("button", { name: /reintentar/i });

    // Verify button is clickable (doesn't throw)
    expect(() => fireEvent.click(retryButton)).not.toThrow();
  });

  it("should display warning icon", () => {
    const { container } = render(
      <CanvasErrorBoundary>
        <ThrowError shouldThrow={true} />
      </CanvasErrorBoundary>,
    );

    // Check for SVG icon (ExclamationTriangleIcon)
    const svg = container.querySelector("svg");
    expect(svg).toBeInTheDocument();
  });
});
