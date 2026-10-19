import { ChevronRight, Folder, FolderOpen } from "lucide-react";
import { type KeyboardEvent, useId, useMemo, useRef, useState } from "react";

import type { FolderRead } from "@/lib/api/types";
import { cn } from "@/lib/utils";

import { buildFolderTree, type FolderNode } from "./buildFolderTree";

// Ids of the folder's parents, so a selected folder (e.g. from the URL) starts visible.
function ancestorIds(folders: FolderRead[], folderId: string | undefined): string[] {
  const byId = new Map(folders.map((folder) => [folder.id, folder]));
  const ids: string[] = [];
  let parentId = folderId ? byId.get(folderId)?.parent_id : null;
  while (parentId) {
    ids.push(parentId);
    parentId = byId.get(parentId)?.parent_id ?? null;
  }
  return ids;
}

interface VisibleItem {
  node: FolderNode;
  level: number;
  parentId: string | null;
}

// The rows on screen, top to bottom: the order for arrow-key navigation.
function listVisible(nodes: FolderNode[], expanded: Set<string>, level = 1, parentId: string | null = null) {
  const items: VisibleItem[] = [];
  for (const node of nodes) {
    items.push({ node, level, parentId });
    if (expanded.has(node.folder.id)) {
      items.push(...listVisible(node.children, expanded, level + 1, node.folder.id));
    }
  }
  return items;
}

interface FolderTreeProps {
  folders: FolderRead[];
  selectedFolderId: string | undefined;
  onSelect: (folderId: string) => void;
  label: string;
}

// WAI-ARIA tree view: one tab stop; arrow keys move, Right/Left open/close, Enter/Space select, Home/End jump.
export function FolderTree({ folders, selectedFolderId, onSelect, label }: FolderTreeProps) {
  const tree = useMemo(() => buildFolderTree(folders), [folders]);
  const [expanded, setExpanded] = useState(() => new Set(ancestorIds(folders, selectedFolderId)));
  // When the selection changes from outside (new subfolder, back button, link) or the list reloads with it, open
  // its parents so it is visible. Adjusted during render instead of in an effect (react.dev "You Might Not Need an
  // Effect"); folders the user closed stay closed until then.
  const [shownSelection, setShownSelection] = useState({ folders, selectedFolderId });
  if (shownSelection.folders !== folders || shownSelection.selectedFolderId !== selectedFolderId) {
    setShownSelection({ folders, selectedFolderId });
    const closedParents = ancestorIds(folders, selectedFolderId).filter((id) => !expanded.has(id));
    if (closedParents.length > 0) {
      setExpanded(new Set([...expanded, ...closedParents]));
    }
  }
  const idPrefix = useId();
  const [focusedId, setFocusedId] = useState<string | undefined>(undefined);
  const rowRefs = useRef(new Map<string, HTMLLIElement>());

  const visible = listVisible(tree, expanded);
  // The tab stop: the focused row, else the selected one (if visible), else the first.
  const tabStopId =
    visible.find((item) => item.node.folder.id === focusedId)?.node.folder.id ??
    visible.find((item) => item.node.folder.id === selectedFolderId)?.node.folder.id ??
    visible[0]?.node.folder.id;

  function setOpen(folderId: string, open: boolean) {
    setExpanded((current) => {
      const next = new Set(current);
      if (open) {
        next.add(folderId);
      } else {
        next.delete(folderId);
      }
      return next;
    });
  }

  function moveFocus(folderId: string | undefined) {
    if (folderId) {
      setFocusedId(folderId);
      rowRefs.current.get(folderId)?.focus();
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLLIElement>, item: VisibleItem) {
    const index = visible.indexOf(item);
    const id = item.node.folder.id;
    const hasChildren = item.node.children.length > 0;
    const isOpen = expanded.has(id);
    const handlers: Record<string, () => void> = {
      ArrowDown: () => {
        moveFocus(visible[index + 1]?.node.folder.id);
      },
      ArrowUp: () => {
        moveFocus(visible[index - 1]?.node.folder.id);
      },
      Home: () => {
        moveFocus(visible[0]?.node.folder.id);
      },
      End: () => {
        moveFocus(visible.at(-1)?.node.folder.id);
      },
      ArrowRight: () => {
        if (hasChildren && !isOpen) {
          setOpen(id, true);
        } else if (hasChildren) {
          moveFocus(item.node.children[0]?.folder.id);
        }
      },
      ArrowLeft: () => {
        if (hasChildren && isOpen) {
          setOpen(id, false);
        } else {
          moveFocus(item.parentId ?? undefined);
        }
      },
      Enter: () => {
        onSelect(id);
      },
      " ": () => {
        onSelect(id);
      },
    };
    const handler = handlers[event.key];
    if (handler) {
      event.preventDefault();
      event.stopPropagation();
      handler();
    }
  }

  function renderNodes(nodes: FolderNode[], level: number, parentId: string | null) {
    return nodes.map((node) => {
      const id = node.folder.id;
      const hasChildren = node.children.length > 0;
      const isOpen = expanded.has(id);
      const isSelected = id === selectedFolderId;
      const item: VisibleItem = visible.find((entry) => entry.node.folder.id === id) ?? { node, level, parentId };
      const Icon = isOpen ? FolderOpen : Folder;
      return (
        <li
          key={id}
          ref={(element) => {
            if (element) {
              rowRefs.current.set(id, element);
            } else {
              rowRefs.current.delete(id);
            }
          }}
          role="treeitem"
          // Named by the folder name alone, not by the text of all its open subfolders.
          aria-labelledby={`${idPrefix}-${id}`}
          aria-level={level}
          aria-selected={isSelected}
          aria-expanded={hasChildren ? isOpen : undefined}
          tabIndex={id === tabStopId ? 0 : -1}
          className="outline-none [&:focus-visible>div]:ring-[3px] [&:focus-visible>div]:ring-ring/50"
          onKeyDown={(event) => {
            handleKeyDown(event, item);
          }}
          onFocus={(event) => {
            if (event.target === event.currentTarget) {
              setFocusedId(id);
            }
          }}
        >
          <div
            className={cn(
              "flex cursor-pointer items-center gap-1.5 rounded-md py-1.5 pr-2 text-sm",
              isSelected ? "bg-accent text-accent-foreground font-medium" : "hover:bg-muted",
            )}
            style={{ paddingLeft: `${String((level - 1) * 16 + 4)}px` }}
            onClick={() => {
              onSelect(id);
            }}
          >
            <span
              aria-hidden="true"
              className={cn("flex size-5 shrink-0 items-center justify-center", !hasChildren && "invisible")}
              onClick={(event) => {
                event.stopPropagation();
                setOpen(id, !isOpen);
              }}
            >
              <ChevronRight className={cn("size-4 transition-transform", isOpen && "rotate-90")} />
            </span>
            <Icon className="text-muted-foreground size-4 shrink-0" aria-hidden="true" />
            <span id={`${idPrefix}-${id}`} className="truncate">
              {node.folder.name}
            </span>
          </div>
          {hasChildren && isOpen && (
            <ul role="group" className="flex flex-col">
              {renderNodes(node.children, level + 1, id)}
            </ul>
          )}
        </li>
      );
    });
  }

  return (
    <ul role="tree" aria-label={label} className="flex flex-col">
      {renderNodes(tree, 1, null)}
    </ul>
  );
}
