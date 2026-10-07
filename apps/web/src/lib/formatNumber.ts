/**
 * Number and byte size formatting helpers for SeeDoc.
 *
 * Formats numbers using the German locale ("de-DE") with decimal comma
 * and dot thousands separator.
 */

import { LOCALE_DE } from "./formatLocale";

export { LOCALE_DE };

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
 * Values below 1024 are always shown in B. Fractional input is rounded to whole bytes.
 * NaN, Infinity and negative numbers return "–".
 *
 * Examples:
 *   0 -> "0 B"
 *   0.5 -> "1 B"
 *   1024 -> "1 KB"
 *   1536 -> "1,5 KB"
 *   20971520 -> "20 MB"
 *   -1 -> "–"
 */
export function formatBytes(bytes: number, decimals = 1): string {
  if (!Number.isFinite(bytes) || bytes < 0) {
    return "–";
  }

  const roundedBytes = Math.round(bytes) || 0;
  if (roundedBytes < 1024) {
    return `${formatNumber(roundedBytes)} B`;
  }

  const k = 1024;
  const i = Math.floor(Math.log(roundedBytes) / Math.log(k));
  const unitIndex = Math.min(i, BYTE_UNITS.length - 1);
  const unit = BYTE_UNITS[unitIndex] ?? "B";

  const value = roundedBytes / Math.pow(k, unitIndex);
  return `${formatNumber(value, { maximumFractionDigits: decimals })} ${unit}`;
}
