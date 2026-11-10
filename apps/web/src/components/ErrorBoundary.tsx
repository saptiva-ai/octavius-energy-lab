'use client'

import * as React from 'react'
import { logError } from '../lib/logger'

interface ErrorBoundaryProps {
  children: React.ReactNode
  fallback?: React.ReactNode
  onError?: (error: Error, errorInfo: React.ErrorInfo) => void
}

interface ErrorBoundaryState {
  hasError: boolean
  error: Error | null
}

/**
 * ErrorBoundary Component
 *
 * Catches React errors in child components and displays a fallback UI.
 * Prevents the entire app from crashing when a component fails.
 *
 * Usage:
 * ```tsx
 * <ErrorBoundary fallback={<ErrorFallback />}>
 *   <ConversationList />
 * </ErrorBoundary>
 * ```
 */
export class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = {
      hasError: false,
      error: null,
    }
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    // Update state so the next render will show the fallback UI
    return {
      hasError: true,
      error,
    }
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    // Log error to console and external service
    logError('ErrorBoundary caught an error:', {
      error: error.message,
      stack: error.stack,
      componentStack: errorInfo.componentStack,
    })

    // Call optional onError callback
    if (this.props.onError) {
      this.props.onError(error, errorInfo)
    }
  }

  handleReset = () => {
    this.setState({
      hasError: false,
      error: null,
    })
  }

  render() {
    if (this.state.hasError) {
      // Custom fallback UI
      if (this.props.fallback) {
        return this.props.fallback
      }

      // Default fallback UI
      return (
        <div className="flex min-h-[400px] flex-col items-center justify-center rounded-2xl border border-red-500/20 bg-red-500/5 p-8 text-center">
          <div className="mb-4 text-6xl">⚠️</div>
          <h2 className="mb-2 text-xl font-semibold text-white">Algo salió mal</h2>
          <p className="mb-6 max-w-md text-sm text-saptiva-light/70">
            Ocurrió un error inesperado. Intenta recargar la página o contacta a soporte si el problema persiste.
          </p>

          {/* Error details (only in development) */}
          {process.env.NODE_ENV === 'development' && this.state.error && (
            <details className="mb-6 w-full max-w-2xl rounded-xl bg-black/30 p-4 text-left text-xs">
              <summary className="cursor-pointer font-mono text-red-400">
                Error Details (dev only)
              </summary>
              <pre className="mt-2 overflow-auto text-red-300">
                {this.state.error.message}
                {'\n\n'}
                {this.state.error.stack}
              </pre>
            </details>
          )}

          <div className="flex gap-3">
            <button
              type="button"
              onClick={this.handleReset}
              className="rounded-full bg-[#49F7D9] px-6 py-2 text-sm font-semibold text-white transition-opacity hover:opacity-90"
            >
              Intentar de nuevo
            </button>
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="rounded-full border border-white/20 bg-white/5 px-6 py-2 text-sm font-semibold text-white transition-all hover:bg-white/10"
            >
              Recargar página
            </button>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}

/**
 * Specialized ErrorBoundary for ConversationList
 *
 * Provides a fallback UI specific to the conversation list context.
 */
export function ConversationListErrorBoundary({ children }: { children: React.ReactNode }) {
  return (
    <ErrorBoundary
      fallback={
        <div className="flex min-h-[300px] flex-col items-center justify-center rounded-2xl border border-red-500/20 bg-red-500/5 p-6 text-center">
          <div className="mb-3 text-4xl">💬</div>
          <h3 className="mb-2 font-semibold text-white">Error al cargar conversaciones</h3>
          <p className="mb-4 text-sm text-saptiva-light/70">
            No pudimos cargar tu lista de conversaciones.
          </p>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="rounded-full bg-[#49F7D9] px-4 py-2 text-sm font-semibold text-white transition-opacity hover:opacity-90"
          >
            Recargar
          </button>
        </div>
      }
    >
      {children}
    </ErrorBoundary>
  )
}