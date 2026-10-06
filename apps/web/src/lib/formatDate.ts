/**
 * Date and time formatting helpers for SeeDoc.
 *
 * All dates and times are formatted using the German locale ("de-DE") in the
 * viewer's local time zone by default (no timeZone passed to Intl). An optional
 * timeZone parameter is supported in options to override if needed.
 *
 * Date-only strings (e.g. "2026-10-06") represent calendar dates and format
 * to "06.10.2026" in every time zone.
 */

import { LOCALE_DE } from "./formatLocale";

export { LOCALE_DE };

export interface DateFormatOptions {
  timeZone?: string;
}

const DATE_ONLY_REGEX = /^\d{4}-\d{2}-\d{2}$/;

function toDate(date: Date | string | number): Date {
  return typeof date === "object" ? date : new Date(date);
}

/**
 * Formats a date to "dd.MM.yyyy" in the viewer's local time zone by default
 * (or the specified timeZone option).
 * Date-only strings (e.g. "2026-10-06") represent calendar dates and format
 * to "06.10.2026" in every time zone.
 * Example: "06.10.2026"
 */
export function formatDate(date: Date | string | number, options?: DateFormatOptions): string {
  if (typeof date === "string" && DATE_ONLY_REGEX.test(date)) {
    return new Intl.DateTimeFormat(LOCALE_DE, {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      timeZone: "UTC",
    }).format(new Date(`${date}T00:00:00Z`));
  }
  const d = toDate(date);
  return new Intl.DateTimeFormat(LOCALE_DE, {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    ...(options?.timeZone ? { timeZone: options.timeZone } : {}),
  }).format(d);
}

/**
 * Formats a time to "HH:mm" in 24-hour format in the viewer's local time zone by default
 * (or the specified timeZone option).
 * Example: "14:30"
 */
export function formatTime(date: Date | string | number, options?: DateFormatOptions): string {
  const d = toDate(date);
  return new Intl.DateTimeFormat(LOCALE_DE, {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    ...(options?.timeZone ? { timeZone: options.timeZone } : {}),
  }).format(d);
}

/**
 * Formats a date and time to "dd.MM.yyyy, HH:mm" in the viewer's local time zone by default
 * (or the specified timeZone option).
 * Example: "06.10.2026, 14:30"
 */
export function formatDateTime(date: Date | string | number, options?: DateFormatOptions): string {
  const dateStr = formatDate(date, options);
  const timeStr = formatTime(date, options);
  return `${dateStr}, ${timeStr}`;
}
