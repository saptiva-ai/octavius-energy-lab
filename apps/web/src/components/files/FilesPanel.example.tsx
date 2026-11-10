/**
 * FilesPanel - Example Integration
 *
 * This is an example showing how to integrate Files V1 components
 * into your chat composer.
 *
 * Copy this pattern into your actual ChatComposer component.
 */

"use client";

import * as React from "react";
import { useFiles } from "../../hooks/useFiles";
import { FileUploadButton, FileAttachmentList, FilesToggle } from "./index";
import type { FileAttachment } from "../../types/files";

interface FilesPanelExampleProps {
  conversationId: string;
  onSendMessage: (message: string, fileIds?: string[]) => Promise<void>;
}

export function FilesPanelExample({
  conversationId,
  onSendMessage,
}: FilesPanelExampleProps) {
  const { attachments, addAttachment, removeAttachment, clearAttachments } =
    useFiles();

  const [message, setMessage] = React.useState("");
  const [useFilesInQuestion, setUseFilesInQuestion] = React.useState(false);

  const handleUploadComplete = (newAttachments: FileAttachment[]) => {
    newAttachments.forEach(addAttachment);
    // Auto-enable toggle when files are uploaded
    if (newAttachments.length > 0) {
      setUseFilesInQuestion(true);
    }
  };

  const handleSendMessage = async () => {
    if (!message.trim()) return;

    // Collect file_ids of READY files if toggle is ON
    let fileIds: string[] | undefined;

    if (useFilesInQuestion && attachments.length > 0) {
      const readyFiles = attachments.filter((a) => a.status === "READY");
      fileIds = readyFiles.map((a) => a.file_id);
    }

    // Send message with optional file_ids
    await onSendMessage(message, fileIds);

    // Clear state after sending
    setMessage("");
    clearAttachments();
    setUseFilesInQuestion(false);
  };

  return (
    <div className="flex flex-col gap-4 p-4 border rounded-lg bg-white">
      {/* File Upload Controls */}
      <div className="flex items-center justify-between gap-4">
        <FileUploadButton
          conversationId={conversationId}
          onUploadComplete={handleUploadComplete}
          maxFiles={5}
        />

        {/* Toggle (only visible when there are attachments) */}
        {attachments.length > 0 && (
          <FilesToggle
            enabled={useFilesInQuestion}
            onChange={setUseFilesInQuestion}
            fileCount={attachments.length}
          />
        )}
      </div>

      {/* File Attachments List */}
      {attachments.length > 0 && (
        <FileAttachmentList
          attachments={attachments}
          onRemove={removeAttachment}
        />
      )}

      {/* Message Input */}
      <div className="flex flex-col gap-2">
        <textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Escribe tu mensaje..."
          className="w-full min-h-[100px] p-3 border rounded-md resize-none focus:outline-none focus:ring-2 focus:ring-primary/60"
        />

        <div className="flex items-center justify-between">
          <div className="text-xs text-gray-500">
            {useFilesInQuestion && attachments.length > 0 && (
              <span>
                ✓ Se incluirán{" "}
                {attachments.filter((a) => a.status === "READY").length}{" "}
                archivo(s) en la pregunta
              </span>
            )}
          </div>

          <button
            onClick={handleSendMessage}
            disabled={!message.trim()}
            className="px-4 py-2 bg-primary text-white rounded-md hover:bg-primary-600 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Enviar
          </button>
        </div>
      </div>
    </div>
  );
}

/**
 * Integration Guide
 * =================
 *
 * To integrate into your existing ChatComposer:
 *
 * 1. Import the hooks and components:
 *    ```tsx
 *    import { useFiles } from '@/hooks/useFiles'
 *    import { FileUploadButton, FileAttachmentList, FilesToggle } from '@/components/files'
 *    ```
 *
 * 2. Add state management:
 *    ```tsx
 *    const { attachments, addAttachment, removeAttachment, clearAttachments } = useFiles()
 *    const [useFilesInQuestion, setUseFilesInQuestion] = useState(false)
 *    ```
 *
 * 3. Add UI in your composer:
 *    ```tsx
 *    <div className="composer-controls">
 *      <FileUploadButton
 *        conversationId={conversationId}
 *        onUploadComplete={(newAttachments) => {
 *          newAttachments.forEach(addAttachment)
 *        }}
 *      />
 *
 *      {attachments.length > 0 && (
 *        <FilesToggle
 *          enabled={useFilesInQuestion}
 *          onChange={setUseFilesInQuestion}
 *          fileCount={attachments.length}
 *        />
 *      )}
 *    </div>
 *
 *    {attachments.length > 0 && (
 *      <FileAttachmentList
 *        attachments={attachments}
 *        onRemove={removeAttachment}
 *      />
 *    )}
 *    ```
 *
 * 4. Modify your sendMessage function:
 *    ```tsx
 *    const handleSendMessage = async (message: string) => {
 *      const payload: any = {
 *        message,
 *        conversation_id: conversationId,
 *      }
 *
 *      // Add file_ids if toggle is ON and files are READY
 *      if (useFilesInQuestion && attachments.length > 0) {
 *        const readyFiles = attachments.filter(a => a.status === 'READY')
 *        payload.file_ids = readyFiles.map(a => a.file_id)
 *      }
 *
 *      await apiClient.sendMessage(payload)
 *
 *      // Clear after sending
 *      clearAttachments()
 *    }
 *    ```
 *
 * 5. That's it! The backend will automatically include file context
 *    when file_ids are present in the payload.
 */
