// Limit of `Title` (= `Name`: trimmed, 1–200 characters) in apps/api/seedoc/schemas/documents.py.
export const TITLE_MAX_LENGTH = 200;

// A starting title for an uploaded file: "Betriebsanleitung_Laser.pdf" → "Betriebsanleitung Laser".
export function titleFromFileName(fileName: string): string {
  return fileName
    .replace(/\.pdf$/i, "")
    .replace(/_+/g, " ")
    .trim()
    .slice(0, TITLE_MAX_LENGTH);
}
