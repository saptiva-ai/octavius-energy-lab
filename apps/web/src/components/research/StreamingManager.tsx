'use client'

import { useEffect } from 'react'
import { useStreaming, calculateProgress } from '../../lib/streaming'
import { logError } from '../../lib/logger'

interface StreamingManagerProps {
  currentTaskId: string | null
  setTasks: React.Dispatch<React.SetStateAction<any[]>>
}

export function StreamingManager({ currentTaskId, setTasks }: StreamingManagerProps) {
  const { connect, disconnect, isConnected } = useStreaming(
    currentTaskId ? `/api/stream/${currentTaskId}` : null,
    {
      onMessage: (event) => {
        setTasks(prev => prev.map(task => 
          task.id === event.task_id
            ? {
                ...task,
                progress: calculateProgress(event),
                status: event.event_type === 'task_completed' ? 'completed' as const :
                       event.event_type === 'task_failed' ? 'failed' as const :
                       'running' as const,
                result: event.data.result || task.result
              }
            : task
        ))
      },
      onError: (error) => {
        logError('Streaming error:', error)
      }
    }
  )

  useEffect(() => {
    if (currentTaskId) {
      connect()
    } else {
      disconnect()
    }

    return () => {
      disconnect()
    }
  }, [currentTaskId, connect, disconnect])

  return null
}
