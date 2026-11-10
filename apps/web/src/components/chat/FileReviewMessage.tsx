"use client";

/**
 * FileReviewMessage - Renders file review card in chat flow
 *
 * Displays upload progress, review stages, and action buttons
 * Integrates with useDocumentReview hook for actions
 */

import { useCallback } from "react";
import type { ChatMessage } from "../../lib/types";
import { FileCard, type FileCardState } from "../document-review/FileCard";
import { useDocumentReview } from "../../hooks/useDocumentReview";
import { useSSE } from "../../hooks/useSSE";
import { logDebug } from "../../lib/logger";

interface FileReviewMessageProps {
  message: ChatMessage;
}

export function FileReviewMessage({ message }: FileReviewMessageProps) {
  const { review } = message;
  const { startReview, getReviewReport } = useDocumentReview();

  // Connect SSE for real-time updates (only if reviewing)
  useSSE(
    review?.jobId || null,
    review?.docId || null,
    review?.status === "reviewing",
  );

  const handleStartReview = useCallback(
    async (docId: string) => {
      await startReview(docId, {
        model: "Saptiva Turbo",
        rewritePolicy: "conservative",
        summary: true,
        colorAudit: true,
      });
    },
    [startReview],
  );

  const handleViewResults = useCallback(
    async (docId: string) => {
      const report = await getReviewReport(docId);
      if (report) {
        // TODO: Open report modal/panel
        logDebug("[FileReviewMessage] Review report fetched", {
          docId,
          report,
        });
      }
    },
    [getReviewReport],
  );

  if (!review) {
    return null;
  }

  const mapStatusToCardState = (status: string): FileCardState => {
    switch (status) {
      case "uploading":
        return "uploading";
      case "processing":
        return "processing";
      case "uploaded":
      case "ready":
        return "ready";
      case "reviewing":
        return "reviewing";
      case "completed":
        return "completed";
      case "error":
      case "failed":
        return "error";
      default:
        return "processing";
    }
  };

  return (
    <div className="my-4">
      <FileCard
        filename={review.filename}
        fileSize={review.fileSize || 0}
        docId={review.docId}
        state={mapStatusToCardState(review.status)}
        progress={review.progress || 0}
        errorMessage={review.errors?.[0]}
        onStartReview={handleStartReview}
        onViewResults={handleViewResults}
      />
    </div>
  );
}
