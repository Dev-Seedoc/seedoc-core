import type { FolderRead } from "@/lib/api/types";

export interface FolderNode {
  folder: FolderRead;
  children: FolderNode[];
}

// Siblings by `sort_order`, then by name in German order (umlauts next to their base letter, not after "z").
function compareFolders(a: FolderRead, b: FolderRead): number {
  return a.sort_order - b.sort_order || a.name.localeCompare(b.name, "de");
}

// The API returns one flat list per space (API.md §3.2); the tree is built here from `parent_id`.
export function buildFolderTree(folders: FolderRead[]): FolderNode[] {
  const nodes = new Map(folders.map((folder) => [folder.id, { folder, children: [] as FolderNode[] }]));
  const roots: FolderNode[] = [];
  for (const node of nodes.values()) {
    const parent = node.folder.parent_id ? nodes.get(node.folder.parent_id) : undefined;
    (parent ? parent.children : roots).push(node);
  }
  const sortLevel = (level: FolderNode[]) => {
    level.sort((a, b) => compareFolders(a.folder, b.folder));
    level.forEach((node) => {
      sortLevel(node.children);
    });
  };
  sortLevel(roots);
  return roots;
}
