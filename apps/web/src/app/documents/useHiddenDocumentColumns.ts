import { useState } from "react";

import { DOCUMENT_COLUMNS, type DocumentColumn } from "./documentColumns";

// Which table columns this viewer has hidden. Remembered in this browser only — a convenience, like the chosen
// tenant (useCurrentTenant): if storage is blocked or holds something odd, every column is shown again.
const STORAGE_KEY = "seedoc.documentsTable.hiddenColumns";

// The title is the link to the document, so it can never be hidden.
export const HIDEABLE_DOCUMENT_COLUMNS = DOCUMENT_COLUMNS.filter((column) => column !== "title");

function readHiddenColumns(): DocumentColumn[] {
  try {
    const stored: unknown = JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? "[]");
    return Array.isArray(stored) ? HIDEABLE_DOCUMENT_COLUMNS.filter((column) => stored.includes(column)) : [];
  } catch {
    return [];
  }
}

function writeHiddenColumns(columns: DocumentColumn[]): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(columns));
  } catch {
    // Storage blocked (private mode): the choice lasts until reload.
  }
}

export function useHiddenDocumentColumns() {
  const [hiddenColumns, setHiddenColumns] = useState(readHiddenColumns);

  function setColumnVisible(column: DocumentColumn, visible: boolean) {
    const next = visible ? hiddenColumns.filter((hidden) => hidden !== column) : [...hiddenColumns, column];
    setHiddenColumns(next);
    writeHiddenColumns(next);
  }

  return { hiddenColumns, setColumnVisible };
}
