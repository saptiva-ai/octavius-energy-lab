/**
 * Tipos compartidos del composer.
 *
 * Extraído del antiguo ChatComposer.tsx (componente muerto eliminado en la
 * limpieza de deuda 2026-07-02): el tipo era lo único vivo de ese archivo.
 */
export interface ChatComposerAttachment {
  id: string;
  file: File;
  name: string;
  size: number;
  type: string;
  progress: number;
  status: "uploading" | "completed" | "error";
  errorMessage?: string;
}
