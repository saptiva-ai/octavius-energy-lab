/**
 * Tests for DeepResearchProgress component.
 */

import { render, screen, fireEvent } from "@testing-library/react";
import { DeepResearchProgress } from "../DeepResearchProgress";
import type {
  ResearchEvidenceEvent,
  ResearchPhase,
  ResearchReportEvent,
  ResearchSourceEvent,
} from "../../../hooks/useDeepResearch";

const mockSources: ResearchSourceEvent[] = [
  {
    type: "source",
    id: "source-1",
    title: "AI Impact Study 2024",
    url: "https://example.com/ai-study",
    snippet: "Comprehensive analysis of AI impact in Latin America",
    relevance_score: 0.95,
    timestamp: "2024-01-01T00:00:00Z",
  },
  {
    type: "source",
    id: "source-2",
    title: "FinTech Trends Report",
    url: "https://example.com/fintech-report",
    snippet: "Latest trends in financial technology",
    relevance_score: 0.87,
    timestamp: "2024-01-01T01:00:00Z",
  },
];

const mockEvidences: ResearchEvidenceEvent[] = [
  {
    type: "evidence",
    id: "evidence-1",
    claim: "AI adoption has increased 150% in LATAM",
    support_level: "strong",
    confidence: 0.92,
    sources: ["source-1"],
    timestamp: "2024-01-01T02:00:00Z",
  },
  {
    type: "evidence",
    id: "evidence-2",
    claim: "FinTech investment reached $2.1B in 2024",
    support_level: "mixed",
    confidence: 0.78,
    sources: ["source-2"],
    timestamp: "2024-01-01T03:00:00Z",
  },
];

const mockReport: ResearchReportEvent = {
  type: "report",
  id: "report-1",
  summary: "AI has significant impact on LATAM economy",
  tl_dr: "AI adoption growing rapidly with strong economic impact",
  key_findings: ["150% increase in adoption", "$2.1B investment"],
  methodology: "Comprehensive analysis of multiple sources",
  timestamp: "2024-01-01T04:00:00Z",
};

