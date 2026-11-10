/**
 * Cross-tab synchronization using BroadcastChannel API
 * Fallback to polling for browsers without BroadcastChannel support
 */

import { logDebug, logError, logWarn } from './logger'
import { ChatSession } from './types'

// Sync event types
export type SyncEventType =
  | 'session_created'
  | 'session_renamed'
  | 'session_pinned'
  | 'session_deleted'
  | 'sessions_reloaded'

export interface SyncEvent {
  type: SyncEventType
  payload: {
    chatId?: string
    session?: ChatSession
    sessions?: ChatSession[]
    timestamp: number
  }
  source: string // Tab ID for deduplication
}

// Generate unique tab ID
const TAB_ID = `tab-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`

/**
 * Cross-tab sync manager using BroadcastChannel
 */
export class CrossTabSync {
  private channel: BroadcastChannel | null = null
  private listeners: Map<SyncEventType, Set<(event: SyncEvent) => void>> = new Map()
  private isSupported: boolean = false
  private pollingInterval: NodeJS.Timeout | null = null
  private lastPollTimestamp: number = Date.now()
  private pollingDelay: number = 5000 // Default: 5s

  constructor(channelName: string = 'saptiva-chat-sync') {
    // Check BroadcastChannel support
    this.isSupported = typeof window !== 'undefined' && 'BroadcastChannel' in window

    if (this.isSupported) {
      try {
        this.channel = new BroadcastChannel(channelName)
        this.setupBroadcastListener()
        logDebug('BroadcastChannel initialized', { channelName, tabId: TAB_ID })
      } catch (error) {
        logError('Failed to initialize BroadcastChannel:', error)
        this.isSupported = false
      }
    }

    if (!this.isSupported) {
      logWarn('BroadcastChannel not supported, using polling fallback')
      this.startPolling()
    }
  }

  /**
   * Setup BroadcastChannel message listener
   */
  private setupBroadcastListener(): void {
    if (!this.channel) return

    this.channel.onmessage = (event: MessageEvent<SyncEvent>) => {
      const syncEvent = event.data

      // Ignore events from this tab
      if (syncEvent.source === TAB_ID) {
        logDebug('Ignoring own event', { type: syncEvent.type })
        return
      }

      logDebug('Received sync event', {
        type: syncEvent.type,
        source: syncEvent.source,
        chatId: syncEvent.payload.chatId,
      })

      this.handleSyncEvent(syncEvent)
    }
  }

  /**
   * Handle incoming sync event
   */
  private handleSyncEvent(event: SyncEvent): void {
    const listeners = this.listeners.get(event.type)
    if (!listeners || listeners.size === 0) {
      logDebug('No listeners for event type', { type: event.type })
      return
    }

    // Notify all listeners
    listeners.forEach((listener) => {
      try {
        listener(event)
      } catch (error) {
        logError('Error in sync event listener:', error)
      }
    })
  }

  /**
   * Broadcast event to other tabs
   */
  broadcast(type: SyncEventType, payload: Omit<SyncEvent['payload'], 'timestamp'>): void {
    const event: SyncEvent = {
      type,
      payload: {
        ...payload,
        timestamp: Date.now(),
      },
      source: TAB_ID,
    }

    if (this.channel && this.isSupported) {
      try {
        this.channel.postMessage(event)
        logDebug('Broadcasted sync event', { type, chatId: payload.chatId })
      } catch (error) {
        logError('Failed to broadcast sync event:', error)
      }
    } else {
      // Store event for polling fallback
      this.storeEventForPolling(event)
    }
  }

  /**
   * Subscribe to sync events
   */
  on(type: SyncEventType, listener: (event: SyncEvent) => void): () => void {
    if (!this.listeners.has(type)) {
      this.listeners.set(type, new Set())
    }

    this.listeners.get(type)!.add(listener)
    logDebug('Added sync listener', { type, listenersCount: this.listeners.get(type)!.size })

    // Return unsubscribe function
    return () => {
      this.listeners.get(type)?.delete(listener)
      logDebug('Removed sync listener', { type, listenersCount: this.listeners.get(type)?.size || 0 })
    }
  }

  /**
   * Cleanup resources
   */
  cleanup(): void {
    if (this.channel) {
      this.channel.close()
      this.channel = null
      logDebug('BroadcastChannel closed')
    }

    if (this.pollingInterval) {
      clearInterval(this.pollingInterval)
      this.pollingInterval = null
      logDebug('Polling stopped')
    }

    this.listeners.clear()
  }

  // ===============================
  // Polling Fallback Implementation
  // ===============================

  /**
   * Start polling fallback (for browsers without BroadcastChannel)
   */
  private startPolling(): void {
    // Use exponential backoff: 5s → 10s → 20s → max 60s
    const poll = () => {
      this.checkForUpdates()
      this.pollingDelay = Math.min(this.pollingDelay * 1.5, 60000)
    }

    this.pollingInterval = setInterval(poll, this.pollingDelay)
    logDebug('Polling started', { initialDelay: this.pollingDelay })
  }

  /**
   * Check for updates from other tabs (polling fallback)
   */
  private async checkForUpdates(): Promise<void> {
    try {
      const events = this.retrieveEventsFromStorage()
      const newEvents = events.filter((e) => e.payload.timestamp > this.lastPollTimestamp)

      if (newEvents.length > 0) {
        logDebug('Found new events via polling', { count: newEvents.length })
        newEvents.forEach((event) => this.handleSyncEvent(event))
        this.lastPollTimestamp = Date.now()

        // Reset polling delay on activity
        this.pollingDelay = 5000
      }
    } catch (error) {
      logError('Error during polling:', error)
    }
  }

  /**
   * Store event in localStorage for polling fallback
   */
  private storeEventForPolling(event: SyncEvent): void {
    if (typeof window === 'undefined' || !window.localStorage) return

    try {
      const key = 'saptiva-sync-events'
      const stored = localStorage.getItem(key)
      const events: SyncEvent[] = stored ? JSON.parse(stored) : []

      // Keep only last 50 events (prevent storage bloat)
      const updated = [...events, event].slice(-50)
      localStorage.setItem(key, JSON.stringify(updated))

      logDebug('Stored event for polling', { type: event.type, totalEvents: updated.length })
    } catch (error) {
      logError('Failed to store event for polling:', error)
    }
  }

  /**
   * Retrieve events from localStorage (polling fallback)
   */
  private retrieveEventsFromStorage(): SyncEvent[] {
    if (typeof window === 'undefined' || !window.localStorage) return []

    try {
      const key = 'saptiva-sync-events'
      const stored = localStorage.getItem(key)
      return stored ? JSON.parse(stored) : []
    } catch (error) {
      logError('Failed to retrieve events from storage:', error)
      return []
    }
  }

  /**
   * Get sync status
   */
  getStatus(): { supported: boolean; method: 'broadcast' | 'polling'; tabId: string } {
    return {
      supported: this.isSupported,
      method: this.isSupported ? 'broadcast' : 'polling',
      tabId: TAB_ID,
    }
  }
}

// Singleton instance
let syncInstance: CrossTabSync | null = null

/**
 * Get or create sync instance
 */
export function getSyncInstance(): CrossTabSync {
  if (!syncInstance) {
    syncInstance = new CrossTabSync()
  }
  return syncInstance
}

/**
 * Cleanup sync instance (useful for testing/cleanup)
 */
export function cleanupSyncInstance(): void {
  if (syncInstance) {
    syncInstance.cleanup()
    syncInstance = null
  }
}