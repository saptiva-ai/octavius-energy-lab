"use client";

import { useEffect, useState, useCallback } from "react";
import { logError, logWarn } from "@/lib/logger";

/**
 * Hook to manage Cloudflare Turnstile widget
 *
 * Turnstile provides invisible CAPTCHA verification that helps
 * Cloudflare trust the user without showing intrusive challenges.
 *
 * Usage:
 * ```tsx
 * const { token, isReady, reset } = useTurnstile('your-site-key');
 * // Include token in API requests
 * ```
 */
export function useTurnstile(siteKey?: string) {
  const [token, setToken] = useState<string | null>(null);
  const [isReady, setIsReady] = useState(false);
  const [widgetId, setWidgetId] = useState<string | null>(null);

  // Load Turnstile script
  useEffect(() => {
    if (!siteKey) {
      logWarn("Turnstile: No site key provided");
      return;
    }

    // Check if script already loaded
    if (window.turnstile) {
      setIsReady(true);
      return;
    }

    const script = document.createElement("script");
    script.src = "https://challenges.cloudflare.com/turnstile/v0/api.js";
    script.async = true;
    script.defer = true;

    script.onload = () => {
      setIsReady(true);
    };

    script.onerror = () => {
      logError("Failed to load Turnstile script");
    };

    document.head.appendChild(script);

    return () => {
      // Cleanup script if component unmounts
      if (script.parentNode) {
        script.parentNode.removeChild(script);
      }
    };
  }, [siteKey]);

  // Render invisible widget when ready
  useEffect(() => {
    if (!isReady || !siteKey || widgetId) return;

    // Create container for invisible widget
    const container = document.createElement("div");
    container.id = "turnstile-widget";
    container.style.display = "none";
    document.body.appendChild(container);

    try {
      const id = window.turnstile.render("#turnstile-widget", {
        sitekey: siteKey,
        callback: (responseToken: string) => {
          setToken(responseToken);
        },
        "error-callback": () => {
          logError("Turnstile verification failed");
          setToken(null);
        },
        "expired-callback": () => {
          logWarn("Turnstile token expired");
          setToken(null);
        },
        theme: "auto",
        size: "invisible",
      });

      setWidgetId(id);
    } catch (error) {
      logError("Failed to render Turnstile widget:", error);
    }

    return () => {
      if (container.parentNode) {
        container.parentNode.removeChild(container);
      }
    };
  }, [isReady, siteKey, widgetId]);

  // Execute challenge manually
  const execute = useCallback(() => {
    if (!isReady || !widgetId) {
      logWarn("Turnstile not ready yet");
      return Promise.reject(new Error("Turnstile not initialized"));
    }

    return new Promise<string>((resolve, reject) => {
      try {
        window.turnstile.execute("#turnstile-widget", {
          callback: (responseToken: string) => {
            setToken(responseToken);
            resolve(responseToken);
          },
          "error-callback": () => {
            reject(new Error("Turnstile verification failed"));
          },
        });
      } catch (error) {
        reject(error);
      }
    });
  }, [isReady, widgetId]);

  // Reset widget
  const reset = useCallback(() => {
    if (isReady && widgetId) {
      window.turnstile.reset("#turnstile-widget");
      setToken(null);
    }
  }, [isReady, widgetId]);

  return {
    token,
    isReady,
    execute,
    reset,
  };
}

// TypeScript declarations for Turnstile global
declare global {
  interface Window {
    turnstile: {
      render: (container: string | HTMLElement, options: any) => string;
      execute: (container: string | HTMLElement, options?: any) => void;
      reset: (container: string | HTMLElement) => void;
      remove: (widgetId: string) => void;
    };
  }
}
