'use client'

import * as React from 'react'
import { cn } from '../../lib/utils'
import { esperaDeConsulta, type Espera, type TemaEspera } from '../../lib/espera-por-consulta'

/** Cada cuánto avanza al siguiente mensaje del paso. */
const PASO_MS = 2500

interface TypingIndicatorProps {
  className?: string
  size?: 'sm' | 'md' | 'lg'
  /** Paso del turno, tema y mensajes; sin él, "Pensando". */
  espera?: Espera
}

const PENSANDO: Espera = esperaDeConsulta(undefined)

/** Mensaje a la vista: los del paso en orden, uno cada `PASO_MS`, y se queda
 * en el último (no se sortea ni vuelve a empezar). Al cambiar de paso, vuelve
 * al primero del nuevo. Sin mensajes, la frase normal. */
function useMensajeEnOrden({ frase, frases }: Espera): string {
  const clave = frases.join('|')
  const [indice, setIndice] = React.useState(0)

  React.useEffect(() => {
    setIndice(0)
    if (frases.length < 2) return
    const intervalo = setInterval(
      () => setIndice((i) => Math.min(i + 1, frases.length - 1)),
      PASO_MS,
    )
    return () => clearInterval(intervalo)
    // `clave` resume `frases`: un arreglo nuevo con los mismos mensajes no
    // reinicia la secuencia.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clave])

  return frases.length > 0 ? frases[Math.min(indice, frases.length - 1)] : frase
}

/** Ícono animado por tema. Solo `transform` y `opacity`; con
 * `prefers-reduced-motion` todos se quedan en un pulso de opacidad (ver
 * `.indicador-espera` en globals.css). */
function IconoEspera({ tema }: { tema: TemaEspera }) {
  const comun = {
    'data-testid': 'icono-espera',
    'data-tema': tema,
    'aria-hidden': true,
  } as const

  switch (tema) {
    case 'ventas':
      return (
        <svg {...comun} className="indicador-espera espera-linea h-[18px] w-[30px]" viewBox="0 0 30 18">
          <path d="M1 16 L8 11 L14 13 L21 5 L29 2" />
        </svg>
      )
    case 'ranking':
      return (
        <span {...comun} className="indicador-espera espera-barras flex h-[18px] items-end gap-[3px]">
          {[45, 80, 60, 100].map((alto, i) => (
            <i key={i} style={{ height: `${alto}%`, '--retraso': `${i * 110}ms` } as React.CSSProperties} />
          ))}
        </span>
      )
    case 'inventario':
      return (
        <span {...comun} className="indicador-espera espera-celdas grid grid-cols-3 gap-[3px]">
          {Array.from({ length: 9 }, (_, i) => (
            <i key={i} style={{ '--retraso': `${i * 100}ms` } as React.CSSProperties} />
          ))}
        </span>
      )
    case 'riesgo':
      return (
        <span {...comun} className="indicador-espera espera-pulso relative h-[22px] w-[22px]">
          <b />
          <i />
          <i style={{ '--retraso': '800ms' } as React.CSSProperties} />
        </span>
      )
    case 'ayuda':
      return (
        <span {...comun} className="indicador-espera espera-ola flex items-center gap-[5px]">
          {[0, 1, 2].map((i) => (
            <i key={i} style={{ '--retraso': `${i * 150}ms` } as React.CSSProperties} />
          ))}
        </span>
      )
    default:
      return <span {...comun} className="indicador-espera espera-anillo h-[18px] w-[18px]" />
  }
}

/**
 * Indicador de que el asistente prepara la respuesta (Equipo, 2026-10-21): uno
 * solo, en la burbuja donde aparecerá la respuesta. Arranca con el anillo y
 * "Pensando"; cuando el backend avisa qué tool eligió (evento `status`), cambia
 * al ícono y la frase del tema: línea de tendencia para ventas, barras para
 * rankings, cuadrícula para inventario, pulso para riesgos y puntos para
 * definiciones y ayuda. A la vista avanzan en orden los mensajes del paso
 * ("Saptivating…", "Leyendo tu pregunta…"; "Revisando los productos sin
 * existencia…", "Recorriendo pasillos…"; "Redactando la respuesta…") con un
 * brillo que los recorre; a lectores de pantalla se anuncia por
 * `role="status"` la frase del paso ("Revisando inventario").
 */
export function TypingIndicator({ className, size = 'md', espera = PENSANDO }: TypingIndicatorProps) {
  const visible = useMensajeEnOrden(espera)

  return (
    <div
      className={cn('inline-flex items-center gap-3', className)}
      role="status"
      aria-live="polite"
      aria-label={espera.frase}
      data-size={size}
    >
      <span className="flex h-6 w-[30px] flex-none items-center justify-center">
        <IconoEspera tema={espera.tema} />
      </span>
      {/* Los mensajes avanzan a la vista; el lector de pantalla oye la frase
          del paso una sola vez, no cada mensaje. */}
      <span className="indicador-brillo whitespace-nowrap text-[13px]" aria-hidden="true">
        {visible}
      </span>
      <span className="sr-only">{espera.frase}</span>
    </div>
  )
}

export function StreamingCursor({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        'inline-block w-0.5 h-4 bg-primary animate-pulse ml-0.5',
        className
      )}
      style={{ animationDuration: '1s' }}
    />
  )
}
