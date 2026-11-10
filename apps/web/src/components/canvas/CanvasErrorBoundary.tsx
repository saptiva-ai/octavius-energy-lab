"use client";

import * as React from "react";
import { ExclamationTriangleIcon } from "@heroicons/react/24/outline";

interface Props {
  children: React.ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class CanvasErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error("Canvas Error Boundary caught an error:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex h-full flex-col items-center justify-center p-6 text-center">
          <div className="rounded-full bg-red-500/10 p-4 mb-4">
            <ExclamationTriangleIcon className="h-12 w-12 text-red-400" />
          </div>
          <h3 className="text-lg font-semibold text-white mb-2">
            Error al cargar el contenido
          </h3>
          <p className="text-sm text-white/60 mb-4 max-w-md">
            Ocurrió un error al intentar mostrar este contenido en el canvas.
            Intenta cerrar y volver a abrir el panel.
          </p>
          {this.state.error && (
            <details className="mt-4 text-xs text-white/40 max-w-md">
              <summary className="cursor-pointer hover:text-white/60">
                Detalles técnicos
              </summary>
              <pre className="mt-2 overflow-auto rounded-lg bg-white/5 p-3 text-left">
                {this.state.error.message}
              </pre>
            </details>
          )}
          <button
            onClick={() => this.setState({ hasError: false, error: null })}
            className="mt-6 rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-sm text-white hover:border-white/30 hover:bg-white/10 transition-colors"
          >
            Reintentar
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
