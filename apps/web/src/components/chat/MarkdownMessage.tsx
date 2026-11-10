"use client";

/**
 * MarkdownMessage Component
 *
 * CHANGELOG:
 * - 2025-01-17: Integrado CodeBlock con react-syntax-highlighter (portado de Vercel)
 * - Reemplazado rehype-highlight con CodeBlock custom
 * - Agregado copy button a bloques de código
 */

import * as React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import rehypeSanitize from "rehype-sanitize"; // FIX ISSUE-008: Prevent XSS attacks
import remend from "remend"; // FIX P3: Complete broken markdown during streaming
import { cn } from "../../lib/utils";
import type { PluggableList } from "unified";
import "katex/dist/katex.min.css";
import {
  CodeBlock,
  CodeBlockCopyButton,
  getLanguageFromClassName,
} from "./CodeBlock";
import { logError } from "@/lib/logger";
import { normalizeLatexSyntax } from "@/lib/markdown-normalize";

/**
 * BA-003 FIX: Strip SQL from chat messages
 * SQL should only be shown in the canvas panel, not in chat
 */
function stripSqlFromContent(text: string): string {
  if (!text) return text;

  let result = text;

  // Remove SQL code blocks (```sql ... ```)
  result = result.replace(/```sql[\s\S]*?```/gi, "");

  // Remove generic code blocks containing SQL keywords
  result = result.replace(
    /```[\s\S]*?(?:SELECT|INSERT|UPDATE|DELETE)[\s\S]*?```/gi,
    "",
  );

  // Remove multi-line SQL after intro phrases
  result = result.replace(
    /(?:La consulta SQL utilizada fue|La consulta utilizada fue|La consulta SQL fue|El query utilizado fue|Consulta SQL utilizada|SQL utilizado fue)[:\s]*\n+(?:SELECT|INSERT|UPDATE|DELETE)[\s\S]*?;/gi,
    "",
  );

  // Remove orphaned SQL intro phrases
  result = result.replace(
    /(?:La consulta SQL utilizada fue|La consulta utilizada fue|La consulta SQL fue|El query utilizado fue|Consulta SQL utilizada|SQL utilizado fue)[:\s]*/gi,
    "",
  );

  // Clean up excessive newlines
  result = result.replace(/\n{3,}/g, "\n\n");

  return result.trim();
}

interface MarkdownMessageProps {
  content: string;
  className?: string;
  /**
   * Enable syntax highlighting when true. During streaming we can disable
   * this to avoid re-processing the markdown on every token.
   */
  highlightCode?: boolean;
  /**
   * BA-003: Skip SQL stripping during streaming for performance.
   * SQL will be stripped once streaming completes.
   */
  skipSqlStripping?: boolean;
}

/** Caracteres desde los que una celda de tabla parte renglón. */
const CELDA_TEXTO_LARGO = 32;

function textoDeCelda(children: React.ReactNode): string {
  // Recursivo: el narrador pone cifras en negritas (**49 piezas**).
  return React.Children.toArray(children)
    .map((c) => {
      if (typeof c === "string" || typeof c === "number") return String(c);
      if (React.isValidElement<{ children?: React.ReactNode }>(c)) {
        return textoDeCelda(c.props.children);
      }
      return "";
    })
    .join("");
}

