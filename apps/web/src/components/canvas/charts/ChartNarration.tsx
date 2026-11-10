"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";

/** Markdown de la narración de un chart, theme-aware (dark:prose-invert sigue
 * al modo real de la app — MarkdownRenderer del panel usa colores de marca
 * fijos para siempre-dark, no sirve para captions que viven en ambos temas). */
export function ChartNarration({
  text,
  className,
}: {
  text: string;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "prose prose-sm dark:prose-invert max-w-none text-foreground",
        "prose-p:my-1 prose-ul:my-1 prose-li:my-0.5 prose-strong:text-foreground",
        className,
      )}
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
    </div>
  );
}

export default ChartNarration;
