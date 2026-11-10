/**
 * DocumentChip - Display document processing status.
 *
 * Shows document name, status, and metadata in a compact chip format.
 */

import React from "react";
import {
  DocumentState,
  DocumentStatusHelpers,
  ProcessingStatus,
} from "@/types/document";

interface DocumentChipProps {
  document: DocumentState;
  onRemove?: (docId: string) => void;
  compact?: boolean;
}

export function DocumentChip({
  document,
  onRemove,
  compact = false,
}: DocumentChipProps) {
  const { doc_id, name, status, pages, error, segments_count } = document;

  const statusIcon = DocumentStatusHelpers.getStatusIcon(status);
  const statusLabel = DocumentStatusHelpers.getStatusLabel(status);
  const statusColor = DocumentStatusHelpers.getStatusColor(status);
  const isProcessing = DocumentStatusHelpers.isProcessing(status);
  const isFailed = DocumentStatusHelpers.isFailed(status);
  const isReady = DocumentStatusHelpers.isReady(status);

  // Color classes based on status
  const colorClasses = {
    blue: "bg-blue-50 border-blue-200 text-blue-700",
    yellow: "bg-yellow-50 border-yellow-200 text-yellow-700",
    green: "bg-green-50 border-green-200 text-green-700",
    red: "bg-red-50 border-red-200 text-red-700",
    gray: "bg-gray-50 border-gray-200 text-gray-700",
  };

  const colorClass =
    colorClasses[statusColor as keyof typeof colorClasses] || colorClasses.gray;

  // Determine file type icon
  const getFileIcon = () => {
    const fileName = name.toLowerCase();
    if (fileName.endsWith(".pdf")) return "📄";
    if (fileName.match(/\.(png|jpg|jpeg|gif|webp|heic)$/)) return "🖼️";
    return "📎";
  };

  return (
    <div
      className={`
        inline-flex items-center gap-2 px-3 py-2 rounded-lg border
        ${colorClass}
        ${compact ? "text-xs" : "text-sm"}
        transition-all duration-200
        ${isProcessing ? "animate-pulse" : ""}
      `}
      title={isFailed ? error : statusLabel}
    >
      {/* Thumbnail Area with Loading State */}
      <div className="relative flex-shrink-0">
        {/* File Icon Background */}
        <div
          className={`
            w-10 h-10 rounded-md flex items-center justify-center text-2xl
            ${isProcessing ? "bg-white/50" : "bg-white/80"}
          `}
        >
          {getFileIcon()}
        </div>

        {/* Loading Spinner Overlay */}
        {isProcessing && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/10 rounded-md">
            <svg
              className="animate-spin h-5 w-5 text-current"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
              />
            </svg>
          </div>
        )}

        {/* Status Badge */}
        <div
          className={`
            absolute -top-1 -right-1 w-4 h-4 rounded-full flex items-center justify-center text-xs
            ${isReady ? "bg-green-500" : isFailed ? "bg-red-500" : "bg-yellow-500"}
          `}
        >
          {statusIcon}
        </div>
      </div>

      {/* Content Area */}
      <div className="flex-1 min-w-0 flex flex-col gap-0.5">
        {/* Document Name */}
        <span className="font-medium truncate max-w-[200px]">{name}</span>

        {/* Metadata */}
        {!compact && (
          <span className="text-xs opacity-75">
            {isReady && segments_count > 0 && (
              <span>{segments_count} segmentos</span>
            )}
            {pages && (
              <span className={segments_count > 0 ? "ml-1" : ""}>
                {segments_count > 0 ? "• " : ""}
                {pages} págs
              </span>
            )}
            {isProcessing && <span className="ml-1">• {statusLabel}</span>}
          </span>
        )}
      </div>

      {/* Remove Button */}
      {onRemove && !isProcessing && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            onRemove(doc_id);
          }}
          className="ml-1 hover:bg-white/50 rounded-full p-1 transition-colors flex-shrink-0"
          aria-label="Remover documento"
        >
          <svg
            className="w-4 h-4"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M6 18L18 6M6 6l12 12"
            />
          </svg>
        </button>
      )}
    </div>
  );
}

/**
 * DocumentChipList - Display multiple documents in a compact list.
 */
interface DocumentChipListProps {
  documents: DocumentState[];
  onRemove?: (docId: string) => void;
  maxVisible?: number;
}

export function DocumentChipList({
  documents,
  onRemove,
  maxVisible = 5,
}: DocumentChipListProps) {
  const visibleDocs = documents.slice(0, maxVisible);
  const hiddenCount = Math.max(0, documents.length - maxVisible);

  if (documents.length === 0) {
    return null;
  }

  return (
    <div className="flex flex-wrap gap-2 items-center">
      {visibleDocs.map((doc) => (
        <DocumentChip
          key={doc.doc_id}
          document={doc}
          onRemove={onRemove}
          compact={documents.length > 3}
        />
      ))}

      {hiddenCount > 0 && (
        <span className="text-xs text-gray-500 px-2">+{hiddenCount} más</span>
      )}
    </div>
  );
}
