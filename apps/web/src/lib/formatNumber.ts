/**
 * Number and byte size formatting helpers for SeeDoc.
 *
 * Formats numbers using the German locale ("de-DE") with decimal comma
 * and dot thousands separator.
 */

export const LOCALE_DE = "de-DE";

const BYTE_UNITS = ["B", "KB", "MB", "GB", "TB", "PB"] as const;

/**
 * Formats a number with German decimal comma and thousand separators.
 * Example: 1234.56 -> "1.234,56"
 */
export function formatNumber(value: number, options?: Intl.NumberFormatOptions): string {
  return new Intl.NumberFormat(LOCALE_DE, options).format(value);
}

/**
 * Formats a byte size with decimal comma and appropriate binary unit (B, KB, MB, GB, ...).
 * Examples:
 *   0 -> "0 B"
 *   1024 -> "1 KB"
 *   1536 -> "1,5 KB"
 *   20971520 -> "20 MB"
 */
export function formatBytes(bytes: number, decimals = 1): string {
  if (bytes < 0) {
    throw new RangeError("Byte value cannot be negative");
  }
  if (bytes === 0) {
    return "0 B";
  }

  const k = 1024;
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  const unitIndex = Math.min(i, BYTE_UNITS.length - 1);
  const unit = BYTE_UNITS[unitIndex] ?? "B";

  if (unitIndex === 0) {
    return `${formatNumber(bytes, { maximumFractionDigits: 0 })} ${unit}`;
  }

  const value = bytes / Math.pow(k, unitIndex);
  return `${formatNumber(value, { maximumFractionDigits: decimals })} ${unit}`;
}
