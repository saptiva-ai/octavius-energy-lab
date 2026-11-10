"use client";

import { useState } from "react";
import Link from "next/link";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setIsLoading(true);

    try {
      const response = await fetch("/api/auth/forgot-password", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ email }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          data.detail || "Error al solicitar recuperación de contraseña",
        );
      }

      setSuccess(true);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Error al solicitar recuperación de contraseña",
      );
    } finally {
      setIsLoading(false);
    }
  };

  if (success) {
    return (
      <div className="w-full max-w-[420px] rounded-2xl border border-border bg-surface px-8 py-10 shadow-card">
        <div className="text-center">
          <div className="mx-auto flex items-center justify-center h-12 w-12 rounded-full bg-primary/20 mb-4">
            <svg
              className="h-6 w-6 text-primary"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
              />
            </svg>
          </div>
          <h2 className="text-2xl font-bold text-foreground mb-2">
            Revisa tu correo
          </h2>
          <div className="mb-3 rounded-xl border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800 dark:border-green-500/40 dark:bg-green-500/10 dark:text-green-100">
            Si el correo <strong className="text-foreground">{email}</strong>{" "}
            existe en nuestro sistema, recibirás un enlace para restablecer tu
            contraseña.
          </div>
          <div className="mb-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-2.5 text-xs text-amber-800 dark:border-amber-500/40 dark:bg-amber-500/10 dark:text-amber-100">
            No olvides revisar tu carpeta de spam o promociones.
          </div>
          <Link
            href="/login"
            className="inline-flex items-center text-primary hover:text-primary/80 font-medium transition-opacity"
          >
            Volver al inicio de sesión
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="w-full max-w-[420px] rounded-2xl border border-border bg-surface px-8 py-10 shadow-card">
      <div className="mb-8 text-center">
        <h1 className="text-2xl font-semibold text-foreground">
          Recuperar Contraseña
        </h1>
        <p className="mt-2 text-sm text-muted">
          Ingresa tu correo electrónico y te enviaremos un enlace para
          restablecer tu contraseña.
        </p>
      </div>
      <div className="mb-6 rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-800 dark:border-blue-500/40 dark:bg-blue-500/10 dark:text-blue-100">
        Asegúrate de usar el correo con el que registraste tu cuenta para que el
        enlace llegue correctamente.
      </div>

      <form className="space-y-5" onSubmit={handleSubmit}>
        {error && (
          <div
            className="mb-6 rounded-xl border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-500/40 dark:bg-red-500/10 dark:text-red-100"
            role="alert"
          >
            {error}
          </div>
        )}

        <div>
          <label
            htmlFor="email-address"
            className="block text-sm font-medium text-foreground mb-1.5"
          >
            Correo electrónico
          </label>
          <input
            id="email-address"
            name="email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full px-3 py-2.5 rounded-xl border border-border bg-surface-2 text-foreground placeholder-muted focus:outline-none focus:ring-2 focus:ring-primary/60 focus:border-primary transition-colors disabled:opacity-50"
            placeholder="tu.correo@empresa.com"
            disabled={isLoading}
          />
        </div>

        <button
          type="submit"
          disabled={isLoading}
          className="w-full rounded-xl bg-primary text-base font-semibold text-primary-foreground py-2.5 transition-opacity hover:opacity-90 disabled:bg-muted disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60 focus-visible:ring-offset-2 focus-visible:ring-offset-background"
        >
          {isLoading ? (
            <span className="flex items-center justify-center">
              <svg
                className="animate-spin -ml-1 mr-3 h-5 w-5 text-primary-foreground"
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                />
              </svg>
              Enviando...
            </span>
          ) : (
            "Enviar enlace de recuperación"
          )}
        </button>

        <div className="text-center">
          <Link
            href="/login"
            className="text-sm text-primary hover:text-primary/80 transition-opacity"
          >
            ← Volver al inicio de sesión
          </Link>
        </div>
      </form>
    </div>
  );
}
