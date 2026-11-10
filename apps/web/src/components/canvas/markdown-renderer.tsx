"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { cn } from "@/lib/utils";
import {
  CodeBlock,
  CodeBlockCopyButton,
  getLanguageFromClassName,
} from "../chat/CodeBlock";

interface MarkdownRendererProps {
  content: string;
  className?: string;
}

const components = {
  code: ({
    inline,
    className,
    children,
    ...props
  }: React.HTMLAttributes<HTMLElement> & { inline?: boolean }) => {
    if (inline) {
      return (
        <code
          {...props}
          className={cn(
            "rounded-sm bg-white/10 px-1.5 py-0.5 font-mono text-[0.85em]",
            className,
          )}
        >
          {children}
        </code>
      );
    }

    const language = getLanguageFromClassName(className);
    const codeString = String(children).replace(/\n$/, "");

    return (
      <CodeBlock code={codeString} language={language} className="my-4">
        <CodeBlockCopyButton />
      </CodeBlock>
    );
  },
};

export function MarkdownRenderer({
  content,
  className,
}: MarkdownRendererProps) {
  return (
    <div
      className={cn(
        "prose prose-invert prose-pre:rounded-xl prose-pre:border prose-pre:border-white/5 max-w-none",
        "prose-headings:text-white prose-p:text-saptiva-light prose-a:text-saptiva-mint",
        "prose-code:text-saptiva-mint prose-strong:text-white",
        className,
      )}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight]}
        components={components as any}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
