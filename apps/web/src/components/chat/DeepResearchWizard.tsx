import { useState } from 'react'
import { Button } from '../ui/Button'
import { Input } from '../ui/Input'
import { Textarea } from '../ui/Textarea'
import { cn } from '@/lib/utils'

export type ResearchDepth = 'shallow' | 'medium' | 'deep'

export interface DeepResearchScope {
  objective: string
  timeWindow: string
  depth: ResearchDepth
}

interface DeepResearchWizardProps {
  query: string
  onConfirm: (scope: DeepResearchScope) => void
  onCancel: () => void
  loading?: boolean
  className?: string
}

const DEPTH_OPTIONS: Array<{ value: ResearchDepth; label: string; description: string }> = [
  { value: 'shallow', label: 'Panorama rápido', description: 'Resumen de alto nivel' },
  { value: 'medium', label: 'Balanceado', description: 'Profundidad equilibrada' },
  { value: 'deep', label: 'Exhaustivo', description: 'Investigación detallada' },
]

const TIME_WINDOWS = [
  { value: 'last_6_months', label: 'Últimos 6 meses' },
  { value: 'last_12_months', label: 'Últimos 12 meses' },
  { value: 'custom', label: 'Rango personalizado' },
]

export function DeepResearchWizard({
  query,
  onConfirm,
  onCancel,
  loading = false,
  className,
}: DeepResearchWizardProps) {
  const [objective, setObjective] = useState(query)
  const [timeWindow, setTimeWindow] = useState<string>('last_12_months')
  const [customRange, setCustomRange] = useState<string>('2023-01..2025-12')
  const [depth, setDepth] = useState<ResearchDepth>('medium')

  const effectiveTimeWindow = timeWindow === 'custom' ? customRange : timeWindow

  const handleConfirm = () => {
    if (!objective.trim()) {
      return
    }

    onConfirm({
      objective: objective.trim(),
      timeWindow: effectiveTimeWindow,
      depth,
    })
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Configurar investigación profunda"
      className={cn(
        'w-full max-w-xl rounded-2xl border border-border bg-surface-2 p-6 shadow-xl backdrop-blur',
        className,
      )}
    >
      <header className="mb-4">
        <p className="text-xs font-semibold uppercase tracking-[0.35em] text-saptiva-light/70">
          Deep Research
        </p>
        <h2 className="mt-2 text-xl font-semibold text-white">Define el alcance de la investigación</h2>
        <p className="mt-1 text-sm text-saptiva-light/70">
          Ajusta el objetivo, periodo y profundidad antes de iniciar la búsqueda automatizada.
        </p>
      </header>

      <div className="space-y-5">
        <Textarea
          label="Objetivo principal"
          value={objective}
          onChange={(event) => setObjective(event.target.value)}
          disabled={loading}
          placeholder="Ej. Impacto de la IA generativa en el sector bancario de LATAM"
          rows={3}
          autoResize
        />

        <div>
          <label className="text-sm font-medium text-saptiva-light/80">Periodo de interés</label>
          <div className="mt-2 grid gap-2 sm:grid-cols-3">
            {TIME_WINDOWS.map((option) => (
              <button
                key={option.value}
                type="button"
                disabled={loading}
                onClick={() => setTimeWindow(option.value)}
                className={cn(
                  'rounded-xl border border-border bg-surface px-3 py-2 text-sm text-saptiva-light transition-colors hover:border-primary/40 hover:bg-surface-2',
                  timeWindow === option.value && 'border-primary/40 bg-primary/10 text-primary',
                )}
              >
                {option.label}
              </button>
            ))}
          </div>
          {timeWindow === 'custom' && (
            <Input
              className="mt-3"
              label="Rango personalizado"
              placeholder="YYYY-MM..YYYY-MM"
              value={customRange}
              onChange={(event) => setCustomRange(event.target.value)}
              disabled={loading}
            />
          )}
        </div>

        <div>
          <label className="text-sm font-medium text-saptiva-light/80">Profundidad deseada</label>
          <div className="mt-2 grid gap-2 sm:grid-cols-3">
            {DEPTH_OPTIONS.map((option) => (
              <button
                key={option.value}
                type="button"
                disabled={loading}
                onClick={() => setDepth(option.value)}
                className={cn(
                  'rounded-xl border border-border bg-surface px-3 py-3 text-left transition-colors hover:border-primary/40 hover:bg-surface-2',
                  depth === option.value && 'border-primary/40 bg-primary/10 text-primary',
                )}
              >
                <div className="text-sm font-medium text-white">{option.label}</div>
                <div className="mt-1 text-xs text-saptiva-light/70">{option.description}</div>
              </button>
            ))}
          </div>
        </div>
      </div>

      <footer className="mt-6 flex items-center justify-end gap-3">
        <Button
          type="button"
          variant="secondary"
          onClick={onCancel}
          disabled={loading}
        >
          Cancelar
        </Button>
        <Button type="button" onClick={handleConfirm} disabled={loading || !objective.trim()}>
          {loading ? 'Iniciando…' : 'Iniciar investigación'}
        </Button>
      </footer>
    </div>
  )
}
