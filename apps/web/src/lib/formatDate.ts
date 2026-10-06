/**
 * Date and time formatting helpers for SeeDoc.
 *
 * All dates and times are formatted in the Europe/Berlin time zone by default
 * (Germany / Central European Time), matching SeeDoc's German industrial context.
 * An optional timeZone parameter is supported in options to override if needed.
 */

export const DEFAULT_TIME_ZONE = "Europe/Berlin";
export const LOCALE_DE = "de-DE";

export interface DateFormatOptions {
  timeZone?: string;
}

function toDate(date: Date | string | number): Date {
  return typeof date === "object" ? date : new Date(date);
}

/**
 * Formats a date to "dd.MM.yyyy" in the given time zone (default: Europe/Berlin).
 * Example: "06.10.2026"
 */
export function formatDate(date: Date | string | number, options?: DateFormatOptions): string {
  const d = toDate(date);
  const timeZone = options?.timeZone ?? DEFAULT_TIME_ZONE;
  return new Intl.DateTimeFormat(LOCALE_DE, {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    timeZone,
  }).format(d);
}

/**
 * Formats a time to "HH:mm" in 24-hour format in the given time zone (default: Europe/Berlin).
 * Example: "14:30"
 */
export function formatTime(date: Date | string | number, options?: DateFormatOptions): string {
  const d = toDate(date);
  const timeZone = options?.timeZone ?? DEFAULT_TIME_ZONE;
  return new Intl.DateTimeFormat(LOCALE_DE, {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone,
  }).format(d);
}

/**
 * Formats a date and time to "dd.MM.yyyy, HH:mm" in the given time zone (default: Europe/Berlin).
 * Example: "06.10.2026, 14:30"
 */
export function formatDateTime(date: Date | string | number, options?: DateFormatOptions): string {
  const d = toDate(date);
  const timeZone = options?.timeZone ?? DEFAULT_TIME_ZONE;
  const dateStr = formatDate(d, { timeZone });
  const timeStr = formatTime(d, { timeZone });
  return `${dateStr}, ${timeStr}`;
}