describe("DeepResearchProgress", () => {
  const defaultProps = {
    query: "AI Impact in LATAM 2024",
    phase: "SEARCH" as ResearchPhase,
    progress: 45,
    sources: mockSources,
    evidences: mockEvidences,
    report: null,
    isStreaming: true,
    onCancel: jest.fn(),
    onClose: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe("Rendering", () => {
    it("renders the research query correctly", () => {
      render(<DeepResearchProgress {...defaultProps} />);
      expect(screen.getByText("AI Impact in LATAM 2024")).toBeInTheDocument();
    });

    it("displays the current phase label", () => {
      render(<DeepResearchProgress {...defaultProps} />);
      expect(screen.getByText("Buscando fuentes")).toBeInTheDocument();
    });

    it("shows progress percentage", () => {
      render(<DeepResearchProgress {...defaultProps} />);
      expect(screen.getByText("45%")).toBeInTheDocument();
    });

    it("renders progress bar with correct width", () => {
      render(<DeepResearchProgress {...defaultProps} />);
      const progressBar = screen.getByRole("progressbar", { hidden: true });
      expect(progressBar).toHaveStyle("width: 45%");
    });
  });

  describe("Phase Transitions", () => {
    const phases: { phase: ResearchPhase; label: string }[] = [
      { phase: "IDLE", label: "Esperando" },
      { phase: "PLAN", label: "Planificando" },
      { phase: "SEARCH", label: "Buscando fuentes" },
      { phase: "EVIDENCE", label: "Evaluando evidencia" },
      { phase: "SYNTHESIS", label: "Sintetizando hallazgos" },
      { phase: "REVIEW", label: "Revisando resultados" },
      { phase: "COMPLETED", label: "Completado" },
      { phase: "FAILED", label: "Fallido" },
    ];

    phases.forEach(({ phase, label }) => {
      it(`displays correct label for ${phase} phase`, () => {
        render(<DeepResearchProgress {...defaultProps} phase={phase} />);
        expect(screen.getByText(label)).toBeInTheDocument();
      });
    });
  });

  describe("Sources Display", () => {
    it("renders sources list correctly", () => {
      render(<DeepResearchProgress {...defaultProps} />);
      expect(screen.getByText("AI Impact Study 2024")).toBeInTheDocument();
      expect(screen.getByText("FinTech Trends Report")).toBeInTheDocument();
    });

    it("shows clickable source URLs", () => {
      render(<DeepResearchProgress {...defaultProps} />);
      const links = screen.getAllByRole("link");
      expect(links).toHaveLength(2);
      expect(links[0]).toHaveAttribute("href", "https://example.com/ai-study");
      expect(links[1]).toHaveAttribute(
        "href",
        "https://example.com/fintech-report",
      );
    });

    it("displays message when no sources available", () => {
      render(<DeepResearchProgress {...defaultProps} sources={[]} />);
      expect(
        screen.getByText("Aún no se han agregado fuentes."),
      ).toBeInTheDocument();
    });

    it("limits sources display to top 4", () => {
      const manySources: ResearchSourceEvent[] = Array.from(
        { length: 10 },
        (_, i) => ({
          type: "source",
          id: `source-${i}`,
          title: `Source ${i}`,
          url: `https://example.com/source-${i}`,
          snippet: `Snippet ${i}`,
          relevance_score: 0.8,
          timestamp: "2024-01-01T00:00:00Z",
        }),
      );

      render(<DeepResearchProgress {...defaultProps} sources={manySources} />);

      // Should only show first 4
      expect(screen.getByText("Source 0")).toBeInTheDocument();
      expect(screen.getByText("Source 3")).toBeInTheDocument();
      expect(screen.queryByText("Source 4")).not.toBeInTheDocument();
    });
  });

  describe("Evidence Display", () => {
    it("renders evidence claims correctly", () => {
      render(<DeepResearchProgress {...defaultProps} />);
      expect(
        screen.getByText("AI adoption has increased 150% in LATAM"),
      ).toBeInTheDocument();
      expect(
        screen.getByText("FinTech investment reached $2.1B in 2024"),
      ).toBeInTheDocument();
    });

    it("shows confidence levels", () => {
      render(<DeepResearchProgress {...defaultProps} />);
      expect(screen.getByText("Confianza: strong")).toBeInTheDocument();
      expect(screen.getByText("Confianza: mixed")).toBeInTheDocument();
    });

    it("displays message when no evidence available", () => {
      render(<DeepResearchProgress {...defaultProps} evidences={[]} />);
      expect(
        screen.getByText("Se están evaluando hallazgos relevantes."),
      ).toBeInTheDocument();
    });

    it("limits evidence display to top 3", () => {
      const manyEvidences: ResearchEvidenceEvent[] = Array.from(
        { length: 8 },
        (_, i) => ({
          type: "evidence",
          id: `evidence-${i}`,
          claim: `Evidence claim ${i}`,
          support_level: "strong",
          confidence: 0.8,
          sources: ["source-1"],
          timestamp: "2024-01-01T00:00:00Z",
        }),
      );

      render(
        <DeepResearchProgress {...defaultProps} evidences={manyEvidences} />,
      );

      // Should only show first 3
      expect(screen.getByText("Evidence claim 0")).toBeInTheDocument();
      expect(screen.getByText("Evidence claim 2")).toBeInTheDocument();
      expect(screen.queryByText("Evidence claim 3")).not.toBeInTheDocument();
    });
  });

  describe("Report Display", () => {
    it("shows TL;DR when report is available", () => {
      render(<DeepResearchProgress {...defaultProps} report={mockReport} />);
      expect(screen.getByText("TL;DR")).toBeInTheDocument();
      expect(
        screen.getByText(
          "AI adoption growing rapidly with strong economic impact",
        ),
      ).toBeInTheDocument();
    });

    it("falls back to summary if no TL;DR", () => {
      const reportWithoutTldr = { ...mockReport, tl_dr: undefined };
      render(
        <DeepResearchProgress {...defaultProps} report={reportWithoutTldr} />,
      );
      expect(
        screen.getByText("AI has significant impact on LATAM economy"),
      ).toBeInTheDocument();
    });

    it("hides report section when no report available", () => {
      render(<DeepResearchProgress {...defaultProps} report={null} />);
      expect(screen.queryByText("TL;DR")).not.toBeInTheDocument();
    });
  });

  describe("Error Handling", () => {
    it("displays error message when provided", () => {
      const errorMessage = "Network error occurred";
      render(
        <DeepResearchProgress {...defaultProps} errorMessage={errorMessage} />,
      );
      expect(screen.getByText(errorMessage)).toBeInTheDocument();
    });

    it("shows default error message for failed phase", () => {
      render(<DeepResearchProgress {...defaultProps} phase="FAILED" />);
      expect(
        screen.getByText(/No se pudo completar la investigación/),
      ).toBeInTheDocument();
    });

    it("changes progress bar color for errors", () => {
      render(<DeepResearchProgress {...defaultProps} phase="FAILED" />);
      const progressBar = screen.getByRole("progressbar", { hidden: true });
      expect(progressBar).toHaveClass("bg-danger/80");
    });

    it("hides sources and evidence sections when there is an error", () => {
      render(
        <DeepResearchProgress {...defaultProps} errorMessage="Test error" />,
      );
      expect(screen.queryByText("Fuentes recientes")).not.toBeInTheDocument();
      expect(
        screen.queryByText("Evidencias destacadas"),
      ).not.toBeInTheDocument();
    });
  });

  describe("Action Buttons", () => {
    it("shows cancel button when streaming and not completed", () => {
      render(<DeepResearchProgress {...defaultProps} />);
      const cancelButton = screen.getByRole("button", { name: /cancelar/i });
      expect(cancelButton).toBeInTheDocument();
      expect(cancelButton).not.toBeDisabled();
    });

    it("disables cancel button when not streaming", () => {
      render(<DeepResearchProgress {...defaultProps} isStreaming={false} />);
      const cancelButton = screen.getByRole("button", { name: /cancelar/i });
      expect(cancelButton).toBeDisabled();
    });

    it("shows close button when completed", () => {
      render(<DeepResearchProgress {...defaultProps} phase="COMPLETED" />);
      expect(
        screen.getByRole("button", { name: /cerrar panel/i }),
      ).toBeInTheDocument();
    });

    it("shows close button when failed", () => {
      render(<DeepResearchProgress {...defaultProps} phase="FAILED" />);
      expect(
        screen.getByRole("button", { name: /cerrar panel/i }),
      ).toBeInTheDocument();
    });

    it("calls onCancel when cancel button is clicked", () => {
      const onCancel = jest.fn();
      render(<DeepResearchProgress {...defaultProps} onCancel={onCancel} />);

      fireEvent.click(screen.getByRole("button", { name: /cancelar/i }));
      expect(onCancel).toHaveBeenCalledTimes(1);
    });

    it("calls onClose when close button is clicked", () => {
      const onClose = jest.fn();
      render(
        <DeepResearchProgress
          {...defaultProps}
          phase="COMPLETED"
          onClose={onClose}
        />,
      );

      fireEvent.click(screen.getByRole("button", { name: /cerrar panel/i }));
      expect(onClose).toHaveBeenCalledTimes(1);
    });
  });

  describe("Progress Calculations", () => {
    it("handles invalid progress values", () => {
      render(<DeepResearchProgress {...defaultProps} progress={NaN} />);
      expect(screen.getByText("0%")).toBeInTheDocument();
    });

    it("clamps progress to 0-100 range", () => {
      render(<DeepResearchProgress {...defaultProps} progress={150} />);
      expect(screen.getByText("100%")).toBeInTheDocument();

      render(<DeepResearchProgress {...defaultProps} progress={-10} />);
      expect(screen.getByText("0%")).toBeInTheDocument();
    });

    it("rounds progress to nearest integer", () => {
      render(<DeepResearchProgress {...defaultProps} progress={67.8} />);
      expect(screen.getByText("68%")).toBeInTheDocument();
    });
  });
});
