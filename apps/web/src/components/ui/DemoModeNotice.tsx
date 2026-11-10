'use client'

import * as React from 'react'
import { isDemoMode, getDemoModeMessage } from '../../lib/env-config'

export function DemoModeNotice() {
  const [isVisible, setIsVisible] = React.useState(false)
  const [isDismissed, setIsDismissed] = React.useState(false)

  React.useEffect(() => {
    // Check if in demo mode and not previously dismissed
    const dismissed = localStorage.getItem('demo-notice-dismissed') === 'true'

    if (isDemoMode() && !dismissed) {
      setIsVisible(true)
    }
  }, [])

  const handleDismiss = () => {
    setIsDismissed(true)
    setIsVisible(false)
    localStorage.setItem('demo-notice-dismissed', 'true')
  }

  if (!isVisible || isDismissed) {
    return null
  }

  const message = getDemoModeMessage()
  if (!message) return null

  return (
    <div className="fixed top-4 right-4 z-50 max-w-sm">
      <div className="rounded-lg border border-yellow-400/20 bg-yellow-900/20 p-4 backdrop-blur-sm">
        <div className="flex items-start gap-3">
          <div className="flex-shrink-0">
            <svg
              className="h-5 w-5 text-yellow-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
          </div>
          <div className="flex-1">
            <p className="text-sm text-yellow-200">
              {message}
            </p>
          </div>
          <button
            onClick={handleDismiss}
            className="flex-shrink-0 text-yellow-400/60 hover:text-yellow-400 transition-colors"
            aria-label="Cerrar aviso"
          >
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  )
}