'use client'

import { useState } from 'react'
import { useAuthStore } from '../../lib/auth-store'
import { Button } from '../ui'

export function CacheClearButton() {
  const [clearing, setClearing] = useState(false)
  const { clearCache } = useAuthStore()

  const handleClearCache = async () => {
    setClearing(true)
    try {
      // Clear auth store cache
      clearCache()

      // Clear all localStorage items that might be stale
      if (typeof window !== 'undefined') {
        const keys = Object.keys(localStorage)
        keys.forEach(key => {
          if (key.includes('copilotos') || key.includes('auth') || key.includes('chat')) {
            localStorage.removeItem(key)
          }
        })

        // Clear session storage too
        sessionStorage.clear()

        // Force a page reload to ensure fresh state
        setTimeout(() => {
          window.location.reload()
        }, 1000)
      }
    } finally {
      setClearing(false)
    }
  }

  // Only show in development or when there are auth issues
  const shouldShow = process.env.NODE_ENV === 'development' ||
    (typeof window !== 'undefined' && window.location.hostname !== 'localhost')

  if (!shouldShow) return null

  return (
    <div className="fixed bottom-4 right-4 z-50">
      <Button
        onClick={handleClearCache}
        disabled={clearing}
        className="bg-yellow-600 hover:bg-yellow-700 text-white text-xs px-3 py-1"
        size="sm"
      >
        {clearing ? 'Limpiando...' : '🗑️ Limpiar Cache'}
      </Button>
    </div>
  )
}