"use client";

/**
 * ResultTabs - Displays review results in tabs
 *
 * Tabs:
 * - Resumen: Summary bullets by page
 * - Ortografía: Spelling errors with suggestions
 * - Gramática: Grammar issues with explanations
 * - Estilo: Style improvement notes
 * - Reescrituras: LLM-suggested rewrites with "Aplicar" button
 * - Accesibilidad: WCAG color contrast audit
 */

import { useState } from "react";
import { cn } from "../../lib/utils";

export interface SummaryItem {
  page: number;
  bullets: string[];
}

export interface SpellingFinding {
  page: number;
  span: string;
  suggestions: string[];
}

export interface GrammarFinding {
  page: number;
  span: string;
  rule: string;
  explain: string;
  suggestions: string[];
}

export interface StyleNote {
  page: number;
  issue: string;
  advice: string;
  span?: string;
}

export interface SuggestedRewrite {
  page: number;
  blockId: string;
  original: string;
  proposal: string;
  rationale: string;
}

export interface ColorPair {
  fg: string;
  bg: string;
  ratio: number;
  wcag: "pass" | "fail";
  location?: string;
}

export interface ReviewResults {
  summary: SummaryItem[];
  spelling: SpellingFinding[];
  grammar: GrammarFinding[];
  styleNotes: StyleNote[];
  suggestedRewrites: SuggestedRewrite[];
  colorAudit: {
    pairs: ColorPair[];
    passCount: number;
    failCount: number;
  };
}

export interface ResultTabsProps {
  results: ReviewResults;
  onApplyRewrite?: (blockId: string, proposal: string) => void;
  className?: string;
}

type TabId =
  | "summary"
  | "spelling"
  | "grammar"
  | "style"
  | "rewrites"
  | "accessibility";

