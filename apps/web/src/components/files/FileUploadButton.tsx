"use client";

import * as React from "react";
import { useFiles } from "../../hooks/useFiles";
import { useTurnstile } from "../../hooks/useTurnstile";
import { Button } from "../ui/Button";
import { validateFile, type FileAttachment } from "../../types/files";
import { cn } from "../../lib/utils";
import { logWarn } from "@/lib/logger";

export interface FileUploadButtonProps {
  conversationId?: string;
  onUploadComplete?: (attachments: FileAttachment[]) => void;
  maxFiles?: number;
  variant?: "default" | "outline" | "ghost";
  size?: "default" | "sm" | "lg";
  disabled?: boolean;
  className?: string;
}

/**
 * FileUploadButton - Button to trigger file upload
 *
 * Features:
 * - Client-side validation (size, MIME type)
 * - Multiple file selection
 * - Upload progress indication
 * - Error handling with user-friendly messages
 *
 * Usage:
 * ```tsx
 * <FileUploadButton
 *   conversationId={chatId}
 *   onUploadComplete={(attachments) => {
 *     attachments.forEach(addAttachment)
 *   }}
 * />
 * ```
 */
export function FileUploadButton({
  conversationId,
  onUploadComplete,
  maxFiles = 5,
  variant = "outline",
  size = "default",
  disabled = false,
  className,
}: FileUploadButtonProps) {
  const { uploadFiles, isUploading, error } = useFiles();
  const fileInputRef = React.useRef<HTMLInputElement>(null);

  // Initialize Turnstile for Cloudflare challenge bypass
  // Site key should be set in environment variable NEXT_PUBLIC_TURNSTILE_SITE_KEY
  const turnstileSiteKey = process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY;
  const { execute: executeTurnstile, isReady: turnstileReady } =
    useTurnstile(turnstileSiteKey);

  const [validationErrors, setValidationErrors] = React.useState<string[]>([]);

  const handleClick = () => {
    if (isUploading || disabled) return;
    fileInputRef.current?.click();
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);

    if (files.length === 0) return;

    // Clear previous validation errors
    setValidationErrors([]);

    // Validate files client-side
    const validFiles: File[] = [];
    const errors: string[] = [];

    for (const file of files) {
      const validation = validateFile(file);
      if (!validation.valid) {
        errors.push(`${file.name}: ${validation.error}`);
      } else {
        validFiles.push(file);
      }
    }

    // Limit number of files
    if (validFiles.length > maxFiles) {
      errors.push(`Máximo ${maxFiles} archivos permitidos`);
      validFiles.splice(maxFiles);
    }

    if (errors.length > 0) {
      setValidationErrors(errors);
    }

    if (validFiles.length === 0) {
      // Clear input
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
      return;
    }

    // Execute Turnstile challenge before upload (if configured)
    let turnstileToken: string | undefined;
    if (turnstileSiteKey && turnstileReady) {
      try {
        turnstileToken = await executeTurnstile();
      } catch (turnstileError) {
        logWarn(
          "Turnstile challenge failed, proceeding without token:",
          turnstileError,
        );
        // Continue without token - fallback to Challenge-Redirect Flow
      }
    }

    // Upload valid files with Turnstile token (if available)
    const attachments = await uploadFiles(
      validFiles,
      conversationId,
      turnstileToken,
    );

    if (attachments.length > 0) {
      onUploadComplete?.(attachments);
    }

    // Clear input for next upload
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  // Combine validation errors with upload errors
  const allErrors = [...validationErrors, error].filter(Boolean) as string[];

  return (
    <div className="flex flex-col gap-2">
      <Button
        variant={variant}
        size={size}
        onClick={handleClick}
        disabled={isUploading || disabled}
        loading={isUploading}
        className={cn("gap-2", className)}
        leftIcon={
          !isUploading && (
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z" />
              <polyline points="14 2 14 8 20 8" />
              <path d="M12 18v-6" />
              <path d="m9 15 3-3 3 3" />
            </svg>
          )
        }
      >
        {isUploading ? "Subiendo..." : "Agregar archivos"}
      </Button>

      <input
        ref={fileInputRef}
        type="file"
        className="hidden"
        multiple
        accept=".pdf,.png,.jpg,.jpeg,.gif,.heic"
        onChange={handleFileChange}
        disabled={isUploading || disabled}
      />

      {/* Validation/Upload Errors */}
      {allErrors.length > 0 && (
        <div className="rounded-md bg-red-50 p-3 text-sm text-red-800">
          <div className="flex items-start gap-2">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="mt-0.5 flex-shrink-0"
            >
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <div className="flex-1">
              {allErrors.length === 1 ? (
                <p>{allErrors[0]}</p>
              ) : (
                <ul className="list-inside list-disc space-y-1">
                  {allErrors.map((err, i) => (
                    <li key={i}>{err}</li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
