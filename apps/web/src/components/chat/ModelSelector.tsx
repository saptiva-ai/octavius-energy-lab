"use client";

import * as React from "react";
import { cn } from "../../lib/utils";
import type { UiModel } from "../../config/modelCatalog";

export type ChatModel = {
  id: string;
  value: string;
  label: string;
  description: string;
  tags: string[];
  available?: boolean;
  backendId?: string | null;
};

interface ModelSelectorProps {
  models: ChatModel[];
  selectedModel: string;
  onModelChange: (modelId: string) => void;
  className?: string;
  disabled?: boolean;
}

export function ModelSelector({
  models,
  selectedModel,
  onModelChange,
  className,
  disabled = false,
}: ModelSelectorProps) {
  const [isOpen, setIsOpen] = React.useState(false);
  const [activeModel, setActiveModel] = React.useState(selectedModel);
  const dropdownRef = React.useRef<HTMLDivElement>(null);
  const buttonRef = React.useRef<HTMLButtonElement>(null);
  const popoverId = React.useId();
  const buttonId = React.useId();

  const currentModel = React.useMemo(() => {
    return models.find((model) => model.id === activeModel) ?? models[0];
  }, [activeModel, models]);

  React.useEffect(() => {
    setActiveModel(selectedModel);
  }, [selectedModel]);

  const handleToggle = React.useCallback(() => {
    setIsOpen((prev) => !prev);
  }, []);

  const handleSelect = React.useCallback(
    (model: ChatModel) => {
      if (!model.available) return; // Don't select unavailable models
      setActiveModel(model.id);
      onModelChange(model.id);
      setIsOpen(false);
    },
    [onModelChange],
  );

  React.useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (!dropdownRef.current?.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }

    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [isOpen]);

  return (
    <div ref={dropdownRef} className={cn("relative inline-block", className)}>
      <button
        ref={buttonRef}
        type="button"
        disabled={disabled}
        id={buttonId}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-controls={isOpen ? popoverId : undefined}
        onClick={handleToggle}
        className={cn(
          "flex h-9 items-center gap-2 rounded-lg border border-border/40 bg-surface-2 px-3 text-sm font-medium text-text transition-all",
          "hover:border-border hover:bg-surface",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60",
          isOpen && "border-border bg-surface",
          disabled && "cursor-not-allowed opacity-60",
        )}
      >
        <span className="text-text">{currentModel?.label}</span>
        <svg
          className={cn(
            "h-3.5 w-3.5 text-text-muted transition-transform",
            isOpen && "rotate-180",
          )}
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      {isOpen && (
        <div
          id={popoverId}
          role="listbox"
          aria-labelledby={buttonId}
          className="absolute left-0 top-full z-40 mt-2 w-[22rem] overflow-hidden rounded-xl border border-border bg-surface shadow-card"
        >
          <div className="max-h-[60vh] overflow-y-auto p-2">
            <div className="px-2 pb-2">
              <h3 className="text-sm font-semibold text-text">
                Modelos de chat
              </h3>
              <p className="text-xs text-text-muted">
                Selecciona un modelo orientado a conversación.
              </p>
            </div>
            <div className="space-y-2">
              {models.map((model) => {
                const isActive = model.id === currentModel?.id;
                const isAvailable = model.available !== false;
                return (
                  <button
                    key={model.id}
                    type="button"
                    role="option"
                    aria-selected={isActive}
                    onClick={() => handleSelect(model)}
                    disabled={!isAvailable}
                    className={cn(
                      "group relative flex w-full items-start gap-3 rounded-lg border px-4 py-3 text-left transition-all",
                      isAvailable
                        ? [
                            "border-transparent bg-surface-2/40",
                            "hover:border-border hover:bg-surface-2 hover:shadow-sm",
                            isActive &&
                              "border-primary/60 bg-primary/10 shadow-sm",
                          ]
                        : "cursor-not-allowed border-transparent bg-surface-2/20 opacity-50",
                    )}
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-2">
                        <p
                          className={cn(
                            "font-semibold text-sm",
                            isAvailable ? "text-text" : "text-text-muted",
                          )}
                        >
                          {model.label}
                        </p>
                        {isActive && isAvailable && (
                          <span
                            className="h-1.5 w-1.5 flex-shrink-0 rounded-full bg-primary"
                            aria-label="Modelo seleccionado"
                          />
                        )}
                        {!isAvailable && (
                          <span className="text-[10px] font-medium uppercase tracking-wider text-text-muted">
                            No disponible
                          </span>
                        )}
                      </div>
                      {model.description && (
                        <p
                          className={cn(
                            "mt-1.5 text-xs leading-relaxed",
                            isAvailable
                              ? "text-text-muted"
                              : "text-text-muted/70",
                          )}
                        >
                          {model.description}
                        </p>
                      )}
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
