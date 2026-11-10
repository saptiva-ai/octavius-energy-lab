export enum IntentLabel {
  GREETING = 'GREETING',
  CHIT_CHAT = 'CHIT_CHAT',
  COMMAND = 'COMMAND',
  RESEARCHABLE = 'RESEARCHABLE',
  AMBIGUOUS = 'AMBIGUOUS',
  MULTI_TOPIC = 'MULTI_TOPIC',
}

export type Intent = IntentLabel

export interface IntentClassification {
  intent: IntentLabel
  confidence: number
  reasons: string[]
  model: 'heuristic'
}

interface HeuristicSignal {
  label: IntentLabel
  confidence: number
  reason: string
}

const RE_QUESTION = /(?:(?:¿|\?)|\b(qué|como|cómo|por qué|por que|cuando|cuándo|donde|dónde|cuál|cual|what|how|why|where|which)\b)/i
const RE_GREETING_PREFIX = /^\s*[¿¡]?(hola|buen[oa]s|buenos días|buenas tardes|hey|qué tal|hi|hello|good\s+(?:morning|afternoon|evening)|how are you|c[óo]mo estás)([,!\?\s]|$)/i
const RE_IMPERATIVE = /(configura|establece|crea|actualiza|ejecuta|borra|elimina|analiza|calcula|busca|explica|resume|genera|traduce|compara|investiga|investigar|analizar)/i
const RE_MULTI_TOPIC = /(\b(?:y\s+(?:también|además|otro)|además de|tanto\s+(?:[^\s]+\s+){0,5}como|both\s+[^\s]+\s+and|as well as)\b)/i
const RE_AMBIGUOUS = /(no sé|podría|maybe|quizás|quizá|diferente|cualquier cosa|not sure|could be)/i

const CONTEXT_PATTERNS = [
  /\b20\d{2}\b/gi,
  /\b(latam|méxico|mx|europa|ee\.uu\.?|usa|apac|emea|argentina|colombia|perú|peru)\b/gi,
  /https?:\/\//gi,
  /\b(impacto|comparativa|tendencia|riesgo|mercado|benchmark|pronóstico|forecast|estudio|análisis|analysis|research|investigación)\b/gi,
  /\b(blockchain|crypto|fintech|ia|inteligencia artificial|ai)\b/gi,
]

const LABEL_PRIORITY: IntentLabel[] = [
  IntentLabel.RESEARCHABLE,
  IntentLabel.MULTI_TOPIC,
  IntentLabel.COMMAND,
  IntentLabel.GREETING,
  IntentLabel.AMBIGUOUS,
  IntentLabel.CHIT_CHAT,
]

function countConstraintMatches(text: string): number {
  return CONTEXT_PATTERNS.reduce((acc, re) => acc + ((text.match(re) || []).length), 0)
}

function detectGreeting(text: string): { isGreeting: boolean; remainderWords: number } {
  const match = text.match(RE_GREETING_PREFIX)
  if (!match) {
    return { isGreeting: false, remainderWords: text.trim() ? text.trim().split(/\s+/).length : 0 }
  }

  const remainder = text.slice(match[0].length).trim()
  const remainderWords = remainder ? remainder.split(/\s+/).length : 0
  const isGreeting = remainder.length === 0 || remainderWords <= 4
  return { isGreeting, remainderWords }
}

