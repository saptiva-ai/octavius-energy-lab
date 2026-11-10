import { Button } from '../ui/Button'
import { cn } from '@/lib/utils'
import type {
  ResearchEvidenceEvent,
  ResearchPhase,
  ResearchReportEvent,
  ResearchSourceEvent,
} from '@/hooks/useDeepResearch'

interface DeepResearchProgressProps {
  query: string
  phase: ResearchPhase
  progress: number
  sources: ResearchSourceEvent[]
  evidences: ResearchEvidenceEvent[]
  report: ResearchReportEvent | null
  errorMessage?: string | null
  isStreaming: boolean
  onCancel: () => void
  onClose: () => void
}

const PHASE_LABELS: Record<ResearchPhase, string> = {
  IDLE: 'Esperando',
  PLAN: 'Planificando',
  SEARCH: 'Buscando fuentes',
  EVIDENCE: 'Evaluando evidencia',
  SYNTHESIS: 'Sintetizando hallazgos',
  REVIEW: 'Revisando resultados',
  COMPLETED: 'Completado',
  FAILED: 'Fallido',
}

export function DeepResearchProgress({
  query,
  phase,
  progress,
  sources,
  evidences,
  report,
  errorMessage,
  isStreaming,
  onCancel,
  onClose,
}: DeepResearchProgressProps) {
  const roundedProgress = Number.isFinite(progress) ? Math.max(0, Math.min(100, Math.round(progress))) : 0
  const topSources = sources.slice(0, 4)
  const topEvidences = evidences.slice(0, 3)

  const isCompleted = phase === 'COMPLETED'
  const hasError = phase === 'FAILED' || Boolean(errorMessage)

  return (
    <section className="mb-4 w-full max-w-4xl rounded-2xl border border-border bg-surface-2 p-5 shadow-lg">
      <header className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.35em] text-saptiva-light/70">Deep Research</p>
          <h3 className="mt-1 text-lg font-semibold text-white">{query}</h3>
          <p className="text-sm text-saptiva-light/60">{PHASE_LABELS[phase]}</p>
        </div>
        <div className="flex items-center gap-2">
          {!isCompleted && !hasError && (
            <Button variant="ghost" size="sm" onClick={onCancel} disabled={!isStreaming}>
              Cancelar
            </Button>
          )}
          {(isCompleted || hasError) && (
            <Button variant="secondary" size="sm" onClick={onClose}>
              Cerrar panel
            </Button>
          )}
        </div>
      </header>

      <div className="mb-5">
        <div className="flex items-center justify-between text-xs text-saptiva-light/60">
          <span aria-hidden="true">{PHASE_LABELS[phase]} · progreso</span>
          <span>{roundedProgress}%</span>
        </div>
        <div className="mt-1 h-2 w-full overflow-hidden rounded-full bg-white/10">
          <div
            className={cn(
              'h-full rounded-full transition-all duration-300',
              hasError ? 'bg-danger/80' : 'bg-primary',
            )}
            role="progressbar"
            aria-valuenow={roundedProgress}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={`Progreso: ${PHASE_LABELS[phase]}`}
            style={{ width: `${roundedProgress}%` }}
          />
        </div>
      </div>

      {hasError && (
        <div className="mb-4 rounded-xl border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger/90">
          {errorMessage ?? 'No se pudo completar la investigación. Intenta ajustar el alcance o vuelve a intentarlo.'}
        </div>
      )}

      {!hasError && (
        <div className="grid gap-4 lg:grid-cols-2">
          <div>
            <h4 className="mb-2 text-sm font-semibold text-white/90">Fuentes recientes</h4>
            <div className="space-y-2 text-sm">
              {topSources.length === 0 && (
                <p className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-saptiva-light/60">
                  Aún no se han agregado fuentes.
                </p>
              )}
              {topSources.map((source) => (
                <article
                  key={source.id ?? source.url ?? `${source.title}-${source.snippet}`}
                  className="rounded-lg border border-white/10 bg-white/5 px-3 py-2"
                >
                  <p className="font-medium text-white line-clamp-2">{source.title ?? source.url ?? 'Fuente sin título'}</p>
                  {source.url && (
                    <a
                      href={source.url}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-1 inline-flex text-xs text-primary hover:underline"
                    >
                      {source.url.replace(/^https?:\/\//, '')}
                    </a>
                  )}
                </article>
              ))}
            </div>
          </div>

          <div>
            <h4 className="mb-2 text-sm font-semibold text-white/90">Evidencias destacadas</h4>
            <div className="space-y-2 text-sm">
              {topEvidences.length === 0 && (
                <p className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-saptiva-light/60">
                  Se están evaluando hallazgos relevantes.
                </p>
              )}
              {topEvidences.map((evidence) => (
                <article
                  key={evidence.id ?? evidence.claim ?? `${evidence.support_level}-${evidence.confidence}`}
                  className="rounded-lg border border-white/10 bg-white/5 px-3 py-2"
                >
                  <p className="text-white line-clamp-3">{evidence.claim ?? 'Hallazgo sin descripción'}</p>
                  {evidence.support_level && (
                    <span className="mt-1 inline-flex rounded-full bg-white/10 px-2 py-[2px] text-xs text-saptiva-light/80">
                      Confianza: {evidence.support_level}
                    </span>
                  )}
                </article>
              ))}
            </div>
          </div>
        </div>
      )}

      {report && !hasError && (
        <div className="mt-5 rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-saptiva-light">
          <h5 className="text-sm font-semibold text-white">TL;DR</h5>
          <p className="mt-1 text-saptiva-light/80">{report.tl_dr ?? report.summary ?? 'Resumen disponible al finalizar.'}</p>
        </div>
      )}
    </section>
  )
}
