'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'

import { Input, Button } from '../ui'
import { useAuthStore } from '../../lib/auth-store'

type RegisterFieldErrors = {
  username?: string
  email?: string
  password?: string
  confirmPassword?: string
}

export function RegisterForm() {
  const router = useRouter()
  const [form, setForm] = useState({
    username: '',
    email: '',
    password: '',
    confirmPassword: '',
  })
  const [fieldErrors, setFieldErrors] = useState<RegisterFieldErrors>({})
  const [generalError, setGeneralError] = useState<string | null>(null)

  const { status, error, clearError, register, isHydrated, accessToken, user } = useAuthStore((state) => ({
    status: state.status,
    error: state.error,
    clearError: state.clearError,
    register: state.register,
    isHydrated: state.isHydrated,
    accessToken: state.accessToken,
    user: state.user,
  }))

  useEffect(() => {
    if (!error) {
      setGeneralError(null)
      return
    }

    if (error.field === 'email') {
      setFieldErrors((prev) => ({ ...prev, email: error.message }))
      setGeneralError(null)
      return
    }

    if (error.field === 'username') {
      setFieldErrors((prev) => ({ ...prev, username: error.message }))
      setGeneralError(null)
      return
    }

    if (error.field === 'password') {
      setFieldErrors((prev) => ({ ...prev, password: error.message }))
      setGeneralError(null)
      return
    }

    setGeneralError(error.message)
  }, [error])

  const isAuthenticated = isHydrated && Boolean(accessToken && user)

  // P0-FIX: Silent redirect instead of showing "already logged in" notice
  useEffect(() => {
    if (isAuthenticated) {
      router.replace('/chat')
    }
  }, [isAuthenticated, router])

  // Show loading state while redirecting
  if (isAuthenticated) {
    return null
  }

  const updateField = (field: keyof typeof form) => (event: React.ChangeEvent<HTMLInputElement>) => {
    setForm((prev) => ({ ...prev, [field]: event.target.value }))
    setFieldErrors((prev) => (prev[field] ? { ...prev, [field]: undefined } : prev))
    if (error) {
      clearError()
    }
    if (generalError) {
      setGeneralError(null)
    }
  }

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    clearError()
    setGeneralError(null)

    const nextFieldErrors: RegisterFieldErrors = {}

    const trimmedUsername = form.username.trim()
    const trimmedEmail = form.email.trim()
    const trimmedPassword = form.password.trim()
    const trimmedConfirm = form.confirmPassword.trim()

    if (!trimmedUsername) {
      nextFieldErrors.username = 'Ingresa un nombre de usuario.'
    }
    if (!trimmedEmail) {
      nextFieldErrors.email = 'Ingresa tu correo corporativo.'
    }
    if (!trimmedPassword) {
      nextFieldErrors.password = 'Define una contraseña segura.'
    }
    if (!trimmedConfirm) {
      nextFieldErrors.confirmPassword = 'Confirma tu contraseña.'
    }

    if (trimmedPassword && trimmedPassword.length < 8) {
      nextFieldErrors.password = 'La contraseña debe tener al menos 8 caracteres.'
    }

    if (trimmedPassword && trimmedConfirm && trimmedPassword !== trimmedConfirm) {
      nextFieldErrors.confirmPassword = 'Las contraseñas no coinciden.'
    }

    if (Object.keys(nextFieldErrors).length > 0) {
      setFieldErrors(nextFieldErrors)
      return
    }

    const success = await register({
      username: trimmedUsername,
      email: trimmedEmail,
      password: trimmedPassword,
    })

    if (success) {
      router.push('/chat')
    }
  }

  const isLoading = status === 'loading'

  return (
    <div className="w-full max-w-[420px] rounded-2xl border border-border bg-surface px-8 py-10 shadow-card">
      <div className="mb-8 text-center">
        <h1 className="text-2xl font-semibold text-foreground">Crear cuenta</h1>
      </div>

      {generalError && (
        <div
          className="mb-6 rounded-xl border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-200"
          role="alert"
          aria-live="assertive"
        >
          {generalError}
        </div>
      )}

      <form className="space-y-5" onSubmit={handleSubmit} noValidate>
        <Input
          label="Nombre de usuario"
          placeholder="ej. ana.castro"
          value={form.username}
          onChange={updateField('username')}
          disabled={isLoading}
          error={fieldErrors.username}
          autoComplete="username"
        />

        <Input
          label="Correo corporativo"
          type="email"
          placeholder="usuario@tuempresa.com"
          value={form.email}
          onChange={updateField('email')}
          disabled={isLoading}
          error={fieldErrors.email}
          autoComplete="email"
        />

        <Input
          label="Contraseña"
          type="password"
          placeholder="Mínimo 8 caracteres"
          value={form.password}
          onChange={updateField('password')}
          disabled={isLoading}
          error={fieldErrors.password}
          autoComplete="new-password"
        />

        <Input
          label="Confirmar contraseña"
          type="password"
          placeholder="Repite tu contraseña"
          value={form.confirmPassword}
          onChange={updateField('confirmPassword')}
          disabled={isLoading}
          error={fieldErrors.confirmPassword}
          autoComplete="new-password"
        />

        <Button
          type="submit"
          loading={isLoading}
          disabled={isLoading}
          className="w-full rounded-xl bg-primary text-base font-semibold text-primary-foreground transition-opacity hover:opacity-90 disabled:bg-muted disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60 focus-visible:ring-offset-2 focus-visible:ring-offset-background"
        >
          Crear cuenta
        </Button>
      </form>

      <p className="mt-6 text-center text-sm text-text-muted">
        ¿Ya tienes acceso?{' '}
        <Link
          href="/login"
          className="text-link transition-opacity hover:opacity-80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
        >
          Iniciar sesión
        </Link>
      </p>
    </div>
  )
}