function buildClassification(text: string): IntentClassification {
  const normalized = text.trim()
  const lower = normalized.toLowerCase()
  const wordCount = normalized ? normalized.split(/\s+/).length : 0

  const signals: HeuristicSignal[] = []
  const reasons = new Set<string>()

  const greetingDetection = detectGreeting(normalized)
  const isGreeting = greetingDetection.isGreeting
  const greetingRemainderWords = greetingDetection.remainderWords
  if (isGreeting) {
    signals.push({ label: IntentLabel.GREETING, confidence: 0.9, reason: 'Coincide con saludo' })
    reasons.add('Coincide con saludo')
  }

  const hasMultiTopicConnector = RE_MULTI_TOPIC.test(normalized)
  let hasCompositeGreetingTopic = false
  const greetingWordPresent = /(hola|hello|hi|bonjour|salut|good\s+(?:morning|afternoon|evening)|c[óo]mo estás|how are you)/i.test(normalized)

  const constraintMatches = countConstraintMatches(normalized)

  const hasMultiTopic = (() => {
    if (hasMultiTopicConnector) {
      return true
    }

    if (greetingWordPresent) {
      const hasRequest = (greetingRemainderWords > 2) && (RE_IMPERATIVE.test(lower) || RE_QUESTION.test(normalized) || constraintMatches > 0)
      if (hasRequest) {
        hasCompositeGreetingTopic = true
        return true
      }
    }
    return false
  })()
  if (hasMultiTopic) {
    const reason = hasCompositeGreetingTopic
      ? 'Múltiples elementos detectados (saludo + solicitud)'
      : 'Coordinación de múltiples temas detectada'
    signals.push({ label: IntentLabel.MULTI_TOPIC, confidence: 0.9, reason })
    reasons.add(reason)
  }

  const hasImperative = RE_IMPERATIVE.test(lower)
  if (hasImperative) {
    const reason = 'Verbo imperativo detectado'
    signals.push({ label: IntentLabel.COMMAND, confidence: 0.75, reason })
    reasons.add(reason)
  }

  const isQuestion = RE_QUESTION.test(normalized)
  if (isQuestion) {
    reasons.add('Pregunta detectada')
  }

  // constraintMatches computed above
  if (constraintMatches > 0) {
    const contextReason = constraintMatches > 1
      ? `Coincidencias de contexto detectadas (${constraintMatches})`
      : 'Contexto investigable detectado'
    reasons.add(contextReason)
  }

  let researchConfidence = 0
  const researchReasons: string[] = []

  if (isQuestion) {
    researchConfidence = 0.82
    researchReasons.push('Pregunta detectada')
  }

  if (constraintMatches > 0) {
    const contextReason = constraintMatches > 1
      ? `Coincidencias de contexto detectadas (${constraintMatches})`
      : 'Contexto investigable detectado'
    researchReasons.push(contextReason)
    researchConfidence = Math.max(researchConfidence, constraintMatches > 1 ? 0.9 : 0.86)
  }

  if (hasMultiTopic && researchConfidence >= 0.8) {
    researchConfidence = 0.8
  }

  if (researchConfidence > 0) {
    researchReasons.forEach((reason) => reasons.add(reason))
    const mergedReason = researchReasons.join(' + ')
    signals.push({ label: IntentLabel.RESEARCHABLE, confidence: researchConfidence, reason: mergedReason || 'Pregunta investigable' })
  }

  if (RE_AMBIGUOUS.test(lower)) {
    const reason = 'Expresión ambigua detectada'
    signals.push({ label: IntentLabel.AMBIGUOUS, confidence: 0.58, reason })
    reasons.add(reason)
  }

  if (!isGreeting && !hasImperative && !isQuestion && constraintMatches === 0 && !hasMultiTopic) {
    const reason = wordCount <= 3 ? 'Mensaje breve sin contexto' : 'Sin clasificación clara'
    const label = wordCount <= 3 ? IntentLabel.CHIT_CHAT : IntentLabel.AMBIGUOUS
    const confidence = wordCount <= 3 ? 0.42 : 0.57
    signals.push({ label, confidence, reason })
    reasons.add(reason)
  }

  if (signals.length === 0) {
    signals.push({ label: IntentLabel.AMBIGUOUS, confidence: 0.55, reason: 'Sin heurística definida' })
    reasons.add('Sin heurística definida')
  }

  let best = signals[0]
  for (const signal of signals.slice(1)) {
    if (signal.confidence > best.confidence) {
      best = signal
      continue
    }

    if (signal.confidence === best.confidence) {
      const signalPriority = LABEL_PRIORITY.indexOf(signal.label)
      const bestPriority = LABEL_PRIORITY.indexOf(best.label)
      if (signalPriority !== -1 && (bestPriority === -1 || signalPriority < bestPriority)) {
        best = signal
      }
    }
  }

  const filteredReasons = Array.from(reasons).filter((reason) => {
    switch (best.label) {
      case IntentLabel.GREETING:
        return /saludo/i.test(reason)
      case IntentLabel.COMMAND:
        return /imperativo|contexto/i.test(reason)
      case IntentLabel.MULTI_TOPIC:
        return /múltiples|coordinación/i.test(reason)
      case IntentLabel.RESEARCHABLE:
        return /contexto|investigación|pregunta/i.test(reason)
      case IntentLabel.CHIT_CHAT:
        return /saludo|pregunta corta|mensaje breve|sin contexto/i.test(reason)
      case IntentLabel.AMBIGUOUS:
      default:
        return /ambigua|contexto|sin clasificación/i.test(reason)
    }
  })

  if (filteredReasons.length === 0) {
    filteredReasons.push(best.reason)
  }

  if (best.label === IntentLabel.RESEARCHABLE && isQuestion && !filteredReasons.some((reason) => /pregunta/i.test(reason))) {
    filteredReasons.push('Pregunta detectada')
  }

  const confidence = Number(Math.min(0.99, Math.max(best.confidence, 0)).toFixed(2))

  const finalReasons = Array.from(new Set(filteredReasons))

  return {
    intent: best.label,
    confidence,
    reasons: finalReasons,
    model: 'heuristic',
  }
}

export async function classifyIntent(text: string): Promise<IntentClassification> {
  const trimmed = text.trim()
  if (!trimmed) {
    throw new Error('Text cannot be empty')
  }

  return buildClassification(trimmed)
}
