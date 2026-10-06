import { describe, expect, it } from "vitest";

import { formatBytes, formatNumber } from "./formatNumber";

describe("formatNumber", () => {
  it("formats integers using German thousands separator (dot)", () => {
    expect(formatNumber(1000)).toBe("1.000");
    expect(formatNumber(1000000)).toBe("1.000.000");
    expect(formatNumber(42)).toBe("42");
  });

  it("formats decimals using German comma", () => {
    expect(formatNumber(12.5)).toBe("12,5");
    expect(formatNumber(1234.56)).toBe("1.234,56");
  });

  it("respects custom Intl options", () => {
    const formatted = formatNumber(12.3, { minimumFractionDigits: 2 });
    expect(formatted).toBe("12,30");
  });
});

describe("formatBytes", () => {
  it("formats 0 bytes as 0 B", () => {
    expect(formatBytes(0)).toBe("0 B");
  });

  it("formats small byte amounts without decimals", () => {
    expect(formatBytes(500)).toBe("500 B");
  });

  it("formats kilobyte amounts with German decimal comma", () => {
    expect(formatBytes(1024)).toBe("1 KB");
    expect(formatBytes(1536)).toBe("1,5 KB");
  });

  it("formats megabytes, gigabytes, and terabytes", () => {
    expect(formatBytes(1048576)).toBe("1 MB");
    expect(formatBytes(1048576 * 20)).toBe("20 MB");
    expect(formatBytes(1073741824 * 1.5)).toBe("1,5 GB");
  });

  it("throws RangeError on negative input", () => {
    expect(() => formatBytes(-1)).toThrow(RangeError);
  });
});
