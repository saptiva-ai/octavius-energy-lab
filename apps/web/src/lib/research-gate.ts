import { classifyIntent, IntentLabel } from './intent'
import type { ToolId } from '@/types/tools'

interface GateDependencies {
  deepResearchOn: boolean
  openWizard: (userText: string) => void
  startResearch: (userText: string, scope?: Record<string, any>) => Promise<void>
  showNudge: (message: string) => void
  routeToChat: (userText: string) => Promise<void> | void
  askSplitTopics?: (userText: string) => void
  onSuggestTool?: (tool: ToolId) => void
}

export type ResearchGateOutcome =
  | { path: 'nudge'; intent: IntentLabel }
  | { path: 'wizard'; intent: IntentLabel }
  | { path: 'research'; intent: IntentLabel }
  | { path: 'chat'; intent: IntentLabel }
  | { path: 'split-topics'; intent: IntentLabel }

const NUDGE_NEEDS_CONTEXT =
  '¿Qué te gustaría investigar? Especifica tema, alcance y periodo. Ej.: “Tendencia crédito PyME en MX 2023–2025”.'

const NUDGE_ENABLE_RESEARCH = 'Activa Deep Research para investigar esta consulta con trazabilidad completa.'

/**
 * Unified intent gate that decides whether to run deep research, open the scope wizard or
 * fallback to regular chat based on the user text and whether the Deep Research mode is enabled.
 */
export async function researchGate(text: string, deps: GateDependencies): Promise<ResearchGateOutcome> {
  // CLIENT-SIDE GUARD: Check if Deep Research is enabled
  // This is a UX guard - the real enforcement is server-side
  const deepResearchServerEnabled = process.env.DEEP_RESEARCH_ENABLED !== 'false';

  const trimmed = text.trim()
  if (!trimmed) {
    return { path: 'nudge', intent: IntentLabel.GREETING }
  }

  const classification = await classifyIntent(trimmed)
  const intent = classification.intent

  if (!deepResearchServerEnabled) {
    // Force chat mode when Deep Research is disabled
    await deps.routeToChat(trimmed)
    return { path: 'chat', intent }
  }

  if (intent === IntentLabel.GREETING) {
    if (deps.deepResearchOn) {
      deps.showNudge(NUDGE_NEEDS_CONTEXT)
      return { path: 'nudge', intent }
    }

    await deps.routeToChat(trimmed)
    return { path: 'chat', intent }
  }

  if (intent === IntentLabel.CHIT_CHAT) {
    await deps.routeToChat(trimmed)
    return { path: 'chat', intent }
  }

  if (intent === IntentLabel.AMBIGUOUS) {
    if (deps.deepResearchOn) {
      deps.openWizard(trimmed)
      return { path: 'wizard', intent }
    }
    await deps.routeToChat(trimmed)
    return { path: 'chat', intent }
  }

  if (intent === IntentLabel.RESEARCHABLE) {
    if (deps.deepResearchOn) {
      await deps.startResearch(trimmed)
      return { path: 'research', intent }
    }
    // Si Deep Research está desactivado, ir directo al chat sin mostrar nudge
    await deps.routeToChat(trimmed)
    return { path: 'chat', intent }
  }

  if (intent === IntentLabel.MULTI_TOPIC && deps.askSplitTopics) {
    deps.askSplitTopics(trimmed)
    return { path: 'split-topics', intent }
  }

  await deps.routeToChat(trimmed)
  return { path: 'chat', intent }
}
