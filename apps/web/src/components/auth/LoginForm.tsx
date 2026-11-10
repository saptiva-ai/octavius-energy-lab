"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import { Input, Button } from "../ui";
import { useAuthStore } from "../../lib/auth-store";
import { useAppStore } from "../../lib/store";

type FieldErrorState = {
  identifier?: string;
  password?: string;
};

export function LoginForm() {
  const router = useRouter();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [fieldErrors, setFieldErrors] = useState<FieldErrorState>({});
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [sessionExpiredMessage, setSessionExpiredMessage] = useState<
    string | null
  >(null);

  const {
    status,
    error,
    clearError,
    login,
    isHydrated,
    accessToken,
    user,
    intendedPath,
    setIntendedPath,
  } = useAuthStore((state) => ({
    status: state.status,
    error: state.error,
    clearError: state.clearError,
    login: state.login,
    isHydrated: state.isHydrated,
    accessToken: state.accessToken,
    user: state.user,
    intendedPath: state.intendedPath,
    setIntendedPath: state.setIntendedPath,
  }));

  // Fix: useAppStore is not a selector-based hook, it returns an object
  const { loadChatSessions } = useAppStore();

  // Check for expiration reason in URL query params
  useEffect(() => {
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      const reason = params.get("reason");

      if (reason && reason.includes("expired")) {
        setSessionExpiredMessage(
          "Tu sesión ha expirado. Por favor, inicia sesión nuevamente.",
        );
      }
    }
  }, []);

  useEffect(() => {
    if (!error) {
      setGeneralError(null);
      return;
    }

    if (
      error.field &&
      ["email", "username", "identifier"].includes(error.field)
    ) {
      setFieldErrors((prev) => ({ ...prev, identifier: error.message }));
      setGeneralError(null);
      return;
    }

    if (error.field === "password") {
      setFieldErrors((prev) => ({ ...prev, password: error.message }));
      setGeneralError(null);
      return;
    }

    setGeneralError(error.message);
  }, [error]);

  const resetFieldError = (field: keyof FieldErrorState) => {
    setFieldErrors((prev) =>
      prev[field] ? { ...prev, [field]: undefined } : prev,
    );
    if (error) {
      clearError();
    }
    if (generalError) {
      setGeneralError(null);
    }
  };

  const isAuthenticated = isHydrated && Boolean(accessToken && user);

  // P0-FIX: Silent redirect instead of showing "already logged in" notice
  useEffect(() => {
    if (isAuthenticated) {
      const destination = intendedPath || "/chat";
      router.replace(destination);
      if (intendedPath) {
        setIntendedPath(null);
      }
    }
  }, [isAuthenticated, intendedPath, router, setIntendedPath]);

  // Show loading state while redirecting
  if (isAuthenticated) {
    return null;
  }

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    clearError();
    setGeneralError(null);

    const trimmedIdentifier = identifier.trim();
    const trimmedPassword = password.trim();

    const nextFieldErrors: FieldErrorState = {};
    if (!trimmedIdentifier) {
      nextFieldErrors.identifier = "Ingresa tu correo o usuario.";
    }
    if (!trimmedPassword) {
      nextFieldErrors.password = "Ingresa tu contraseña.";
    }

    if (Object.keys(nextFieldErrors).length > 0) {
      setFieldErrors(nextFieldErrors);
      return;
    }

    const success = await login({
      identifier: trimmedIdentifier,
      password: trimmedPassword,
    });
    if (success) {
      // Preload chat sessions before redirecting to avoid empty history bug
      await loadChatSessions();
      const destination = intendedPath || "/chat";
      router.push(destination);
      if (intendedPath) {
        setIntendedPath(null);
      }
    }
  };

  const isLoading = status === "loading";

  return (
    <div className="w-full max-w-[420px] rounded-2xl border border-border bg-surface px-8 py-10 shadow-card">
      <div className="mb-8 text-center">
        <h1 className="text-2xl font-semibold text-foreground">Iniciar sesión</h1>
      </div>

      {sessionExpiredMessage && (
        <div
          className="mb-6 rounded-xl border border-[#2DD4BF]/40 bg-gray-900 px-4 py-3 flex items-start gap-3"
          style={{ color: "#2DD4BF" }}
          role="alert"
          aria-live="polite"
        >
          <svg
            className="w-5 h-5 flex-shrink-0 mt-0.5"
            fill="currentColor"
            viewBox="0 0 20 20"
            aria-hidden="true"
          >
            <path
              fillRule="evenodd"
              d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z"
              clipRule="evenodd"
            />
          </svg>
          <p className="text-sm">{sessionExpiredMessage}</p>
        </div>
      )}

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
          label="Correo electrónico o usuario"
          placeholder="tu.nombre@saptiva.ai"
          value={identifier}
          onChange={(event) => {
            setIdentifier(event.target.value);
            resetFieldError("identifier");
          }}
          disabled={isLoading}
          error={fieldErrors.identifier}
          autoComplete="username"
        />

        <Input
          label="Contraseña"
          type="password"
          placeholder="••••••••"
          value={password}
          onChange={(event) => {
            setPassword(event.target.value);
            resetFieldError("password");
          }}
          disabled={isLoading}
          error={fieldErrors.password}
          autoComplete="current-password"
        />

        <Button
          type="submit"
          loading={isLoading}
          disabled={isLoading}
          className="w-full rounded-xl bg-primary text-base font-semibold text-primary-foreground transition-opacity hover:opacity-90 disabled:bg-muted disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60 focus-visible:ring-offset-2 focus-visible:ring-offset-background"
        >
          Iniciar sesión
        </Button>
      </form>

      <div className="mt-6 text-center text-sm text-text-muted">
        <Link
          href="/forgot-password"
          className="text-link transition-opacity hover:opacity-80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
        >
          ¿Olvidaste tu contraseña?
        </Link>
      </div>

      <p className="mt-4 text-center text-sm text-text-muted">
        ¿Necesitas una cuenta?{" "}
        <a
          href="mailto:support@saptiva.com?subject=Solicitud%20de%20cuenta%20OctaviOS"
          className="text-link transition-opacity hover:opacity-80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
        >
          Contacta a un administrador
        </a>
      </p>
    </div>
  );
}
