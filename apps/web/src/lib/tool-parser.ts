import type { ToolInvocation } from "@/lib/types";
import { logError } from "@/lib/logger";

/**
 * Result of parsing tool calls from message content
 */
export interface ParsedToolContent {
  content: string;
  toolInvocations: ToolInvocation[];
}

/**
 * Parses <tool_call> tags from the message content.
 *
 * Example input:
 * "Here is the report. <tool_call> {"name": "create_artifact", "arguments": {...}} </tool_call>"
 *
 * Example output:
 * {
 *   content: "Here is the report. ",
 *   toolInvocations: [{ tool_name: "create_artifact", result: { ...arguments, id: "generated-id" } }]
 * }
 */
export function parseToolCalls(content: string): ParsedToolContent {
  const toolInvocations: ToolInvocation[] = [];
  let cleanedContent = content;

  // Regex to match <tool_call> JSON </tool_call>
  // Using [\s\S]*? for non-greedy match across newlines
  const regex = /<tool_call>([\s\S]*?)<\/tool_call>/g;

  let match;
  while ((match = regex.exec(content)) !== null) {
    try {
      const jsonStr = match[1];
      const parsed = JSON.parse(jsonStr);

      if (parsed.name && parsed.arguments) {
        // For create_artifact, map arguments to result
        // Generate a synthetic ID if missing, as UI requires it
        const result = {
          ...parsed.arguments,
          id:
            parsed.arguments.id ||
            `artifact-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
        };

        toolInvocations.push({
          tool_name: parsed.name,
          result,
        });
      }
    } catch (e) {
      logError("Failed to parse tool call:", e);
    }
  }

  // Remove tags from content
  cleanedContent = content.replace(regex, "").trim();

  return {
    content: cleanedContent,
    toolInvocations,
  };
}
