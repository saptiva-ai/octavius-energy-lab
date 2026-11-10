import type { JSX } from "react";

interface IconProps {
  className?: string;
}

// BookOpen icon (Deep Research)
const DeepResearchIcon = ({ className }: IconProps) => (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={1.8}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" />
    <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" />
  </svg>
);

// FilePlus2 icon (Add Files)
const AddFilesIcon = ({ className }: IconProps) => (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={1.8}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z" />
    <polyline points="14,2 14,8 20,8" />
    <line x1={12} y1={18} x2={12} y2={12} />
    <line x1={9} y1={15} x2={15} y2={15} />
  </svg>
);

// HardDrive icon (Google Drive)
const GoogleDriveIcon = ({ className }: IconProps) => (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={1.8}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <line x1={22} y1={12} x2={2} y2={12} />
    <path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z" />
    <line x1={6} y1={16} x2={6} y2={20} />
    <line x1={10} y1={16} x2={10} y2={20} />
  </svg>
);

// Globe icon (Web Search)
const WebSearchIcon = ({ className }: IconProps) => (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={1.8}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <circle cx={12} cy={12} r={10} />
    <path d="m4.93 4.93 4.24 4.24" />
    <path d="m14.83 9.17 4.24-4.24" />
    <path d="m14.83 14.83 4.24 4.24" />
    <path d="m9.17 14.83-4.24 4.24" />
    <circle cx={12} cy={12} r={4} />
  </svg>
);

// SquarePen icon (Canvas)
const CanvasIcon = ({ className }: IconProps) => (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={1.8}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <path d="M12 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
    <path d="M18.375 2.625a2.121 2.121 0 1 1 3 3L12 15l-4 1 1-4Z" />
  </svg>
);

// Bot icon (Agent Mode)
const AgentModeIcon = ({ className }: IconProps) => (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={1.8}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <path d="M12 8V4H8" />
    <rect width={16} height={12} x={4} y={8} rx={2} />
    <path d="M2 14h2" />
    <path d="M20 14h2" />
    <path d="M15 13v2" />
    <path d="M9 13v2" />
  </svg>
);

// FileCheck icon (Document Review)
const DocumentReviewIcon = ({ className }: IconProps) => (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={1.8}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z" />
    <polyline points="14,2 14,8 20,8" />
    <path d="m9 15 2 2 4-4" />
  </svg>
);

// FileSearch icon (Audit File - Copiloto Audit)
// DEPRECATED: Audit functionality is now integrated into file attachment cards
// const AuditFileIcon = ({ className }: IconProps) => (
//   <svg
//     viewBox="0 0 24 24"
//     fill="none"
//     stroke="currentColor"
//     strokeWidth={1.8}
//     strokeLinecap="round"
//     strokeLinejoin="round"
//     className={className}
//   >
//     <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z" />
//     <polyline points="14,2 14,8 20,8" />
//     <circle cx={11.5} cy={14.5} r={2.5} />
//     <path d="m13.25 16.25 1.75 1.75" />
//   </svg>
// );

// Store icon (Retail Advisor)
const RetailAdvisorIcon = ({ className }: IconProps) => (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={1.8}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <path d="m2 7 1.5-3h17L22 7" />
    <path d="M4 7v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7" />
    <path d="M2 7h20" />
    <path d="M9 11a3 3 0 0 0 6 0" />
  </svg>
);

export type ToolId =
  | "files"
  | "deep-research"
  | "add-files"
  | "google-drive"
  | "web-search"
  | "canvas"
  | "agent-mode"
  | "document-review"
  | "retail-advisor";

export type Tool = {
  id: ToolId;
  label: string;
  Icon: (props: IconProps) => JSX.Element;
};

export const TOOL_REGISTRY: Record<ToolId, Tool> = {
  files: { id: "files", label: "Agregar archivos", Icon: AddFilesIcon },
  "deep-research": {
    id: "deep-research",
    label: "Deep research",
    Icon: DeepResearchIcon,
  },
  "add-files": { id: "add-files", label: "Add files", Icon: AddFilesIcon },
  "google-drive": {
    id: "google-drive",
    label: "Google Drive",
    Icon: GoogleDriveIcon,
  },
  "web-search": { id: "web-search", label: "Web search", Icon: WebSearchIcon },
  canvas: { id: "canvas", label: "Canvas", Icon: CanvasIcon },
  "agent-mode": { id: "agent-mode", label: "Agent mode", Icon: AgentModeIcon },
  "document-review": {
    id: "document-review",
    label: "Document review",
    Icon: DocumentReviewIcon,
  },
  "retail-advisor": {
    id: "retail-advisor",
    // "Retail advisor" no le decía nada al usuario (feedback de QA,
    // 2026-10-16, punto 10): el chip dice de dónde salen las respuestas.
    label: "Datos de venta e inventario",
    Icon: RetailAdvisorIcon,
  },
  // DEPRECATED: "audit-file" removed - now integrated in file attachment cards
};
