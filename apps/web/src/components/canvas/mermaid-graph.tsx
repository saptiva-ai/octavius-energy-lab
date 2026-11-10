"use client";

import * as React from "react";

interface MermaidGraphProps {
  chart: string;
}

export function MermaidGraph({ chart }: MermaidGraphProps) {
  const [svg, setSvg] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let mounted = true;

    const renderMermaid = async () => {
      try {
        const mermaid = (window as any)?.mermaid;
        if (mermaid && typeof mermaid.render === "function") {
          const { svg: rendered } = await mermaid.render(
            `mermaid-${Date.now()}`,
            chart,
          );
          if (mounted) {
            setSvg(rendered);
            setError(null);
          }
        } else {
          if (mounted) {
            setSvg(null);
            setError("Mermaid no está disponible, mostrando texto plano.");
          }
        }
      } catch (err: any) {
        if (mounted) {
          setSvg(null);
          setError(
            err?.message || "No se pudo renderizar el grafo en este momento.",
          );
        }
      }
    };

    void renderMermaid();

    return () => {
      mounted = false;
    };
  }, [chart]);

  if (svg) {
    return (
      <div
        className="mermaid w-full overflow-auto"
        dangerouslySetInnerHTML={{ __html: svg }}
      />
    );
  }

  return (
    <div className="space-y-2">
      {error && (
        <p className="text-xs text-red-200/80">
          {error} Mostrando definición del grafo:
        </p>
      )}
      <pre className="overflow-auto rounded-md border border-white/10 bg-white/5 p-3 text-xs leading-relaxed">
        {chart}
      </pre>
    </div>
  );
}
