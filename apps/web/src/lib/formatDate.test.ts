import { describe, expect, it } from "vitest";

import { formatDate, formatDateTime, formatTime } from "./formatDate";

describe("formatDate", () => {
  it("formats date to dd.MM.yyyy with explicit timeZone", () => {
    // 12:00 UTC on Oct 6 is 14:00 CEST in Europe/Berlin (same day)
    const resultBerlin = formatDate("2026-10-06T12:00:00Z", { timeZone: "Europe/Berlin" });
    expect(resultBerlin).toBe("06.10.2026");

    const resultUtc = formatDate("2026-10-06T12:00:00Z", { timeZone: "UTC" });
    expect(resultUtc).toBe("06.10.2026");
  });

  it("handles midnight boundaries across time zones", () => {
    // 23:30 UTC on Oct 6 is 01:30 CEST on Oct 7 in Europe/Berlin
    const resultBerlin = formatDate("2026-10-06T23:30:00Z", { timeZone: "Europe/Berlin" });
    expect(resultBerlin).toBe("07.10.2026");

    // When overridden with UTC, it remains Oct 6
    const resultUtc = formatDate("2026-10-06T23:30:00Z", { timeZone: "UTC" });
    expect(resultUtc).toBe("06.10.2026");

    // In America/New_York (UTC-4 in EDT), 23:30 UTC is 19:30 on Oct 6
    const resultNy = formatDate("2026-10-06T23:30:00Z", { timeZone: "America/New_York" });
    expect(resultNy).toBe("06.10.2026");
  });

  it("accepts Date object and timestamp number", () => {
    const d = new Date("2026-03-01T10:00:00Z");
    expect(formatDate(d, { timeZone: "UTC" })).toBe("01.03.2026");
    expect(formatDate(d.getTime(), { timeZone: "UTC" })).toBe("01.03.2026");
  });

  it("formats date-only calendar strings consistently in any time zone", () => {
    expect(formatDate("2026-10-06", { timeZone: "America/New_York" })).toBe("06.10.2026");
    expect(formatDate("2026-10-06", { timeZone: "Europe/Berlin" })).toBe("06.10.2026");
    expect(formatDate("2026-10-06", { timeZone: "UTC" })).toBe("06.10.2026");
    expect(formatDate("2026-10-06", { timeZone: "Asia/Tokyo" })).toBe("06.10.2026");
  });
});

describe("formatTime", () => {
  it("formats time to HH:mm with explicit timeZone", () => {
    // In daylight saving time (CEST, UTC+2)
    const resultCest = formatTime("2026-10-06T12:00:00Z", { timeZone: "Europe/Berlin" });
    expect(resultCest).toBe("14:00");

    // In standard winter time (CET, UTC+1)
    const resultCet = formatTime("2026-01-15T09:05:00Z", { timeZone: "Europe/Berlin" });
    expect(resultCet).toBe("10:05");
  });

  it("formats time with overridden timeZone option", () => {
    const resultUtc = formatTime("2026-10-06T12:00:00Z", { timeZone: "UTC" });
    expect(resultUtc).toBe("12:00");

    const resultNy = formatTime("2026-10-06T12:00:00Z", { timeZone: "America/New_York" });
    expect(resultNy).toBe("08:00");
  });
});

describe("formatDateTime", () => {
  it("formats combined date and time to dd.MM.yyyy, HH:mm with explicit timeZone", () => {
    const result = formatDateTime("2026-10-06T12:00:00Z", { timeZone: "Europe/Berlin" });
    expect(result).toBe("06.10.2026, 14:00");
  });

  it("formats combined date and time with overridden timeZone option", () => {
    const resultUtc = formatDateTime("2026-10-06T12:00:00Z", { timeZone: "UTC" });
    expect(resultUtc).toBe("06.10.2026, 12:00");

    const resultNy = formatDateTime("2026-10-06T12:00:00Z", { timeZone: "America/New_York" });
    expect(resultNy).toBe("06.10.2026, 08:00");
  });
});
