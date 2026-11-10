/**
 * Tests for intent classification utilities.
 */

import { classifyIntent, IntentLabel } from '../intent'

describe('Intent Classification', () => {
  describe('Greeting Detection', () => {
    it('should classify basic greetings correctly', async () => {
      const greetings = [
        'hola',
        'hello',
        'buenos días',
        'good morning',
        'hi there',
        '¿cómo estás?',
        'how are you?',
      ]

      for (const greeting of greetings) {
        const result = await classifyIntent(greeting)
        expect(result.intent).toBe(IntentLabel.GREETING)
        expect(result.confidence).toBeGreaterThanOrEqual(0.8)
        expect(result.reasons).toContain('Coincide con saludo')
      }
    })

    it('should handle case variations in greetings', async () => {
      const variations = ['HOLA', 'HeLLo', 'buenos DÍAS']

      for (const variation of variations) {
        const result = await classifyIntent(variation)
        expect(result.intent).toBe(IntentLabel.GREETING)
      }
    })
  })

  describe('Researchable Query Detection', () => {
    it('should classify research queries correctly', async () => {
      const researchQueries = [
        '¿Cuál es el impacto de la IA en LATAM 2024?',
        'Analiza las tendencias de fintech en México',
        'What are the effects of climate change?',
        'Investigación sobre energías renovables 2023',
        'Análisis del mercado crypto en Argentina',
      ]

      for (const query of researchQueries) {
        const result = await classifyIntent(query)
        expect(result.intent).toBe(IntentLabel.RESEARCHABLE)
        expect(result.confidence).toBeGreaterThanOrEqual(0.8)
        expect(result.reasons.length).toBeGreaterThan(0)
      }
    })

    it('should detect research context indicators', async () => {
      const contextIndicators = [
        'análisis de tendencias blockchain 2024',
        'estudio comparativo de fintech',
        'investigación sobre impacto económico',
        'data sobre adopción de cripto en LATAM',
      ]

      for (const query of contextIndicators) {
        const result = await classifyIntent(query)
        expect(result.intent).toBe(IntentLabel.RESEARCHABLE)
        expect(result.reasons).toEqual(
          expect.arrayContaining([
            expect.stringMatching(/contexto|investigación|palabras clave/i)
          ])
        )
      }
    })

    it('should detect question patterns', async () => {
      const questions = [
        '¿Qué impacto tiene la IA?',
        '¿Cómo afecta el blockchain?',
        '¿Cuáles son las tendencias?',
        'What is the impact of AI?',
        'How does fintech affect banking?',
      ]

      for (const question of questions) {
        const result = await classifyIntent(question)
        expect(result.intent).toBe(IntentLabel.RESEARCHABLE)
        expect(result.reasons).toEqual(
          expect.arrayContaining([
            expect.stringMatching(/pregunta detectada/i)
          ])
        )
      }
    })
  })

  describe('Command Detection', () => {
    it('should classify commands correctly', async () => {
      const commands = [
        'resume el documento anterior',
        'traduce esto al inglés',
        'explica la función',
        'crea una lista',
        'genera un reporte',
      ]

      for (const command of commands) {
        const result = await classifyIntent(command)
        expect(result.intent).toBe(IntentLabel.COMMAND)
        expect(result.confidence).toBeGreaterThanOrEqual(0.7)
      }
    })

    it('should detect imperative verbs', async () => {
      const imperatives = [
        'analiza estos datos',
        'compara las opciones',
        'calcula el promedio',
        'busca información sobre',
      ]

      for (const imperative of imperatives) {
        const result = await classifyIntent(imperative)
        expect(result.intent).toBe(IntentLabel.COMMAND)
        expect(result.reasons).toEqual(
          expect.arrayContaining([
            expect.stringMatching(/verbo imperativo/i)
          ])
        )
      }
    })
  })

  describe('Multi-topic Detection', () => {
    it('should detect multiple topics in single query', async () => {
      const multiTopicQueries = [
        'Hola, ¿puedes investigar el impacto de la IA y también explicar blockchain?',
        '¿Qué opinas de crypto y además analiza el mercado fintech?',
        'Analiza tanto el impacto económico como el social de la tecnología',
      ]

      for (const query of multiTopicQueries) {
        const result = await classifyIntent(query)
        expect(result.intent).toBe(IntentLabel.MULTI_TOPIC)
        expect(result.confidence).toBeGreaterThanOrEqual(0.7)
      }
    })

    it('should detect coordination patterns', async () => {
      const coordinatedQueries = [
        'Investigar A y también B',
        'Analizar X además de Y',
        'Tanto A como B necesitan análisis',
      ]

      for (const query of coordinatedQueries) {
        const result = await classifyIntent(query)
        expect(result.intent).toBe(IntentLabel.MULTI_TOPIC)
        expect(result.reasons).toEqual(
          expect.arrayContaining([
            expect.stringMatching(/coordinación|múltiples/i)
          ])
        )
      }
    })
  })

  describe('Edge Cases', () => {
    it('should handle empty or whitespace input', async () => {
      const emptyInputs = ['', '   ', '\n\t\n', '  \t  ']

      for (const input of emptyInputs) {
        await expect(classifyIntent(input)).rejects.toThrow('Text cannot be empty')
      }
    })

    it('should handle very short input', async () => {
      const shortInputs = ['a', 'ok', 'sí', 'no']

      for (const input of shortInputs) {
        const result = await classifyIntent(input)
        expect(result.intent).toBe(IntentLabel.CHIT_CHAT)
        expect(result.confidence).toBeLessThan(0.8)
      }
    })

    it('should handle very long input', async () => {
      const longInput = 'Analiza el impacto de la inteligencia artificial '.repeat(20)

      const result = await classifyIntent(longInput)
      expect(result.intent).toBe(IntentLabel.RESEARCHABLE)
      expect(result.confidence).toBeGreaterThan(0.8)
    })

    it('should handle mixed languages', async () => {
      const mixedLanguageInputs = [
        'Hello, ¿puedes investigar AI trends?',
        'Hola, can you analyze blockchain impact?',
        'Bonjour, analiza el mercado fintech por favor',
      ]

      for (const input of mixedLanguageInputs) {
        const result = await classifyIntent(input)
        expect(result.intent).toBe(IntentLabel.MULTI_TOPIC)
        expect(result.confidence).toBeGreaterThan(0.6)
      }
    })

    it('should classify ambiguous text correctly', async () => {
      const ambiguousInputs = [
        'esto es algo raro',
        'no sé qué pensar',
        'maybe something different',
        'podría ser cualquier cosa',
      ]

      for (const input of ambiguousInputs) {
        const result = await classifyIntent(input)
        expect(result.intent).toBe(IntentLabel.AMBIGUOUS)
        expect(result.confidence).toBeLessThan(0.7)
      }
    })
  })

  describe('Performance', () => {
    it('should classify intent quickly', async () => {
      const query = '¿Cuál es el impacto de la IA en LATAM 2024?'

      const startTime = performance.now()
      await classifyIntent(query)
      const endTime = performance.now()

      const duration = endTime - startTime
      expect(duration).toBeLessThan(50) // Less than 50ms
    })

    it('should handle concurrent classifications', async () => {
      const queries = [
        'hola',
        '¿Qué impacto tiene la IA?',
        'analiza estos datos',
        'tengo hambre',
        'investigar blockchain y fintech',
      ]

      const promises = queries.map(query => classifyIntent(query))
      const results = await Promise.all(promises)

      expect(results).toHaveLength(5)
      results.forEach(result => {
        expect(result.intent).toBeDefined()
        expect(result.confidence).toBeGreaterThan(0)
        expect(result.model).toBe('heuristic')
      })
    })
  })
})