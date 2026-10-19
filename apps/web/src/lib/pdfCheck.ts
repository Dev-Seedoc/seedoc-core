// The server's upload rules (BUSINESS_RULES §3, apps/api/seedoc/services/uploads.py), checked in the browser before
// anything is sent: PDF by its first bytes, not by its name; not empty; at most 100 MB.
export const MAX_UPLOAD_BYTES = 100 * 1024 * 1024;
export const PDF_CONTENT_TYPE = "application/pdf";
const PDF_MAGIC = "%PDF-";

export type PdfProblem = "notPdf" | "empty" | "tooLarge";

export async function checkPdf(file: Blob): Promise<PdfProblem | null> {
  if (file.size === 0) {
    return "empty";
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return "tooLarge";
  }
  const head = new TextDecoder("latin1").decode(await file.slice(0, PDF_MAGIC.length).arrayBuffer());
  return head === PDF_MAGIC ? null : "notPdf";
}
