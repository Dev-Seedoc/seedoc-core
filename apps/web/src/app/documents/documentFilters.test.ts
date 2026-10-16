import { describe, expect, it } from "vitest";

import { documentFilterParams, hasDocumentFilters, readDocumentFilters } from "./documentFilters";

describe("document filters in the URL", () => {
  it("reads every known filter", () => {
    const params = new URLSearchParams(
      "q=%20Pumpe%20&doc_type=datasheet&language=en&access_level=internal&processing_status=failed&folder_id=f",
    );

    expect(readDocumentFilters(params)).toEqual({
      q: "Pumpe",
      doc_type: "datasheet",
      language: "en",
      access_level: "internal",
      processing_status: "failed",
    });
  });

  it("ignores unknown values from an edited or old link", () => {
    const params = new URLSearchParams("q=%20%20&doc_type=quatsch&language=DE&access_level=secret&processing_status=x");

    expect(readDocumentFilters(params)).toEqual({});
    expect(hasDocumentFilters(readDocumentFilters(params))).toBe(false);
  });

  it("turns only the set filters into URL parameters", () => {
    expect(documentFilterParams({ q: "Pumpe", doc_type: undefined, language: "de" })).toEqual({
      q: "Pumpe",
      language: "de",
    });
  });
});
