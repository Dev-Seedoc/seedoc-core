import { describe, expect, it } from "vitest";

import { formatDate, formatDateTime, formatTime } from "./formatDate";

describe("formatDate", () => {
  it("formats date to dd.MM.yyyy in default Europe/Berlin time zone (CEST)", () => {
    // 12:00 UTC on Oct 6 is 14:00 CEST (same day)
    const result = formatDate("2026-10-06T12:00:00Z");
    expect(result).toBe("06.10.2026");
  });

  it("handles midnight boundaries across time zones", () => {
    // 23:30 UTC on Oct 6 is 01:30 CEST on Oct 7 in Europe/Berlin
    const resultBerlin = formatDate("2026-10-06T23:30:00Z");
    expect(resultBerlin).toBe("07.10.2026");

    // When overridden with UTC, it remains Oct 6
    const resultUtc = formatDate("2026-10-06T23:30:00Z", { timeZone: "UTC" });
    expect(resultUtc).toBe("06.10.2026");
  });

  it("accepts Date object and timestamp number", () => {
    const d = new Date("2026-03-01T10:00:00Z");
    expect(formatDate(d)).toBe("01.03.2026");
    expect(formatDate(d.getTime())).toBe("01.03.2026");
  });
});

describe("formatTime", () => {
  it("formats time to HH:mm in default Europe/Berlin time zone", () => {
    // In daylight saving time (CEST, UTC+2)
    const resultCest = formatTime("2026-10-06T12:00:00Z");
    expect(resultCest).toBe("14:00");

    // In standard winter time (CET, UTC+1)
    const resultCet = formatTime("2026-01-15T09:05:00Z");
    expect(resultCet).toBe("10:05");
  });

  it("formats time with overridden timeZone option", () => {
    const resultUtc = formatTime("2026-10-06T12:00:00Z", { timeZone: "UTC" });
    expect(resultUtc).toBe("12:00");
  });
});

describe("formatDateTime", () => {
  it("formats combined date and time to dd.MM.yyyy, HH:mm in Europe/Berlin", () => {
    const result = formatDateTime("2026-10-06T12:00:00Z");
    expect(result).toBe("06.10.2026, 14:00");
  });

  it("formats combined date and time with overridden timeZone option", () => {
    const resultUtc = formatDateTime("2026-10-06T12:00:00Z", { timeZone: "UTC" });
    expect(resultUtc).toBe("06.10.2026, 12:00");
  });
});
