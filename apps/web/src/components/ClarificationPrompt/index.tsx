"use client";

import * as React from "react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "../../lib/utils";
import { Button } from "../ui";
import { ClarificationPromptProps } from "./types";

export function ClarificationPrompt({
  payload,
  onResolve,
  className,
}: ClarificationPromptProps) {
  const [selections, setSelections] = React.useState<Record<string, string>>(
    {},
  );
  const [activeStep, setActiveStep] = React.useState(0);

  // FIX: Robustly derive clarifications array to handle both legacy and new formats
  const clarifications = React.useMemo(() => {
    if (payload.clarifications && Array.isArray(payload.clarifications)) {
      return payload.clarifications;
    }
    // Fallback for new backend format (options list)
    if (payload.options && Array.isArray(payload.options)) {
      return [
        {
          field: "selected_option",
          question: payload.message || "Por favor selecciona una opción",
          reason: "Selection required", // Mock reason
          options: payload.options.map((opt: any) => ({
            value: opt.id || opt.value, // Handle both id and value
            label: opt.label,
            description: opt.description,
          })),
        },
      ];
    }
    return [];
  }, [payload]);

  const currentField = clarifications[activeStep];
  const isLastStep = activeStep === clarifications.length - 1;

  const handleOptionClick = (field: string, value: string) => {
    const nextSelections = { ...selections, [field]: value };
    setSelections(nextSelections);

    if (isLastStep) {
      onResolve(nextSelections);
    } else {
      setActiveStep((prev) => prev + 1);
    }
  };

  if (!currentField) return null;

  const hasSuggested =
    payload.related_queries && payload.related_queries.length > 0;

  return (
    <div
      className={cn(
        "my-4 p-5 rounded-2xl bg-surface-2 border border-border shadow-sm max-w-xl",
        className,
      )}
      data-testid="clarification-prompt"
    >
      <div className="flex items-center gap-2 mb-4">
        <div
          className="flex h-6 w-6 items-center justify-center rounded-full bg-primary/20 text-primary text-xs font-bold"
          data-testid="clarification-step"
        >
          {activeStep + 1}
        </div>
        <span className="text-xs font-semibold uppercase tracking-wider text-muted">
          Paso {activeStep + 1} de {clarifications.length}
        </span>
      </div>

      <h3 className="text-sm font-medium text-foreground mb-4">
        {currentField.question}
      </h3>

      <div className="flex flex-wrap gap-2">
        <AnimatePresence mode="wait">
          <motion.div
            key={currentField.field}
            initial={{ opacity: 0, x: 10 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -10 }}
            transition={{ duration: 0.2 }}
            className="flex flex-wrap gap-2"
          >
            {currentField.options.map((option) => (
              <button
                key={option.value}
                onClick={() =>
                  handleOptionClick(currentField.field, option.value)
                }
                className="px-4 py-2 rounded-xl bg-surface border border-border hover:border-primary hover:bg-primary/5 text-sm transition-all duration-200 text-left group"
                data-testid={`clarification-option-${option.value}`}
              >
                <div className="font-medium text-foreground group-hover:text-primary">
                  {option.label}
                </div>
                {option.description && (
                  <div className="text-xs text-muted leading-tight mt-0.5">
                    {option.description}
                  </div>
                )}
              </button>
            ))}
          </motion.div>
        </AnimatePresence>
      </div>

      {activeStep > 0 && (
        <button
          onClick={() => setActiveStep((prev) => prev - 1)}
          className="mt-4 text-xs text-muted hover:text-foreground transition-colors flex items-center gap-1"
        >
          <svg
            className="h-3 w-3"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M15 19l-7-7 7-7"
            />
          </svg>
          Volver al paso anterior
        </button>
      )}

      {hasSuggested && (
        <div className="mt-4 space-y-3">
          {payload.related_queries && payload.related_queries.length > 0 && (
            <div>
              <div className="text-xs font-semibold text-muted mb-1">
                Preguntas relacionadas
              </div>
              <div className="flex flex-col gap-1">
                {payload.related_queries.slice(0, 5).map((q) => (
                  <button
                    key={q}
                    onClick={() => onResolve({ quick_query: q })}
                    className="text-left text-sm text-primary hover:underline"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
