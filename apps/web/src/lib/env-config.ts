/**
 * ENV-only Configuration Service
 * Manages SAPTIVA API configuration without UI exposure
 */

interface SaptivaConfig {
  apiKey: string | null
  baseUrl: string
  isDemoMode: boolean
}

const DEFAULT_BASE_URL = 'https://api.saptiva.com'

/**
 * Get SAPTIVA configuration from environment variables only
 * No localStorage or UI inputs allowed per security requirements
 */
export function getSaptivaConfig(): SaptivaConfig {
  // Only read from environment variables
  const apiKey = process.env.SAPTIVA_API_KEY || null
  const baseUrl = process.env.NEXT_PUBLIC_SAPTIVA_BASE_URL || DEFAULT_BASE_URL

  return {
    apiKey,
    baseUrl,
    isDemoMode: !apiKey, // Demo mode when no API key is available
  }
}

/**
 * Check if SAPTIVA is properly configured
 */
export function isSaptivaConfigured(): boolean {
  const config = getSaptivaConfig()
  return config.apiKey !== null && config.apiKey.length > 0
}

/**
 * Get demo mode status
 */
export function isDemoMode(): boolean {
  return getSaptivaConfig().isDemoMode
}

/**
 * Get configuration for API client
 */
export function getApiClientConfig() {
  const config = getSaptivaConfig()

  return {
    baseUrl: config.baseUrl,
    headers: config.apiKey ? {
      'Authorization': `Bearer ${config.apiKey}`,
      'Content-Type': 'application/json',
    } : {
      'Content-Type': 'application/json',
    },
    isDemoMode: config.isDemoMode,
  }
}

/**
 * Demo mode message for user notification
 */
export function getDemoModeMessage(): string | null {
  if (!isDemoMode()) return null

  return 'Modo demo activo. Configura SAPTIVA_API_KEY en variables de entorno para funcionalidad completa.'
}