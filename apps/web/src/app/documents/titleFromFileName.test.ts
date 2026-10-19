import { describe, expect, it } from "vitest";

import { TITLE_MAX_LENGTH, titleFromFileName } from "./titleFromFileName";

describe("titleFromFileName", () => {
  it("drops .pdf in any case and turns underscores into spaces", () => {
    expect(titleFromFileName("Betriebsanleitung_Laser.pdf")).toBe("Betriebsanleitung Laser");
    expect(titleFromFileName("Wartung__2026.PDF")).toBe("Wartung 2026");
    expect(titleFromFileName("Datenblatt v2.1.pdf")).toBe("Datenblatt v2.1");
  });

  it("stays within the API's title limit", () => {
    expect(titleFromFileName(`${"x".repeat(300)}.pdf`)).toHaveLength(TITLE_MAX_LENGTH);
  });
});
