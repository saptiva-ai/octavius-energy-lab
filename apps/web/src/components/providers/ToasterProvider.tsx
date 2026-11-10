'use client'

import { Toaster } from 'react-hot-toast'

/**
 * ToasterProvider
 *
 * Global toast notification provider using react-hot-toast.
 * Styled to match the Saptiva dark theme with mint accents.
 *
 * Features:
 * - Position: bottom-right for non-intrusive feedback
 * - Duration: 4s default (configurable per toast)
 * - Theme: Dark background with mint success/error colors
 * - Accessible: ARIA labels and keyboard dismissible
 */
export function ToasterProvider() {
  return (
    <Toaster
      position="bottom-right"
      reverseOrder={false}
      gutter={8}
      toastOptions={{
        // Default options
        duration: 4000,
        style: {
          background: '#1B1B27',
          color: '#E8EAED',
          border: '1px solid rgba(255, 255, 255, 0.1)',
          borderRadius: '12px',
          fontSize: '14px',
          maxWidth: '420px',
          padding: '12px 16px',
          boxShadow: '0 8px 20px rgba(0, 0, 0, 0.4)',
        },
        // Success toasts
        success: {
          duration: 3000,
          iconTheme: {
            primary: '#49F7D9', // Saptiva mint
            secondary: '#1B1B27',
          },
          style: {
            border: '1px solid rgba(73, 247, 217, 0.3)',
          },
        },
        // Error toasts
        error: {
          duration: 5000,
          iconTheme: {
            primary: '#FF5555',
            secondary: '#1B1B27',
          },
          style: {
            border: '1px solid rgba(255, 85, 85, 0.3)',
          },
        },
        // Loading toasts
        loading: {
          iconTheme: {
            primary: '#49F7D9',
            secondary: '#1B1B27',
          },
        },
      }}
      // Accessible options
      containerStyle={{
        zIndex: 9999,
      }}
    />
  )
}