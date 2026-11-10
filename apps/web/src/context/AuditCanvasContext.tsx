"use client";

import React, { createContext, useContext, useState, useCallback } from "react";
import type { AuditReportResponse } from "@/lib/types";

interface AuditCanvasState {
  isOpen: boolean;
  activeReport: AuditReportResponse | null;
  openCanvas: (report: AuditReportResponse) => void;
  closeCanvas: () => void;
}

const AuditCanvasContext = createContext<AuditCanvasState | undefined>(
  undefined,
);

export function AuditCanvasProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [activeReport, setActiveReport] = useState<AuditReportResponse | null>(
    null,
  );

  const openCanvas = useCallback((report: AuditReportResponse) => {
    setActiveReport(report);
    setIsOpen(true);
  }, []);

  const closeCanvas = useCallback(() => {
    setIsOpen(false);
    setActiveReport(null);
  }, []);

  return (
    <AuditCanvasContext.Provider
      value={{ isOpen, activeReport, openCanvas, closeCanvas }}
    >
      {children}
    </AuditCanvasContext.Provider>
  );
}

export function useAuditCanvas(): AuditCanvasState {
  const ctx = useContext(AuditCanvasContext);
  if (!ctx) {
    throw new Error(
      "useAuditCanvas must be used within an AuditCanvasProvider",
    );
  }
  return ctx;
}
