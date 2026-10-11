"use client";

import { useCallback, useEffect, useState } from "react";
import { connector, type DocumentSummary } from "@/connector";
import styles from "./documents.module.css";

const ACCEPTED_TYPES = ".pdf,.txt,.md,.markdown,application/pdf,text/plain,text/markdown";
const PENDING_POLL_MS = 2_000;
const STATUS_LABELS: Record<DocumentSummary["status"], string> = {
  pending: "reading…",
  indexed: "ready",
  failed: "failed",
};

function describe(error: unknown): string {
  return error instanceof Error ? error.message : "Request failed";
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function detailFor(document: DocumentSummary): string {
  const pages = document.page_count === null ? null : `${document.page_count} pp`;
  return [formatSize(document.size_bytes), pages].filter(Boolean).join(" · ");
}

export function useDocuments() {
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [uploading, setUploading] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(
    () =>
      connector
        .listDocuments()
        .then((listing) => setDocuments(listing.documents))
        .catch((caught: unknown) => setError(describe(caught))),
    [],
  );

  useEffect(() => {
    let active = true;
    connector
      .listDocuments()
      .then((listing) => {
        if (active) setDocuments(listing.documents);
      })
      .catch((caught: unknown) => {
        if (active) setError(describe(caught));
      });
    return () => {
      active = false;
    };
  }, []);

  const anyPending = documents.some((document) => document.status === "pending");
  useEffect(() => {
    if (!anyPending) return;
    const timer = setTimeout(refresh, PENDING_POLL_MS);
    return () => clearTimeout(timer);
  }, [anyPending, documents, refresh]);

  const upload = useCallback(
    async (files: File[]) => {
      setError(null);
      setUploading((count) => count + files.length);
      for (const file of files) {
        try {
          await connector.uploadDocument(file, file.name);
        } catch (caught: unknown) {
          setError(`${file.name}: ${describe(caught)}`);
        } finally {
          setUploading((count) => count - 1);
        }
      }
      await refresh();
    },
    [refresh],
  );

  const remove = useCallback(
    async (documentId: string) => {
      setError(null);
      try {
        await connector.deleteDocument(documentId);
      } catch (caught: unknown) {
        setError(describe(caught));
      }
      await refresh();
    },
    [refresh],
  );

  return { documents, uploading, error, upload, remove };
}

interface DocumentPickerProps {
  onFiles: (files: File[]) => void;
  disabled?: boolean;
  className?: string;
}

export function DocumentPicker({ onFiles, disabled, className }: DocumentPickerProps) {
  return (
    <label className={className} data-disabled={disabled || undefined}>
      <input
        className={styles.fileInput}
        type="file"
        accept={ACCEPTED_TYPES}
        multiple
        disabled={disabled}
        onChange={(event) => {
          const files = Array.from(event.target.files ?? []);
          event.target.value = "";
          if (files.length > 0) onFiles(files);
        }}
      />
      <span aria-hidden="true">+</span>
      <span className={styles.visuallyHidden}>Add a document</span>
    </label>
  );
}

interface DocumentShelfProps {
  documents: DocumentSummary[];
  uploading: number;
  error: string | null;
  onRemove: (documentId: string) => void;
}

export function DocumentShelf({
  documents,
  uploading,
  error,
  onRemove,
}: DocumentShelfProps) {
  if (documents.length === 0 && uploading === 0 && !error) return null;

  return (
    <section className={styles.shelf} aria-label="Documents">
      <p className={styles.heading}>
        documents
        {uploading > 0 && <span className={styles.uploading}> · uploading…</span>}
      </p>
      {error && <p className={styles.error}>{error}</p>}
      <ul className={styles.items}>
        {documents.map((document) => (
          <li key={document.id} className={styles.item}>
            <span className={styles.name} title={document.filename}>
              {document.filename}
            </span>
            <span className={styles.meta}>{detailFor(document)}</span>
            <span
              className={styles.status}
              data-status={document.status}
              title={document.error ?? undefined}
            >
              {STATUS_LABELS[document.status]}
            </span>
            <button
              className={styles.remove}
              type="button"
              aria-label={`Delete ${document.filename}`}
              onClick={() => onRemove(document.id)}
            >
              ×
            </button>
            {document.status === "failed" && document.error && (
              <p className={styles.reason}>{document.error}</p>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
