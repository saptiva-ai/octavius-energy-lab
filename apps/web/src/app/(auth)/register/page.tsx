'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'

/**
 * Registration is disabled - users must contact an administrator.
 * This page redirects to login after showing a brief message.
 */
export default function RegisterPage() {
  const router = useRouter()

  useEffect(() => {
    // Auto-redirect to login after 3 seconds
    const timer = setTimeout(() => {
      router.replace('/login')
    }, 3000)

    return () => clearTimeout(timer)
  }, [router])

  return (
    <div className="w-full max-w-[420px] rounded-2xl border border-border bg-surface px-8 py-10 shadow-card">
      <div className="mb-6 text-center">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
          <svg
            className="h-6 w-6 text-primary"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
            />
          </svg>
        </div>
        <h1 className="text-2xl font-semibold text-foreground">
          Registro no disponible
        </h1>
      </div>

      <div className="mb-6 rounded-xl border border-primary/30 bg-primary/5 px-4 py-4 text-center">
        <p className="text-sm text-foreground">
          El registro de nuevas cuentas está restringido.
        </p>
        <p className="mt-2 text-sm text-text-muted">
          Para solicitar acceso, contacta a un administrador:
        </p>
        <a
          href="mailto:support@saptiva.com?subject=Solicitud%20de%20cuenta%20OctaviOS"
          className="mt-2 inline-block text-sm font-medium text-link transition-opacity hover:opacity-80"
        >
          support@saptiva.com
        </a>
      </div>

      <p className="text-center text-sm text-text-muted">
        Redirigiendo a inicio de sesión...
      </p>

      <div className="mt-6 text-center">
        <Link
          href="/login"
          className="inline-flex items-center justify-center rounded-xl bg-primary px-6 py-2.5 text-sm font-semibold text-primary-foreground transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
        >
          Ir a iniciar sesión
        </Link>
      </div>
    </div>
  )
}
