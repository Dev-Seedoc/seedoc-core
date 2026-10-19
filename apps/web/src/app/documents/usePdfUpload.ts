import type { TFunction } from "i18next";

import { getErrorMessage } from "@/lib/api/errors";
import { useCreateUpload } from "@/lib/api/hooks/documents";
import { PDF_CONTENT_TYPE } from "@/lib/pdfCheck";
import { putWithProgress, UploadFailedError } from "@/lib/putWithProgress";
import { sha256Hex } from "@/lib/sha256";

// Where one file is on its way to the store; the caller shows it.
export type PdfUploadStep = { name: "hashing" } | { name: "uploading"; progress: number };

// The first half of every upload (API.md §3.3), shared by new documents and new versions: SHA-256 in the browser →
// create_upload → PUT to the presigned URL. Returns the upload id for create_document / create_document_version.
export function usePdfUpload(tenantId: string) {
  const createUpload = useCreateUpload(tenantId);

  return async function uploadPdf(file: File, onStep: (step: PdfUploadStep) => void): Promise<string> {
    onStep({ name: "hashing" });
    const sha256 = await sha256Hex(file);
    const upload = await createUpload.mutateAsync({
      file_name: file.name,
      size_bytes: file.size,
      sha256_hex: sha256,
      content_type: PDF_CONTENT_TYPE,
    });
    onStep({ name: "uploading", progress: 0 });
    await putWithProgress(upload.upload_url, file, {
      contentType: PDF_CONTENT_TYPE,
      onProgress: (progress) => {
        onStep({ name: "uploading", progress });
      },
    });
    return upload.upload_id;
  };
}

// The store answers in its own format (no API error code): one plain message for every store problem.
export function getUploadErrorMessage(error: unknown, t: TFunction): string {
  return error instanceof UploadFailedError ? t("documents.upload.storeFailed") : getErrorMessage(error);
}
