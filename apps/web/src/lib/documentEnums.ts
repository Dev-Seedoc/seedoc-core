import type { AccessLevel, DocType } from "@/lib/api/types";

// Every value of the generated enum types, in display order. Written as `Record<…, true>` so the compiler fails here
// when the API adds a value that a dropdown would otherwise miss. Labels: `common.accessLevel.*`, `common.docType.*`.
const ACCESS_LEVEL_KEYS = { public: true, customer: true, internal: true } satisfies Record<AccessLevel, true>;

const DOC_TYPE_KEYS = {
  operating_manual: true,
  installation_manual: true,
  maintenance_manual: true,
  safety_instruction: true,
  datasheet: true,
  spare_parts_list: true,
  wiring_diagram: true,
  declaration_of_conformity: true,
  certificate: true,
  test_report: true,
  training_material: true,
  other: true,
} satisfies Record<DocType, true>;

export const ACCESS_LEVELS = Object.keys(ACCESS_LEVEL_KEYS) as AccessLevel[];
export const DOC_TYPES = Object.keys(DOC_TYPE_KEYS) as DocType[];