const defaultComponents = {
  a: ({ node: _, href, children, ...props }: any) => {
    // Detect audit report download links
    const isAuditReportDownload = href?.match(
      /\/api\/reports\/audit\/([^/]+)\/download/,
    );

    if (isAuditReportDownload) {
      const reportId = isAuditReportDownload[1];

      return (
        <button
          onClick={async (e) => {
            e.preventDefault();
            try {
              // Get auth token from localStorage
              const authData = localStorage.getItem("auth-storage");
              const token = authData
                ? JSON.parse(authData)?.state?.token
                : null;

              if (!token) {
                alert("Debes iniciar sesión para descargar el reporte");
                return;
              }

              // Fetch the PDF with authentication
              const response = await fetch(href, {
                headers: {
                  Authorization: `Bearer ${token}`,
                },
              });

              if (!response.ok) {
                throw new Error("Error al descargar el reporte");
              }

              // Create a blob and download
              const blob = await response.blob();
              const url = window.URL.createObjectURL(blob);
              const a = document.createElement("a");
              a.href = url;
              a.download = `reporte-auditoria-${reportId}.pdf`;
              document.body.appendChild(a);
              a.click();
              window.URL.revokeObjectURL(url);
              document.body.removeChild(a);
            } catch (error) {
              logError("Error downloading audit report:", error);
              alert(
                "Error al descargar el reporte. Por favor intenta nuevamente.",
              );
            }
          }}
          className={cn(
            "inline-flex items-center gap-2 px-4 py-2 rounded-md",
            "bg-primary/10 hover:bg-primary/20",
            "text-primary font-medium",
            "border border-primary/30",
            "transition-colors cursor-pointer",
            props.className,
          )}
        >
          {children}
        </button>
      );
    }

    // Regular links
    return (
      <a
        {...props}
        href={href}
        className={cn(
          "text-primary underline decoration-dotted underline-offset-2 hover:text-primary/80 transition-colors",
          props.className,
        )}
        target="_blank"
        rel="noreferrer"
      />
    );
  },
  pre: ({ children, ...props }: React.HTMLAttributes<HTMLPreElement>) => {
    // Extract code props from the child code element
    // ReactMarkdown wraps block code in <pre><code>...</code></pre>
    const codeElement = React.isValidElement(children) ? children : null;

    if (
      codeElement &&
      (codeElement.type === "code" ||
        codeElement.type === defaultComponents.code)
    ) {
      const { className, children: codeChildren } =
        codeElement.props as React.HTMLAttributes<HTMLElement>;
      const language = getLanguageFromClassName(className);
      const codeString = String(codeChildren).replace(/\n$/, "");

      return (
        <CodeBlock code={codeString} language={language} className="my-4">
          <CodeBlockCopyButton />
        </CodeBlock>
      );
    }

    // Fallback for non-standard pre usage
    return <pre {...props}>{children}</pre>;
  },
  code: ({
    className,
    children,
    ...props
  }: React.HTMLAttributes<HTMLElement>) => {
    // Inline code (not wrapped in pre)
    return (
      <code
        {...props}
        className={cn(
          "rounded-md bg-muted/20 px-1.5 py-0.5 font-mono text-[0.85em] text-primary",
          className,
        )}
      >
        {children}
      </code>
    );
  },
  blockquote: ({ className, ...props }: React.HTMLAttributes<HTMLElement>) => (
    <blockquote
      {...props}
      className={cn("border-l-2 border-primary/50 pl-4 text-muted", className)}
    />
  ),
  ul: ({ className, ...props }: React.HTMLAttributes<HTMLUListElement>) => (
    <ul
      {...props}
      className={cn(
        "list-disc space-y-2 pl-5 marker:text-primary/80",
        className,
      )}
    />
  ),
  ol: ({ className, ...props }: React.HTMLAttributes<HTMLOListElement>) => (
    <ol
      {...props}
      className={cn(
        "list-decimal space-y-2 pl-5 marker:text-primary/80",
        className,
      )}
    />
  ),
  // Contenedor con borde y barra visible en ambos temas (`thin-scroll`): una
  // tabla más ancha que la burbuja se recorría sin ninguna señal (feedback de
  // QA, 2026-10-16, punto 7).
  table: ({ className, ...props }: React.HTMLAttributes<HTMLTableElement>) => (
    <div className="overflow-x-auto max-w-full thin-scroll rounded-md border border-border pb-1">
      <table
        {...props}
        className={cn(
          // my-0: el margen de .prose dejaba una franja vacía sobre el encabezado.
          "min-w-full border-collapse text-left text-sm my-0",
          className,
        )}
      />
    </div>
  ),
  th: ({ className, ...props }: React.HTMLAttributes<HTMLTableCellElement>) => (
    <th
      {...props}
      className={cn(
        "border border-border bg-surface-2 px-3 py-2 text-foreground font-medium whitespace-nowrap",
        className,
      )}
    />
  ),
  // Cifras y textos cortos en un renglón; el texto largo ("Razón principal")
  // parte renglón para que la tabla quepa en la burbuja.
  td: ({
    className,
    children,
    ...props
  }: React.HTMLAttributes<HTMLTableCellElement>) => (
    <td
      {...props}
      className={cn(
        "border border-border px-3 py-2 align-top text-foreground",
        textoDeCelda(children).length > CELDA_TEXTO_LARGO
          ? "whitespace-normal min-w-[8rem] max-w-[22rem]"
          : "whitespace-nowrap",
        className,
      )}
    >
      {children}
    </td>
  ),
};

// Normalización de LaTeX e importes en pesos: vive en lib para testearse sin
// montar react-markdown (card 2026-09-03__FIX__markdown-chat-pesos-como-latex).

export function MarkdownMessage({
  content,
  className,
  highlightCode = true,
  skipSqlStripping = false,
}: MarkdownMessageProps) {
  // BA-003 FIX: Strip SQL + Normalize LaTeX syntax before rendering
  // Skip SQL stripping during streaming for performance (runs O(n) regex)
  // P3-FIX: Use remend to complete broken markdown (unclosed **bold**, *italic*, etc.)
  const normalizedContent = React.useMemo(() => {
    const processed = skipSqlStripping ? content : stripSqlFromContent(content);
    const normalized = normalizeLatexSyntax(processed);
    // remend completes unterminated markdown blocks (e.g., "**bold" → "**bold**")
    // This prevents broken rendering during streaming when LLM sends incomplete syntax
    return remend(normalized);
  }, [content, skipSqlStripping]);

  const markdownPlugins = React.useMemo(() => {
    const remarkPlugins: PluggableList = [remarkGfm, remarkMath];
    const rehypePlugins: PluggableList = [];

    // FIX ISSUE-008: Sanitize HTML first to prevent XSS
    rehypePlugins.push(rehypeSanitize);

    // NOTE: Removed rehypeHighlight - now using CodeBlock component instead
    // Syntax highlighting is handled by react-syntax-highlighter in CodeBlock

    rehypePlugins.push(rehypeKatex);
    return {
      remark: remarkPlugins,
      rehype: rehypePlugins,
    };
  }, []);

  return (
    <div
      className={cn(
        "prose dark:prose-invert max-w-none text-sm prose-p:text-foreground prose-headings:text-foreground prose-strong:text-foreground prose-li:text-foreground",
        // LAYOUT FIX: Add min-w-0 to allow prose content to shrink below content size in flex layouts
        "min-w-0",
        className,
      )}
    >
      <ReactMarkdown
        remarkPlugins={markdownPlugins.remark}
        rehypePlugins={markdownPlugins.rehype}
        components={defaultComponents}
      >
        {normalizedContent}
      </ReactMarkdown>
    </div>
  );
}

export default MarkdownMessage;
