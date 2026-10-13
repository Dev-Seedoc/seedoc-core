import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { FolderRead, SpaceRead } from "@/lib/api/types";
import { apiError, renderRoute, stubApi, TEST_ME } from "@/test/renderRoute";

const TENANT_ID = "00000000-0000-4000-8000-00000000000a";
const SPACES = `GET /api/v1/app/tenants/${TENANT_ID}/spaces`;
const FOLDERS = `GET /api/v1/app/tenants/${TENANT_ID}/folders`;

function space(id: string, name: string): SpaceRead {
  return { id, name, created_at: "2026-10-13T10:00:00Z" };
}

function folder(id: string, name: string, path: string, parentId: string | null = null): FolderRead {
  return {
    id,
    space_id: "handbuecher",
    parent_id: parentId,
    name,
    path,
    sort_order: 0,
    default_access_level: "public",
    default_doc_type: null,
    default_language: null,
    created_at: "2026-10-13T10:00:00Z",
    updated_at: "2026-10-13T10:00:00Z",
  };
}

const HANDBUECHER = space("handbuecher", "Handbücher");
const ZERTIFIKATE = space("zertifikate", "Zertifikate");
const FOLDERS_OF: Record<string, FolderRead[]> = {
  handbuecher: [
    folder("sicherheit", "Sicherheit", "Sicherheit"),
    folder("hinweise", "Hinweise", "Sicherheit/Hinweise", "sicherheit"),
    folder("laser", "Laser", "Sicherheit/Hinweise/Laser", "hinweise"),
    folder("wartung", "Wartung", "Wartung"),
  ],
  zertifikate: [{ ...folder("ce", "CE", "CE"), space_id: "zertifikate" }],
};

function page<T>(items: T[]) {
  return { status: 200, body: { items, next_cursor: null } };
}

// Two spaces; each space's folders by the `space_id` query parameter.
function stubLibrary(spaces: SpaceRead[] = [HANDBUECHER, ZERTIFIKATE]) {
  return stubApi({
    [SPACES]: page(spaces),
    [FOLDERS]: (request) => page(FOLDERS_OF[new URL(request.url).searchParams.get("space_id") ?? ""] ?? []),
  });
}

function treeItem(name: string): HTMLElement {
  return screen.getByRole("treeitem", { name: new RegExp(`^${name}`) });
}

