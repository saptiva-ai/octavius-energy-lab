'use client'

import * as React from 'react'
import { cn } from '@/lib/utils'

interface ChatSkeletonProps {
  className?: string
}

/**
 * ChatSkeleton - Placeholder shown during conversation creation/hydration
 * Prevents flash of empty content during optimistic UI transitions
 */
export function ChatSkeleton({ className }: ChatSkeletonProps) {
  return (
    <div className={cn('flex h-full flex-col items-center justify-center px-4', className)}>
      <div className="w-full max-w-3xl space-y-8">
        {/* Skeleton conversation bubbles */}
        <div className="space-y-6 animate-pulse">
          {/* User message skeleton */}
          <div className="flex justify-end">
            <div className="max-w-[80%] space-y-2">
              <div className="h-16 bg-white/5 rounded-2xl rounded-tr-sm" />
            </div>
          </div>

          {/* Assistant message skeleton */}
          <div className="flex justify-start">
            <div className="max-w-[80%] space-y-3">
              <div className="h-20 bg-white/5 rounded-2xl rounded-tl-sm" />
              <div className="h-16 bg-white/5 rounded-2xl rounded-tl-sm w-5/6" />
            </div>
          </div>
        </div>

        {/* Loading indicator */}
        <div className="flex items-center justify-center gap-2 text-sm text-white/40">
          <svg
            className="h-4 w-4 animate-spin"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              strokeWidth="3"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
            />
          </svg>
          <span>Preparando conversación...</span>
        </div>
      </div>
    </div>
  )
}
