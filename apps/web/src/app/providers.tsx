"use client";

import { ReactNode, useState } from "react";
import { usePathname } from "next/navigation";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { CanvasProvider } from "@/context/CanvasContext";

/**
 * Rutas que siempre se ven en tema claro, sin tocar la preferencia guardada
 * del usuario (forcedTheme no escribe en localStorage).
 */
const RUTAS_TEMA_CLARO: string[] = [];

/**
 * React Query configuration for the application
 *
 * Optimized settings:
 * - staleTime: 60s (data fresh for 1 minute before refetch)
 * - refetchOnWindowFocus: false (prevents unnecessary refetches)
 * - retry: 1 (single retry on failure)
 * - refetchOnMount: false (uses cached data on mount if available)
 */
export function Providers({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const temaForzado = RUTAS_TEMA_CLARO.some(
    (ruta) => pathname === ruta || pathname?.startsWith(`${ruta}/`),
  )
    ? "light"
    : undefined;
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 60 * 1000, // 60 seconds
            refetchOnWindowFocus: false,
            retry: 1,
            refetchOnMount: false,
          },
        },
      }),
  );

  return (
    <ThemeProvider
      attribute="class"
      defaultTheme="dark"
      forcedTheme={temaForzado}
      enableSystem
      disableTransitionOnChange={false}
    >
      <QueryClientProvider client={queryClient}>
        <CanvasProvider>{children}</CanvasProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
