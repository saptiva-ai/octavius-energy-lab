'use client'

import { useEffect, useRef } from 'react'
import { useRouter } from 'next/navigation'
import { shallow } from 'zustand/shallow'

import { useAuthStore } from '../lib/auth-store'

export function useRequireAuth() {
  const router = useRouter()
  const hasCheckedRef = useRef(false)
  const isRefreshingRef = useRef(false)

  const {
    isHydrated,
    accessToken,
    refreshToken,
    user,
    refreshSession,
    fetchProfile,
    logout,
  } = useAuthStore(
    (state) => ({
      isHydrated: state.isHydrated,
      accessToken: state.accessToken,
      refreshToken: state.refreshToken,
      user: state.user,
      refreshSession: state.refreshSession,
      fetchProfile: state.fetchProfile,
      logout: state.logout,
    }),
    shallow
  )

  // P0-FIX: Prevent refresh loops with single-flight pattern
  useEffect(() => {
    if (!isHydrated || hasCheckedRef.current || isRefreshingRef.current) {
      return
    }

    hasCheckedRef.current = true
    isRefreshingRef.current = true

    const ensureSession = async () => {
      try {
        const refreshed = await refreshSession()
        const currentState = useAuthStore.getState()

        // If refresh failed and we have no access token, logout and redirect
        if (!refreshed && !currentState.accessToken) {
          await logout({ reason: 'session-expired' })
          router.replace('/login?reason=session-expired')
          return
        }

        // If we have token but no user profile, fetch it
        if (currentState.accessToken && !currentState.user) {
          await fetchProfile()
        }
      } finally {
        isRefreshingRef.current = false
      }
    }

    void ensureSession()
  }, [isHydrated, refreshSession, fetchProfile, logout, router])

  // P0-FIX: Secondary check - only redirect if truly no auth state
  useEffect(() => {
    if (!isHydrated) return

    // If refresh is in progress, wait
    if (isRefreshingRef.current) return

    // If we've already checked and have no tokens, redirect
    if (hasCheckedRef.current && !accessToken && !refreshToken) {
      router.replace('/login')
    }
  }, [isHydrated, accessToken, refreshToken, router])

  const isAuthenticated = Boolean(accessToken && user)

  return { isAuthenticated, isHydrated }
}
