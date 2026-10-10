import { createHmac } from "node:crypto";

// TOTP codes for the test staff user (RFC 6238 with the defaults pyotp uses in the API: HMAC-SHA1, 30 s, 6 digits).
// Built on node:crypto so the test needs no extra package (NAMING §10).

const BASE32_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
const TOTP_STEP_SECONDS = 30;
const TOTP_DIGITS = 6;

// Same clean-up as the seed: spaces removed, upper case; `=` padding is optional.
function decodeBase32(secret: string): Buffer {
  const bytes: number[] = [];
  let buffer = 0;
  let bitCount = 0;
  for (const char of secret.replace(/[\s=]/g, "").toUpperCase()) {
    const index = BASE32_ALPHABET.indexOf(char);
    if (index === -1) {
      throw new Error("E2E_STAFF_TOTP_SECRET is not base32 (A-Z, 2-7)");
    }
    buffer = (buffer << 5) | index;
    bitCount += 5;
    if (bitCount >= 8) {
      bitCount -= 8;
      bytes.push((buffer >> bitCount) & 0xff);
      buffer &= (1 << bitCount) - 1;
    }
  }
  return Buffer.from(bytes);
}

// The code an authenticator app shows at `timeMs`. The API also accepts the previous and next step (clock drift).
export function getTotpCode(secret: string, timeMs: number = Date.now()): string {
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(timeMs / 1000 / TOTP_STEP_SECONDS)));
  const hmac = createHmac("sha1", decodeBase32(secret)).update(counter).digest();
  // Dynamic truncation (RFC 4226 §5.3).
  const offset = hmac.readUInt8(hmac.length - 1) & 0x0f;
  const binary = hmac.readUInt32BE(offset) & 0x7fffffff;
  return String(binary % 10 ** TOTP_DIGITS).padStart(TOTP_DIGITS, "0");
}
