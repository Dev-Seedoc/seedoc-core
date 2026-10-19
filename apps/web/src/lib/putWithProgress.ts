// PUT of a file to a presigned upload URL with progress. `fetch` cannot report upload progress, XMLHttpRequest can.
// The URL goes straight to object storage (not through the API), so no cookie is sent.

export class UploadFailedError extends Error {
  // HTTP status from the store; 0 = no answer (network error or CORS refusal).
  readonly status: number;

  constructor(status: number) {
    super(`upload failed with HTTP ${String(status)}`);
    this.name = "UploadFailedError";
    this.status = status;
  }
}

interface PutOptions {
  contentType: string;
  // 0 … 1 while the bytes are sent.
  onProgress?: (fraction: number) => void;
  signal?: AbortSignal;
}

export function putWithProgress(
  url: string,
  body: Blob,
  { contentType, onProgress, signal }: PutOptions,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("PUT", url);
    // Signed into the URL (API.md §3.3): any other type is refused by the store with 403.
    request.setRequestHeader("Content-Type", contentType);
    request.upload.onprogress = (event) => {
      if (event.lengthComputable && event.total > 0) {
        onProgress?.(event.loaded / event.total);
      }
    };
    request.onload = () => {
      if (request.status >= 200 && request.status < 300) {
        onProgress?.(1);
        resolve();
      } else {
        reject(new UploadFailedError(request.status));
      }
    };
    // Network error, CORS refusal or abort: no HTTP status to report.
    request.onerror = () => {
      reject(new UploadFailedError(0));
    };
    request.onabort = () => {
      reject(new DOMException("upload aborted", "AbortError"));
    };
    signal?.addEventListener("abort", () => {
      request.abort();
    });
    request.send(body);
  });
}
