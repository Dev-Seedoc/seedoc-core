import { afterEach, describe, expect, it, vi } from "vitest";

import { putWithProgress, UploadFailedError } from "./putWithProgress";

// A stand-in for XMLHttpRequest: records the request; the test decides what the "store" answers.
class FakeXhr {
  static last: FakeXhr | undefined;
  method = "";
  url = "";
  headers: Record<string, string> = {};
  body: unknown;
  status = 0;
  upload: { onprogress: ((event: { lengthComputable: boolean; loaded: number; total: number }) => void) | null } = {
    onprogress: null,
  };
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onabort: (() => void) | null = null;

  constructor() {
    FakeXhr.last = this;
  }
  open(method: string, url: string) {
    this.method = method;
    this.url = url;
  }
  setRequestHeader(name: string, value: string) {
    this.headers[name] = value;
  }
  send(body: unknown) {
    this.body = body;
  }
  abort() {
    this.onabort?.();
  }
  answer(status: number) {
    this.status = status;
    this.onload?.();
  }
}

function lastRequest(): FakeXhr {
  if (!FakeXhr.last) {
    throw new Error("no request was sent");
  }
  return FakeXhr.last;
}

afterEach(() => {
  vi.unstubAllGlobals();
  FakeXhr.last = undefined;
});

describe("putWithProgress", () => {
  it("PUTs the file with its content type and reports progress", async () => {
    vi.stubGlobal("XMLHttpRequest", FakeXhr);
    const file = new Blob(["%PDF-"]);
    const progress: number[] = [];

    const done = putWithProgress("https://s3.example/upload?sig=1", file, {
      contentType: "application/pdf",
      onProgress: (fraction) => progress.push(fraction),
    });
    const request = lastRequest();
    request.upload.onprogress?.({ lengthComputable: true, loaded: 25, total: 100 });
    request.answer(200);
    await done;

    expect([request.method, request.url, request.headers["Content-Type"], request.body]).toEqual([
      "PUT",
      "https://s3.example/upload?sig=1",
      "application/pdf",
      file,
    ]);
    expect(progress).toEqual([0.25, 1]);
  });

  it("fails with the store's status, or 0 when there was no answer", async () => {
    vi.stubGlobal("XMLHttpRequest", FakeXhr);

    const refused = putWithProgress("u", new Blob([]), { contentType: "application/pdf" });
    lastRequest().answer(403);
    await expect(refused).rejects.toEqual(new UploadFailedError(403));

    const offline = putWithProgress("u", new Blob([]), { contentType: "application/pdf" });
    lastRequest().onerror?.();
    await expect(offline).rejects.toMatchObject({ status: 0 });
  });

  it("stops when the signal aborts", async () => {
    vi.stubGlobal("XMLHttpRequest", FakeXhr);
    const controller = new AbortController();

    const upload = putWithProgress("u", new Blob([]), { contentType: "application/pdf", signal: controller.signal });
    controller.abort();

    await expect(upload).rejects.toMatchObject({ name: "AbortError" });
  });
});
