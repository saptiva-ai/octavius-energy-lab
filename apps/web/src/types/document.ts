/**
 * Document types for document-centric architecture.
 *
 * Mirrors backend DocumentState model.
 */

export enum ProcessingStatus {
  UPLOADING = "uploading",
  PROCESSING = "processing",
  SEGMENTING = "segmenting",
  INDEXING = "indexing",
  READY = "ready",
  FAILED = "failed",
  ARCHIVED = "archived",
}

export interface DocumentState {
  doc_id: string;
  name: string;
  status: ProcessingStatus;
  error?: string;
  pages?: number;
  size_bytes?: number;
  mimetype?: string;
  segments_count: number;
  created_at: string;
  updated_at: string;
  indexed_at?: string;
}

/**
 * Helper functions for document status
 */
export const DocumentStatusHelpers = {
  isReady: (status: ProcessingStatus): boolean => {
    return status === ProcessingStatus.READY;
  },

  isProcessing: (status: ProcessingStatus): boolean => {
    return [
      ProcessingStatus.UPLOADING,
      ProcessingStatus.PROCESSING,
      ProcessingStatus.SEGMENTING,
      ProcessingStatus.INDEXING,
    ].includes(status);
  },

  isFailed: (status: ProcessingStatus): boolean => {
    return status === ProcessingStatus.FAILED;
  },

  getStatusLabel: (status: ProcessingStatus): string => {
    const labels: Record<ProcessingStatus, string> = {
      [ProcessingStatus.UPLOADING]: "Subiendo...",
      [ProcessingStatus.PROCESSING]: "Procesando...",
      [ProcessingStatus.SEGMENTING]: "Segmentando...",
      [ProcessingStatus.INDEXING]: "Indexando...",
      [ProcessingStatus.READY]: "Listo",
      [ProcessingStatus.FAILED]: "Error",
      [ProcessingStatus.ARCHIVED]: "Archivado",
    };
    return labels[status];
  },

  getStatusIcon: (status: ProcessingStatus): string => {
    const icons: Record<ProcessingStatus, string> = {
      [ProcessingStatus.UPLOADING]: "⏫",
      [ProcessingStatus.PROCESSING]: "⚙️",
      [ProcessingStatus.SEGMENTING]: "✂️",
      [ProcessingStatus.INDEXING]: "🔍",
      [ProcessingStatus.READY]: "✅",
      [ProcessingStatus.FAILED]: "❌",
      [ProcessingStatus.ARCHIVED]: "📦",
    };
    return icons[status];
  },

  getStatusColor: (status: ProcessingStatus): string => {
    const colors: Record<ProcessingStatus, string> = {
      [ProcessingStatus.UPLOADING]: "blue",
      [ProcessingStatus.PROCESSING]: "yellow",
      [ProcessingStatus.SEGMENTING]: "yellow",
      [ProcessingStatus.INDEXING]: "yellow",
      [ProcessingStatus.READY]: "green",
      [ProcessingStatus.FAILED]: "red",
      [ProcessingStatus.ARCHIVED]: "gray",
    };
    return colors[status];
  },
};