export function ResultTabs({
  results,
  onApplyRewrite,
  className,
}: ResultTabsProps) {
  const [activeTab, setActiveTab] = useState<TabId>("summary");

  const tabs: { id: TabId; label: string; count: number }[] = [
    { id: "summary", label: "Resumen", count: results.summary.length },
    { id: "spelling", label: "Ortografía", count: results.spelling.length },
    { id: "grammar", label: "Gramática", count: results.grammar.length },
    { id: "style", label: "Estilo", count: results.styleNotes.length },
    {
      id: "rewrites",
      label: "Reescrituras",
      count: results.suggestedRewrites.length,
    },
    {
      id: "accessibility",
      label: "Accesibilidad",
      count: results.colorAudit.failCount,
    },
  ];

  return (
    <div className={cn("w-full", className)}>
      {/* Tab Headers */}
      <div className="border-b border-border/40 overflow-x-auto">
        <div className="flex gap-1 min-w-max">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={cn(
                "px-4 py-2.5 text-sm font-medium whitespace-nowrap",
                "border-b-2 transition-colors",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60",
                activeTab === tab.id
                  ? "border-primary text-primary"
                  : "border-transparent text-text-muted hover:text-text hover:border-border",
              )}
            >
              {tab.label}
              {tab.count > 0 && (
                <span
                  className={cn(
                    "ml-2 px-1.5 py-0.5 rounded-full text-xs",
                    activeTab === tab.id
                      ? "bg-primary/15 text-primary"
                      : "bg-surface-2 text-text-muted",
                  )}
                >
                  {tab.count}
                </span>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Tab Content */}
      <div className="mt-4">
        {activeTab === "summary" && <SummaryTab items={results.summary} />}
        {activeTab === "spelling" && (
          <SpellingTab findings={results.spelling} />
        )}
        {activeTab === "grammar" && <GrammarTab findings={results.grammar} />}
        {activeTab === "style" && <StyleTab notes={results.styleNotes} />}
        {activeTab === "rewrites" && (
          <RewritesTab
            rewrites={results.suggestedRewrites}
            onApply={onApplyRewrite}
          />
        )}
        {activeTab === "accessibility" && (
          <AccessibilityTab audit={results.colorAudit} />
        )}
      </div>
    </div>
  );
}

function SummaryTab({ items }: { items: SummaryItem[] }) {
  if (items.length === 0) {
    return <EmptyState message="No se generó resumen para este documento." />;
  }

  return (
    <div className="space-y-4">
      {items.map((item, idx) => (
        <div
          key={idx}
          className="rounded-lg border border-border/40 bg-surface p-4"
        >
          <h4 className="text-sm font-medium text-text mb-2">
            Página {item.page}
          </h4>
          <ul className="space-y-1.5 text-sm text-text-muted">
            {item.bullets.map((bullet, bidx) => (
              <li key={bidx} className="flex gap-2">
                <span className="text-primary flex-shrink-0">•</span>
                <span>{bullet}</span>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

function SpellingTab({ findings }: { findings: SpellingFinding[] }) {
  if (findings.length === 0) {
    return (
      <EmptyState message="No se encontraron errores de ortografía." icon="✓" />
    );
  }

  return (
    <div className="space-y-3">
      {findings.map((finding, idx) => (
        <div
          key={idx}
          className="rounded-lg border border-border/40 bg-surface p-3 hover:border-primary/40 transition-colors"
        >
          <div className="flex items-start gap-3">
            <span className="text-xs text-text-muted flex-shrink-0 mt-0.5">
              [p.{finding.page}]
            </span>
            <div className="flex-1 min-w-0">
              <p className="text-sm text-text">
                <span className="line-through text-red-400">
                  {finding.span}
                </span>
              </p>
              {finding.suggestions.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {finding.suggestions.map((suggestion, sidx) => (
                    <button
                      key={sidx}
                      className="px-2 py-0.5 rounded text-xs bg-primary/10 text-primary hover:bg-primary/20 transition-colors"
                    >
                      {suggestion}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function GrammarTab({ findings }: { findings: GrammarFinding[] }) {
  if (findings.length === 0) {
    return (
      <EmptyState message="No se encontraron errores gramaticales." icon="✓" />
    );
  }

  return (
    <div className="space-y-3">
      {findings.map((finding, idx) => (
        <div
          key={idx}
          className="rounded-lg border border-border/40 bg-surface p-3 hover:border-primary/40 transition-colors"
        >
          <div className="flex items-start gap-3">
            <span className="text-xs text-text-muted flex-shrink-0 mt-0.5">
              [p.{finding.page}]
            </span>
            <div className="flex-1 min-w-0">
              <p className="text-sm text-text mb-1">
                <span className="text-yellow-400">{finding.span}</span>
              </p>
              <p className="text-xs text-text-muted mb-2">{finding.explain}</p>
              {finding.suggestions.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {finding.suggestions.map((suggestion, sidx) => (
                    <button
                      key={sidx}
                      className="px-2 py-0.5 rounded text-xs bg-primary/10 text-primary hover:bg-primary/20 transition-colors"
                    >
                      {suggestion}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function StyleTab({ notes }: { notes: StyleNote[] }) {
  if (notes.length === 0) {
    return (
      <EmptyState message="No se encontraron sugerencias de estilo." icon="✓" />
    );
  }

  return (
    <div className="space-y-3">
      {notes.map((note, idx) => (
        <div
          key={idx}
          className="rounded-lg border border-border/40 bg-surface p-3 hover:border-primary/40 transition-colors"
        >
          <div className="flex items-start gap-3">
            <span className="text-xs text-text-muted flex-shrink-0 mt-0.5">
              [p.{note.page}]
            </span>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-text mb-1">{note.issue}</p>
              <p className="text-xs text-text-muted">{note.advice}</p>
              {note.span && (
                <p className="mt-2 text-xs text-primary/70 italic">
                  &ldquo;{note.span}&rdquo;
                </p>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function RewritesTab({
  rewrites,
  onApply,
}: {
  rewrites: SuggestedRewrite[];
  onApply?: (blockId: string, proposal: string) => void;
}) {
  if (rewrites.length === 0) {
    return <EmptyState message="No se generaron reescrituras sugeridas." />;
  }

  return (
    <div className="space-y-4">
      {rewrites.map((rewrite, idx) => (
        <div
          key={idx}
          className="rounded-lg border border-border/40 bg-surface p-4 hover:border-primary/40 transition-colors"
        >
          <div className="flex items-start gap-3 mb-3">
            <span className="text-xs text-text-muted flex-shrink-0 mt-0.5">
              [p.{rewrite.page}]
            </span>
            <div className="flex-1 min-w-0">
              <p className="text-xs text-text-muted mb-2">
                {rewrite.rationale}
              </p>
            </div>
          </div>

          <div className="space-y-3">
            {/* Original */}
            <div>
              <p className="text-xs font-medium text-text-muted mb-1">
                Original:
              </p>
              <p className="text-sm text-text bg-surface-2 rounded p-2">
                {rewrite.original}
              </p>
            </div>

            {/* Proposal */}
            <div>
              <p className="text-xs font-medium text-text-muted mb-1">
                Propuesta:
              </p>
              <p className="text-sm text-primary bg-primary/10 rounded p-2">
                {rewrite.proposal}
              </p>
            </div>
          </div>

          {onApply && (
            <button
              onClick={() => onApply(rewrite.blockId, rewrite.proposal)}
              className={cn(
                "mt-3 px-3 py-1.5 rounded-lg text-xs font-medium",
                "bg-primary text-white hover:bg-primary/90",
                "transition-colors",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60",
              )}
            >
              Aplicar
            </button>
          )}
        </div>
      ))}
    </div>
  );
}

function AccessibilityTab({
  audit,
}: {
  audit: { pairs: ColorPair[]; passCount: number; failCount: number };
}) {
  if (audit.pairs.length === 0) {
    return <EmptyState message="No se encontraron colores para auditar." />;
  }

  const totalCount = audit.passCount + audit.failCount;

  return (
    <div className="space-y-4">
      {/* Stats */}
      <div className="grid grid-cols-3 gap-3">
        <div className="rounded-lg border border-border/40 bg-surface p-3 text-center">
          <p className="text-2xl font-bold text-text">{totalCount}</p>
          <p className="text-xs text-text-muted">Total</p>
        </div>
        <div className="rounded-lg border border-green-500/40 bg-green-500/10 p-3 text-center">
          <p className="text-2xl font-bold text-green-400">{audit.passCount}</p>
          <p className="text-xs text-green-400/70">Pasan WCAG</p>
        </div>
        <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-center">
          <p className="text-2xl font-bold text-red-400">{audit.failCount}</p>
          <p className="text-xs text-red-400/70">Fallan WCAG</p>
        </div>
      </div>

      {/* Pairs */}
      <div className="space-y-3">
        {audit.pairs.map((pair, idx) => (
          <div
            key={idx}
            className={cn(
              "rounded-lg border p-3",
              pair.wcag === "pass"
                ? "border-green-500/40 bg-green-500/5"
                : "border-red-500/40 bg-red-500/5",
            )}
          >
            <div className="flex items-center gap-3">
              {/* Color Preview */}
              <div
                className="w-12 h-12 rounded flex-shrink-0 border border-border/40"
                style={{ backgroundColor: pair.bg, color: pair.fg }}
              >
                <div className="w-full h-full flex items-center justify-center text-xs font-bold">
                  Aa
                </div>
              </div>

              {/* Details */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 text-xs">
                  <code className="text-text">{pair.fg}</code>
                  <span className="text-text-muted">sobre</span>
                  <code className="text-text">{pair.bg}</code>
                </div>
                <p className="text-xs text-text-muted mt-1">
                  Ratio:{" "}
                  <span className="font-medium">{pair.ratio.toFixed(2)}:1</span>
                  {pair.location && (
                    <span className="ml-2">• {pair.location}</span>
                  )}
                </p>
              </div>

              {/* Status Badge */}
              <div
                className={cn(
                  "px-2 py-1 rounded text-xs font-medium",
                  pair.wcag === "pass"
                    ? "bg-green-500/20 text-green-400"
                    : "bg-red-500/20 text-red-400",
                )}
              >
                {pair.wcag === "pass" ? "PASA" : "FALLA"}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function EmptyState({ message, icon }: { message: string; icon?: string }) {
  return (
    <div className="text-center py-12">
      {icon && <div className="text-4xl mb-2">{icon}</div>}
      <p className="text-sm text-text-muted">{message}</p>
    </div>
  );
}
