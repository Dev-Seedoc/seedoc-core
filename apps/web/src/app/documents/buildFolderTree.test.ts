import { describe, expect, it } from "vitest";

import type { FolderRead } from "@/lib/api/types";

import { buildFolderTree, type FolderNode } from "./buildFolderTree";

function folder(id: string, name: string, parentId: string | null = null, sortOrder = 0): FolderRead {
  return {
    id,
    space_id: "s",
    parent_id: parentId,
    name,
    path: name,
    sort_order: sortOrder,
    default_access_level: "public",
    default_doc_type: null,
    default_language: null,
    created_at: "2026-10-13T10:00:00Z",
    updated_at: "2026-10-13T10:00:00Z",
  };
}

// "Name" for a leaf, "Name[child, child]" for a folder with subfolders.
function outline(nodes: FolderNode[]): string[] {
  return nodes.map((node) =>
    node.children.length ? `${node.folder.name}[${outline(node.children).join(", ")}]` : node.folder.name,
  );
}

describe("buildFolderTree", () => {
  it("nests folders under their parent, whatever order the list has", () => {
    const tree = buildFolderTree([
      folder("laser", "Laser", "hinweise"),
      folder("wartung", "Wartung"),
      folder("hinweise", "Hinweise", "sicherheit"),
      folder("sicherheit", "Sicherheit"),
    ]);

    expect(outline(tree)).toEqual(["Sicherheit[Hinweise[Laser]]", "Wartung"]);
  });

  it("sorts siblings by sort_order, then by name in German order", () => {
    const tree = buildFolderTree([
      folder("z", "Zubehör"),
      folder("o", "Ölwechsel"),
      folder("i", "Intervalle"),
      folder("first", "Zuerst", null, -1),
    ]);

    expect(outline(tree)).toEqual(["Zuerst", "Intervalle", "Ölwechsel", "Zubehör"]);
  });

  it("returns an empty tree for no folders", () => {
    expect(buildFolderTree([])).toEqual([]);
  });
});
