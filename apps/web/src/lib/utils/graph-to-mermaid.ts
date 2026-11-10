type GraphNode = {
  id: string;
  status?: "done" | "running" | "error" | string;
  label?: string;
};

type GraphEdge = {
  from: string;
  to: string;
};

interface GraphPayload {
  nodes?: GraphNode[];
  edges?: GraphEdge[];
}

const STATUS_CLASS: Record<string, string> = {
  done: "done",
  running: "running",
  error: "error",
};

export function graphToMermaid(data: GraphPayload): string {
  const nodes = data?.nodes ?? [];
  const edges = data?.edges ?? [];

  const lines: string[] = ["flowchart TB"];

  nodes.forEach((node) => {
    const label = (node?.label || node?.id || "").replace(/"/g, "'");
    const statusClass = STATUS_CLASS[node?.status || ""] || "pending";
    lines.push(`${node.id}["${label}"]:::${statusClass}`);
  });

  edges.forEach((edge) => {
    if (edge.from && edge.to) {
      lines.push(`${edge.from} --> ${edge.to}`);
    }
  });

  lines.push("classDef done fill:#22c55e,stroke:#22c55e,color:#0f172a;");
  lines.push(
    "classDef running fill:#facc15,stroke:#facc15,color:#0f172a,stroke-width:2px;",
  );
  lines.push("classDef error fill:#ef4444,stroke:#ef4444,color:#0f172a;");
  lines.push("classDef pending fill:#94a3b8,stroke:#94a3b8,color:#0f172a;");

  return lines.join("\n");
}
