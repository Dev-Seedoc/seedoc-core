// Column ids; also the keys of `documents.table.*` and of the column visibility.
export const DOCUMENT_COLUMNS = [
  "title",
  "docType",
  "language",
  "accessLevel",
  "folder",
  "version",
  "status",
  "updatedAt",
  // Only in the trash view.
  "trashedAt",
] as const;
export type DocumentColumn = (typeof DOCUMENT_COLUMNS)[number];
