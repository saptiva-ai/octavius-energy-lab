export interface ClarificationOption {
  label: string;
  value: string;
  description?: string;
}

export interface ClarificationField {
  field: string;
  reason: string;
  question: string;
  options: ClarificationOption[];
  allow_custom?: boolean;
}

export interface ClarificationPayload {
  type: "clarification";
  message: string;
  clarifications?: ClarificationField[];
  options?: any[]; // Fallback for new backend format
  original_query?: string;
  confidence?: number;
  related_queries?: string[];
}

export interface ClarificationPromptProps {
  payload: ClarificationPayload;
  onResolve: (selections: Record<string, string>) => void;
  className?: string;
}
