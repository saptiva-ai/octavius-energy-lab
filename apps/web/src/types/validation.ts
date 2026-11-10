/**
 * Types for Copiloto Audit - Document Validation System
 *
 * These types mirror the backend schemas defined in apps/api/src/schemas/review.py
 */

export type FindingCategory = "compliance" | "format" | "logo" | "linguistic";
export type FindingSeverity = "critical" | "high" | "medium" | "low";
export type FindingRule = string;

export type EvidenceKind = "text" | "image" | "metric" | "rule";

export interface Location {
  page: number;
  bbox?: [number, number, number, number]; // [x0, y0, x1, y1]
  fragment_id?: string;
  text_snippet?: string;
}

export interface Evidence {
  kind: EvidenceKind;
  data: Record<string, any>;
}

export interface Finding {
  id: string;
  category: FindingCategory;
  rule: FindingRule;
  issue: string;
  severity: FindingSeverity;
  location?: Location;
  suggestion?: string;
  evidence: Evidence[];
}

export interface ValidationSummary {
  total_findings: number;
  findings_by_severity: Record<FindingSeverity, number>;
  findings_by_category?: Record<string, number>;
  disclaimer?: {
    coverage: number;
    total_pages: number;
    pages_with_disclaimer: number;
    missing_pages: number[];
  };
  format?: {
    number_violations: number;
    font_violations: number;
    color_violations: number;
    image_violations?: number;
    fonts_detail?: Array<{ font: string; count: number; sizes: number[] }>;
    colors_detail?: Array<{ color: string; count: number }>;
    dominant_colors?: string[];
    images?: {
      total_images: number;
      pages_with_images: number[];
      largest_image_ratio: number;
      average_image_ratio: number;
    };
  };
  grammar?: {
    total_issues: number;
    spelling_issues: number;
    grammar_issues: number;
    pages_with_issues: number[];
    examples?: Array<{
      type: "grammar" | "spelling";
      page: number;
      text: string;
      suggestion?: string | null;
      rule?: string;
    }>;
  };
  auditors_run: string[];
  auditor_summaries?: Array<{
    auditor_name: string;
    findings_count: number;
  }>;
  total_duration_ms?: number;
  disclaimer_duration_ms?: number;
  format_duration_ms?: number;
  grammar_duration_ms?: number;
  logo_duration_ms?: number;
}

export interface ValidationReportResponse {
  job_id: string;
  status: "pending" | "completed" | "error";
  findings: Finding[];
  summary: ValidationSummary;
  attachments?: {
    overlay_pdf?: string | null;
  };
  error?: string;
  created_at: string;
}

export interface AuditFileState {
  file: File | null;
  uploading: boolean;
  validating: boolean;
  error: string | null;
  documentId: string | null;
  report: ValidationReportResponse | null;
}
