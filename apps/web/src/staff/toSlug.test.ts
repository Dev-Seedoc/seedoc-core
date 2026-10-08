import { describe, expect, it } from "vitest";

import { SLUG_MAX_LENGTH, SLUG_PATTERN, toSlug } from "./toSlug";

describe("toSlug", () => {
  it.each([
    ["Müller Maschinenbau GmbH", "mueller-maschinenbau-gmbh"],
    ["Größe & Söhne KG", "groesse-soehne-kg"],
    ["  Café  Crème  ", "cafe-creme"],
    ["ABC-123 / Werk 2", "abc-123-werk-2"],
    ["---", ""],
  ])("turns %j into %j", (name, slug) => {
    expect(toSlug(name)).toBe(slug);
  });

  it("caps the length without leaving a trailing hyphen", () => {
    const slug = toSlug(`${"a".repeat(62)} b`);

    expect(slug).toBe("a".repeat(62));
    expect(slug.length).toBeLessThanOrEqual(SLUG_MAX_LENGTH);
  });

  it("produces slugs the API accepts", () => {
    expect(toSlug("Müller Maschinenbau GmbH")).toMatch(SLUG_PATTERN);
  });
});