function visibleFolderNames(): string[] {
  // The name is the first text of each row; nested rows are their own treeitems.
  return screen.getAllByRole("treeitem").map((item) => item.querySelector("span.truncate")?.textContent ?? "");
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("DocumentsPage", () => {
  it("shows the first space with its top-level folders", async () => {
    stubLibrary();
    renderRoute("/documents", TEST_ME);

    expect(await screen.findByRole("tree", { name: "Ordner in Handbücher" })).toBeInTheDocument();
    expect(screen.getByLabelText("Bereich")).toHaveValue("handbuecher");
    expect(visibleFolderNames()).toEqual(["Sicherheit", "Wartung"]);
    expect(treeItem("Sicherheit")).toHaveAttribute("aria-expanded", "false");
    expect(treeItem("Wartung")).not.toHaveAttribute("aria-expanded");
    expect(screen.getByRole("heading", { name: "Kein Ordner ausgewählt" })).toBeInTheDocument();
  });

  it("selects a folder into the URL and shows its path", async () => {
    stubLibrary();
    const router = renderRoute("/documents", TEST_ME);

    fireEvent.click(await screen.findByText("Wartung"));

    expect(router.state.location.search).toBe("?space_id=handbuecher&folder_id=wartung");
    expect(treeItem("Wartung")).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("heading", { name: "Wartung" })).toBeInTheDocument();
  });

  it("opens a folder from the URL with its parents expanded", async () => {
    stubLibrary();
    renderRoute("/documents?space_id=handbuecher&folder_id=laser", TEST_ME);

    expect(await screen.findByRole("heading", { name: "Sicherheit/Hinweise/Laser" })).toBeInTheDocument();
    expect(visibleFolderNames()).toEqual(["Sicherheit", "Hinweise", "Laser", "Wartung"]);
    expect(treeItem("Laser")).toHaveAttribute("aria-selected", "true");
    // The selected folder is the one tab stop of the tree.
    expect(treeItem("Laser")).toHaveAttribute("tabindex", "0");
    expect(treeItem("Sicherheit")).toHaveAttribute("tabindex", "-1");
  });

  it("is usable with the keyboard alone", async () => {
    stubLibrary();
    const router = renderRoute("/documents", TEST_ME);
    const first = await screen.findByRole("treeitem", { name: /^Sicherheit/ });
    first.focus();

    fireEvent.keyDown(first, { key: "ArrowRight" }); // open Sicherheit
    expect(treeItem("Sicherheit")).toHaveAttribute("aria-expanded", "true");
    fireEvent.keyDown(treeItem("Sicherheit"), { key: "ArrowDown" }); // to Hinweise
    expect(treeItem("Hinweise")).toHaveFocus();
    fireEvent.keyDown(treeItem("Hinweise"), { key: "ArrowLeft" }); // closed folder → back to its parent
    expect(treeItem("Sicherheit")).toHaveFocus();
    fireEvent.keyDown(treeItem("Sicherheit"), { key: "End" });
    expect(treeItem("Wartung")).toHaveFocus();
    fireEvent.keyDown(treeItem("Wartung"), { key: "Enter" });

    expect(router.state.location.search).toBe("?space_id=handbuecher&folder_id=wartung");
  });

  it("switches the space and forgets the folder", async () => {
    stubLibrary();
    const router = renderRoute("/documents?space_id=handbuecher&folder_id=wartung", TEST_ME);
    await screen.findByRole("tree", { name: "Ordner in Handbücher" });

    fireEvent.change(screen.getByLabelText("Bereich"), { target: { value: "zertifikate" } });

    expect(await screen.findByRole("tree", { name: "Ordner in Zertifikate" })).toBeInTheDocument();
    expect(visibleFolderNames()).toEqual(["CE"]);
    expect(router.state.location.search).toBe("?space_id=zertifikate");
  });

  it("shows a single space as text instead of a choice", async () => {
    stubLibrary([HANDBUECHER]);
    renderRoute("/documents", TEST_ME);

    await screen.findByRole("tree");
    expect(screen.queryByLabelText("Bereich")).not.toBeInTheDocument();
    expect(screen.getByText("Handbücher")).toBeInTheDocument();
  });

  it("explains a tenant without spaces", async () => {
    stubLibrary([]);
    renderRoute("/documents", TEST_ME);

    expect(await screen.findByRole("heading", { name: "Noch keine Bereiche" })).toBeInTheDocument();
  });

  it("explains a space without folders", async () => {
    stubApi({ [SPACES]: page([ZERTIFIKATE]), [FOLDERS]: page([]) });
    renderRoute("/documents", TEST_ME);

    expect(await screen.findByRole("heading", { name: "Noch keine Ordner" })).toBeInTheDocument();
  });

  it("shows a load error with a retry that works", async () => {
    let failing = true;
    stubApi({
      [SPACES]: () => (failing ? apiError(500, "internal_error") : page([HANDBUECHER])),
      [FOLDERS]: page(FOLDERS_OF.handbuecher ?? []),
    });
    renderRoute("/documents", TEST_ME);

    const error = await screen.findByRole("heading", { name: "Die Bereiche konnten nicht geladen werden." });
    failing = false;
    fireEvent.click(within(error.parentElement ?? document.body).getByRole("button", { name: "Wiederholen" }));

    await waitFor(() => {
      expect(screen.getByRole("tree", { name: "Ordner in Handbücher" })).toBeInTheDocument();
    });
  });
});
