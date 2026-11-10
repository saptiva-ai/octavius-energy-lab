/**
 * Types for Files V1 - Unified File Ingestion System
 *
 * See: VALIDATION_REPORT_V1.md for complete specification
 */

/**
 * File processing status
 */
export type FileStatus = "RECEIVED" | "PROCESSING" | "READY" | "FAILED";

/**
 * Error codes from backend
 */
export type FileErrorCode =
  | "UPLOAD_TOO_LARGE" // File >10MB
  | "UNSUPPORTED_MIME" // MIME type not in whitelist
  | "EXTRACTION_FAILED" // Processing error
  | "RATE_LIMITED" // >5 uploads/min
  | "OCR_TIMEOUT" // OCR timeout (reserved for V1.1)
  | "QUOTA_EXCEEDED"; // Storage quota exceeded (V1.1)

/**
 * Error object from backend
 */
export interface FileError {
  code: FileErrorCode;
  detail?: string;
}

/**
 * Response from /api/files/upload (single file)
 */
export interface FileIngestResponse {
  file_id: string;
  doc_id?: string; // Alias for backward compatibility
  status: FileStatus;
  mimetype?: string;
  bytes: number;
  pages?: number;
  name?: string;
  filename?: string;
  error?: FileError;
}

/**
 * Response from /api/files/upload (bulk)
 */
export interface FileIngestBulkResponse {
  files: FileIngestResponse[];
}

/**
 * SSE Event from /api/files/events/{file_id}
 */
export type FileEventPhase = "upload" | "extract" | "cache" | "complete";

export interface FileEventPayload {
  file_id: string;
  phase: FileEventPhase;
  pct: number; // 0.0 - 100.0
  trace_id?: string;
  status?: FileStatus;
  error?: FileError;
}

/**
 * Upload progress tracking
 */
export interface UploadProgress {
  loaded: number;
  total: number;
  percentage: number;
}

/**
 * File attachment for chat context
 */
export interface FileAttachment {
  file_id: string;
  filename: string;
  status: FileStatus;
  bytes: number;
  pages?: number;
  mimetype?: string;
}

/**
 * Supported MIME types (from backend)
 */
export const SUPPORTED_MIME_TYPES = [
  "application/pdf",
  "image/png",
  "image/jpeg",
  "image/jpg",
  "image/heic",
  "image/heif",
  "image/gif",
] as const;

export type SupportedMimeType = (typeof SUPPORTED_MIME_TYPES)[number];

/**
 * Max upload size - reads from NEXT_PUBLIC_MAX_FILE_SIZE_MB environment variable
 * Fallback: 50MB (matches production backend)
 */
const MAX_FILE_SIZE_MB = process.env.NEXT_PUBLIC_MAX_FILE_SIZE_MB
  ? parseInt(process.env.NEXT_PUBLIC_MAX_FILE_SIZE_MB, 10)
  : 50;

export const MAX_UPLOAD_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024; // Convert MB to bytes

/**
 * Rate limit (10 uploads per minute for testing, 5 in production)
 */
export const RATE_LIMIT_UPLOADS_PER_MINUTE = 10;

/**
 * User-friendly error messages
 */
export const FILE_ERROR_MESSAGES: Record<FileErrorCode, string> = {
  UPLOAD_TOO_LARGE: `El archivo es demasiado grande. Máximo ${MAX_FILE_SIZE_MB} MB.`,
  UNSUPPORTED_MIME:
    "Tipo de archivo no soportado. Usa PDF, PNG, JPG, GIF o HEIC.",
  EXTRACTION_FAILED: "Error al procesar el archivo. Intenta de nuevo.",
  RATE_LIMITED:
    "Demasiados archivos subidos. Espera un minuto e intenta de nuevo.",
  OCR_TIMEOUT:
    "El archivo tardó demasiado en procesarse. Intenta con un archivo más pequeño.",
  QUOTA_EXCEEDED:
    "Has alcanzado tu límite de almacenamiento. Elimina algunos archivos.",
};

/**
 * Helper to check if file type is supported
 */
export function isSupportedMimeType(
  mimeType: string,
): mimeType is SupportedMimeType {
  return SUPPORTED_MIME_TYPES.includes(mimeType as SupportedMimeType);
}

/**
 * Helper to check if file size is within limit
 */
export function isFileSizeValid(sizeBytes: number): boolean {
  return sizeBytes > 0 && sizeBytes <= MAX_UPLOAD_SIZE;
}

/**
 * Get user-friendly error message
 */
export function getErrorMessage(error: FileError): string {
  return FILE_ERROR_MESSAGES[error.code] || error.detail || "Error desconocido";
}

/**
 * Validate file before upload
 */
export interface FileValidationResult {
  valid: boolean;
  error?: string;
}

export function validateFile(file: File): FileValidationResult {
  // Check size
  if (!isFileSizeValid(file.size)) {
    return {
      valid: false,
      error: FILE_ERROR_MESSAGES.UPLOAD_TOO_LARGE,
    };
  }

  // Check MIME type
  if (!isSupportedMimeType(file.type)) {
    return {
      valid: false,
      error: FILE_ERROR_MESSAGES.UNSUPPORTED_MIME,
    };
  }

  return { valid: true };
}
