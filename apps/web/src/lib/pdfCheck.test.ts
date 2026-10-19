import { describe, expect, it } from "vitest";

import { checkPdf, MAX_UPLOAD_BYTES } from "./pdfCheck";

// Stands in for a file of `size` bytes without allocating them: checkPdf only reads `size` and `slice`.
function blobOfSize(size: number, head = "%PDF-1.7"): Blob {
  const content = new Blob([head]);
  const fake: Pick<Blob, "size" | "slice"> = { size, slice: (start, end) => content.slice(start, end) };
  return fake as Blob;
}

describe("checkPdf", () => {
  it("accepts a PDF by its first bytes, whatever its name or type", async () => {
    expect(await checkPdf(new File(["%PDF-1.7\n…"], "scan.bin", { type: "application/octet-stream" }))).toBeNull();
  });

  it("rejects files that only look like a PDF", async () => {
    expect(await checkPdf(new File(["<html>"], "anleitung.pdf", { type: "application/pdf" }))).toBe("notPdf");
  });

  it("rejects empty files and files over 100 MB", async () => {
    expect(await checkPdf(new File([], "leer.pdf"))).toBe("empty");
    expect(await checkPdf(blobOfSize(MAX_UPLOAD_BYTES))).toBeNull();
    expect(await checkPdf(blobOfSize(MAX_UPLOAD_BYTES + 1))).toBe("tooLarge");
  });
});
