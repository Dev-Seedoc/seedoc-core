import type { AccessLevel, DocType, ProcessingStatus } from "@/lib/api/types";
import { ACCESS_LEVELS, DOC_TYPES, PROCESSING_STATUSES } from "@/lib/documentEnums";
import { SUPPORTED_LANGUAGES } from "@/lib/languages";

// Filters of the documents table, stored in the URL under the query names of list_documents (API.md §3.3), next to
// `space_id` / `folder_id`. Unknown values (an edited or outdated link) are ignored, never sent to the API.
export interface DocumentFilters {
  q?: string;
  doc_type?: DocType;
  language?: (typeof SUPPORTED_LANGUAGES)[number];
  access_level?: AccessLevel;
  processing_status?: ProcessingStatus;
}

export const DOCUMENT_FILTER_PARAMS = ["q", "doc_type", "language", "access_level", "processing_status"] as const;

function oneOf<T extends string>(values: readonly T[], value: string | null): T | undefined {
  return values.find((candidate) => candidate === value);
}

export function readDocumentFilters(params: URLSearchParams): DocumentFilters {
  const filters: DocumentFilters = {
    q: params.get("q")?.trim() || undefined,
    doc_type: oneOf(DOC_TYPES, params.get("doc_type")),
    language: oneOf(SUPPORTED_LANGUAGES, params.get("language")),
    access_level: oneOf(ACCESS_LEVELS, params.get("access_level")),
    processing_status: oneOf(PROCESSING_STATUSES, params.get("processing_status")),
  };
  return Object.fromEntries(Object.entries(filters).filter(([, value]) => value !== undefined));
}

export function hasDocumentFilters(filters: DocumentFilters): boolean {
  return Object.keys(filters).length > 0;
}

// Only the set filters, ready to merge into the URL parameters.
export function documentFilterParams(filters: DocumentFilters): Record<string, string> {
  return Object.fromEntries(Object.entries(filters).filter((entry): entry is [string, string] => Boolean(entry[1])));
}
