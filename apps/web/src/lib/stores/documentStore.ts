/**
 * Document Store - State management for document processing.
 *
 * Uses Zustand for lightweight state management.
 */

import { create } from "zustand";
import { DocumentState, ProcessingStatus } from "@/types/document";

interface DocumentStore {
  // State
  documents: Record<string, DocumentState>;

  // Actions
  updateDocument: (doc: DocumentState) => void;
  updateDocumentStatus: (
    docId: string,
    status: ProcessingStatus,
    error?: string,
  ) => void;
  removeDocument: (docId: string) => void;
  clearDocuments: () => void;
  getDocument: (docId: string) => DocumentState | undefined;
  getDocumentsBySession: (sessionId: string) => DocumentState[];
}

export const useDocumentStore = create<DocumentStore>((set, get) => ({
  documents: {},

  updateDocument: (doc: DocumentState) => {
    set((state) => ({
      documents: {
        ...state.documents,
        [doc.doc_id]: doc,
      },
    }));
  },

  updateDocumentStatus: (
    docId: string,
    status: ProcessingStatus,
    error?: string,
  ) => {
    set((state) => {
      const doc = state.documents[docId];
      if (!doc) return state;

      return {
        documents: {
          ...state.documents,
          [docId]: {
            ...doc,
            status,
            error,
            updated_at: new Date().toISOString(),
          },
        },
      };
    });
  },

  removeDocument: (docId: string) => {
    set((state) => {
      const { [docId]: removed, ...rest } = state.documents;
      return { documents: rest };
    });
  },

  clearDocuments: () => {
    set({ documents: {} });
  },

  getDocument: (docId: string) => {
    return get().documents[docId];
  },

  getDocumentsBySession: (sessionId: string) => {
    // Future: Filter by session when we track session_id in documents
    return Object.values(get().documents);
  },
}));
