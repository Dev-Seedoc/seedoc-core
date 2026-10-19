// SHA-256 of a file as 64 lowercase hex characters (UploadCreate.sha256_hex), with the browser's WebCrypto — no
// extra package. The whole file is read into memory; uploads are at most 100 MB (BUSINESS_RULES §3).
export async function sha256Hex(file: Blob): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}
