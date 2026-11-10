/**
 * Cross-tab sync provider
 * This component sets up the sync listeners at the app root level
 */

'use client'

import { useCrossTabSync } from '@/hooks/useCrossTabSync'

export function SyncProvider() {
  useCrossTabSync()
  return null // This component only sets up listeners
}