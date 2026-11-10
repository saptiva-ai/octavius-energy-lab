"use client";

/**
 * CodeBlock Component
 *
 * Portado desde: Vercel AI Chatbot
 * Fuente: /home/jazielflo/Proyects/ai-chatbot/components/elements/code-block.tsx
 *
 * Adaptaciones para Octavio's Chat:
 * - Usa react-syntax-highlighter con Prism
 * - Temas oneLight/oneDark para light/dark mode
 * - Botón de copy con feedback visual
 * - Integrado con Tailwind y CSS variables
 * - Context API para compartir código entre bloque y botón
 */

import {
  type ComponentProps,
  type HTMLAttributes,
  type ReactNode,
  createContext,
  useContext,
  useState,
} from "react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import {
  oneDark,
  oneLight,
} from "react-syntax-highlighter/dist/esm/styles/prism";
import { cn } from "@/lib/utils";

type CodeBlockContextType = {
  code: string;
};

const CodeBlockContext = createContext<CodeBlockContextType>({
  code: "",
});

export type CodeBlockProps = HTMLAttributes<HTMLDivElement> & {
  code: string;
  language: string;
  showLineNumbers?: boolean;
  children?: ReactNode;
};

/**
 * Componente para mostrar código con syntax highlighting
 *
 * Características:
 * - Syntax highlighting con Prism
 * - Temas light/dark automáticos
 * - Line numbers opcionales
 * - Copy button integrado
 * - Scroll horizontal para código largo
 * - Tipografía monoespaciada
 */
export function CodeBlock({
  code,
  language,
  showLineNumbers = false,
  className,
  children,
  ...props
}: CodeBlockProps) {
  return (
    <CodeBlockContext.Provider value={{ code }}>
      {/*
        LAYOUT FIX: Code block overflow prevention
        - Changed overflow-hidden → overflow-x-auto to enable horizontal scroll
        - Added max-w-full to respect parent container boundaries
        - Removed overflowWrap/wordBreak from SyntaxHighlighter to preserve code formatting
        - Uses whiteSpace: "pre" to maintain code structure with scroll instead of wrap
      */}
      <div
        className={cn(
          "relative w-full max-w-full overflow-x-auto rounded-lg border border-border bg-background",
          className,
        )}
        {...props}
      >
        <div className="relative">
          {/* Light theme version */}
          <SyntaxHighlighter
            className="!overflow-visible dark:hidden"
            codeTagProps={{
              className: "font-mono text-sm",
            }}
            customStyle={{
              margin: 0,
              padding: "1rem",
              fontSize: "0.875rem",
              background: "hsl(var(--background))",
              color: "hsl(var(--foreground))",
              whiteSpace: "pre",
              overflowX: "visible",
            }}
            language={language}
            lineNumberStyle={{
              color: "hsl(var(--muted-foreground))",
              paddingRight: "1rem",
              minWidth: "2.5rem",
            }}
            showLineNumbers={showLineNumbers}
            style={oneLight}
          >
            {code}
          </SyntaxHighlighter>

          {/* Dark theme version */}
          <SyntaxHighlighter
            className="hidden !overflow-visible dark:block"
            codeTagProps={{
              className: "font-mono text-sm",
            }}
            customStyle={{
              margin: 0,
              padding: "1rem",
              fontSize: "0.875rem",
              background: "hsl(var(--background))",
              color: "hsl(var(--foreground))",
              whiteSpace: "pre",
              overflowX: "visible",
            }}
            language={language}
            lineNumberStyle={{
              color: "hsl(var(--muted-foreground))",
              paddingRight: "1rem",
              minWidth: "2.5rem",
            }}
            showLineNumbers={showLineNumbers}
            style={oneDark}
          >
            {code}
          </SyntaxHighlighter>

          {/* Floating buttons (copy, etc) */}
          {children && (
            <div className="absolute top-2 right-2 flex items-center gap-2">
              {children}
            </div>
          )}
        </div>
      </div>
    </CodeBlockContext.Provider>
  );
}

export type CodeBlockCopyButtonProps = HTMLAttributes<HTMLButtonElement> & {
  onCopy?: () => void;
  onError?: (error: Error) => void;
  timeout?: number;
};

/**
 * Botón de copiar al portapapeles para bloques de código
 *
 * Características:
 * - Copy to clipboard con Clipboard API
 * - Feedback visual (checkmark por 2s)
 * - Error handling
 * - Acceso al código via Context
 */
export function CodeBlockCopyButton({
  onCopy,
  onError,
  timeout = 2000,
  children,
  className,
  ...props
}: CodeBlockCopyButtonProps) {
  const [isCopied, setIsCopied] = useState(false);
  const { code } = useContext(CodeBlockContext);

  const copyToClipboard = async () => {
    if (typeof window === "undefined" || !navigator.clipboard?.writeText) {
      onError?.(new Error("Clipboard API not available"));
      return;
    }

    try {
      await navigator.clipboard.writeText(code);
      setIsCopied(true);
      onCopy?.();
      setTimeout(() => setIsCopied(false), timeout);
    } catch (error) {
      onError?.(error as Error);
    }
  };

  return (
    <button
      className={cn(
        "flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-background/50 text-foreground transition-colors hover:bg-background",
        className,
      )}
      onClick={copyToClipboard}
      type="button"
      aria-label={isCopied ? "Copiado" : "Copiar código"}
      {...props}
    >
      {children ??
        (isCopied ? (
          // Check icon
          <svg
            className="h-4 w-4 text-green-500"
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M5 13l4 4L19 7"
            />
          </svg>
        ) : (
          // Copy icon
          <svg
            className="h-4 w-4"
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
            viewBox="0 0 24 24"
          >
            <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
            <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
          </svg>
        ))}
    </button>
  );
}

/**
 * Helper: Detectar lenguaje desde className de Markdown
 *
 * Markdown usa className="language-javascript" en <code>
 */
export function getLanguageFromClassName(className?: string): string {
  if (!className) return "text";
  const match = className.match(/language-(\w+)/);
  return match ? match[1] : "text";
}
