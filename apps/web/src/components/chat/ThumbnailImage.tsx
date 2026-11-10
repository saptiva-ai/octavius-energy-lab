"use client";

/**
 * ThumbnailImage Component
 *
 * Loads thumbnail images with authentication headers.
 *
 * Why needed:
 * - <img> tags don't support custom headers
 * - Backend requires Authorization header
 * - This component uses fetch + blob URL to display authenticated images
 */

import { useEffect, useRef, useState } from "react";
import { useAuthStore } from "@/lib/auth-store";
import { logDebug, logError } from "@/lib/logger";

interface ThumbnailImageProps {
  fileId: string;
  alt: string;
  className?: string;
  onError?: (reuploadRequired?: boolean) => void;
}

export function ThumbnailImage({
  fileId,
  alt,
  className,
  onError,
}: ThumbnailImageProps) {
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [hasError, setHasError] = useState(false);
  const accessToken = useAuthStore((state) => state.accessToken);
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;

  useEffect(() => {
    let objectUrl: string | null = null;

    async function loadThumbnail() {
      if (!accessToken) {
        setHasError(true);
        setIsLoading(false);
        onErrorRef.current?.();
        return;
      }

      try {
        setIsLoading(true);
        setHasError(false);

        const authHeaders = { Authorization: `Bearer ${accessToken}` };

        // Fetch thumbnail via backend proxy
        const thumbnailUrl = `/api/documents/${fileId}/thumbnail`;
        logDebug(
          `[ThumbnailImage] Fetching thumbnail via proxy: ${thumbnailUrl}`,
        );

        const response = await fetch(thumbnailUrl, {
          headers: authHeaders,
        });

        logDebug(`[ThumbnailImage] Response status: ${response.status}`);

        if (!response.ok) {
          const reupload =
            response.headers.get("X-Reupload-Required") === "true";
          logError(
            `[ThumbnailImage] Thumbnail fetch failed: ${response.status} ${response.statusText}`,
            { reuploadRequired: reupload },
          );
          setHasError(true);
          setIsLoading(false);
          onErrorRef.current?.(reupload);
          return;
        }

        const blob = await response.blob();

        objectUrl = URL.createObjectURL(blob);
        setImageUrl(objectUrl);
        setIsLoading(false);
      } catch (error) {
        logError("Failed to load thumbnail:", error);
        setHasError(true);
        setIsLoading(false);
        onErrorRef.current?.();
      }
    }

    loadThumbnail();

    // Cleanup: revoke object URL when component unmounts
    return () => {
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [fileId, accessToken]);

  if (isLoading) {
    return (
      <div className={className}>
        <div className="flex size-full items-center justify-center bg-zinc-800">
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-600 border-t-zinc-400" />
        </div>
      </div>
    );
  }

  if (hasError || !imageUrl) {
    return null; // Let parent component show fallback icon
  }

  // eslint-disable-next-line @next/next/no-img-element
  return <img src={imageUrl} alt={alt} className={className} />;
}
