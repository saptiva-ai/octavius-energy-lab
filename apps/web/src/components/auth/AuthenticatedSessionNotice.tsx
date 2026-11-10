'use client'

import { useMemo } from 'react'
import { useRouter } from 'next/navigation'

import { Button } from '../ui'
import { useAuthStore } from '../../lib/auth-store'

interface AuthenticatedSessionNoticeProps {
  context: 'login' | 'register'
}

export function AuthenticatedSessionNotice({ context }: AuthenticatedSessionNoticeProps) {
  const router = useRouter()
  const { user, logout } = useAuthStore((state) => ({
    user: state.user,
    logout: state.logout,
  }))

  const subtitle = useMemo(() => {
    if (context === 'register') {
      return 'Para crear una cuenta diferente necesitas cerrar la sesión actual.'
    }
    return 'Ya tienes una sesión activa en la plataforma.'
  }, [context])

  const description = useMemo(() => {
    if (context === 'register') {
      return 'Cierra tu sesión si deseas crear un usuario nuevo o continúa directamente al área de chat.'
    }
    return 'Puedes continuar al chat o cerrar tu sesión para acceder con otra cuenta.'
  }, [context])

  const handleGoToChat = () => {
    router.push('/chat')
  }

  const handleLogout = async () => {
    await logout({ reason: 'switch-account' })
  }

  return (
    <div className="w-full max-w-[420px] rounded-2xl border border-border bg-surface px-8 py-10 text-center shadow-card">
      <h1 className="text-2xl font-semibold text-text">Sesión ya iniciada</h1>
      <p className="mt-3 text-sm text-text-muted">{subtitle}</p>
      {user?.email || user?.username ? (
        <p className="mt-4 text-sm text-text">Actualmente estás autenticado como <span className="font-semibold">{user.email ?? user.username}</span>.</p>
      ) : null}
      <p className="mt-4 text-sm text-text-muted">{description}</p>
      <div className="mt-8 flex flex-col gap-3">
        <Button onClick={handleGoToChat} className="w-full rounded-xl bg-[#49F7D9] text-base font-semibold text-white transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#49F7D9]/60 focus-visible:ring-offset-2 focus-visible:ring-offset-[#0B1217]">
          Ir al chat
        </Button>
        <Button
          onClick={handleLogout}
          variant="secondary"
          className="w-full rounded-xl border border-border bg-transparent text-base font-semibold text-text transition-opacity hover:opacity-70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
        >
          Cerrar sesión
        </Button>
      </div>
    </div>
  )
}
