/**
 * Structured UX logger for chat state auditing
 * Temporary instrumentation to trace state flow and identify race conditions
 */

type LogLevel = 'STATE' | 'EFFECT' | 'RENDER' | 'ACTION' | 'STREAM' | 'ERROR'

interface LogEntry {
  level: LogLevel
  tag: string
  data?: Record<string, any>
  timestamp: number
}

const logs: LogEntry[] = []
const MAX_LOGS = 100

export function logUX(level: LogLevel, tag: string, data?: Record<string, any>) {
  const entry: LogEntry = {
    level,
    tag,
    data,
    timestamp: Date.now(),
  }

  logs.push(entry)
  if (logs.length > MAX_LOGS) logs.shift()

  const color = {
    STATE: '#2196F3',    // blue
    EFFECT: '#9C27B0',   // purple
    RENDER: '#4CAF50',   // green
    ACTION: '#FF9800',   // orange
    STREAM: '#00BCD4',   // cyan
    ERROR: '#F44336',    // red
  }[level]

  // eslint-disable-next-line no-console
  console.log(
    `%c[${level}] ${tag}`,
    `color: ${color}; font-weight: bold`,
    data || ''
  )
}

export function logState(tag: string, state: {
  currentChatId: string | null
  messagesLength: number
  isDraftMode: boolean
  submitIntent?: boolean
  showHero?: boolean
}) {
  logUX('STATE', tag, {
    chatId: state.currentChatId,
    msgs: state.messagesLength,
    draft: state.isDraftMode,
    submitIntent: state.submitIntent,
    showHero: state.showHero,
  })
}

export function logEffect(tag: string, deps: Record<string, any>) {
  logUX('EFFECT', tag, deps)
}

export function logRender(component: string, props: Record<string, any>) {
  logUX('RENDER', component, props)
}

export function logAction(action: string, payload?: Record<string, any>) {
  logUX('ACTION', action, payload)
}

export function logStream(event: string, data?: Record<string, any>) {
  logUX('STREAM', event, data)
}

export function logError(error: string, details?: Record<string, any>) {
  logUX('ERROR', error, details)
}

// Get logs for debugging
export function getLogs(level?: LogLevel) {
  return level ? logs.filter(l => l.level === level) : logs
}

export function clearLogs() {
  logs.length = 0
}

// Pretty print trace for a scenario
export function printTrace(scenario: string) {
  // eslint-disable-next-line no-console
  console.group(`📊 Trace: ${scenario}`)
  logs.forEach(log => {
    const elapsed = log.timestamp - logs[0].timestamp
    // eslint-disable-next-line no-console
    console.log(`[+${elapsed}ms] [${log.level}] ${log.tag}`, log.data || '')
  })
  // eslint-disable-next-line no-console
  console.groupEnd()
}
