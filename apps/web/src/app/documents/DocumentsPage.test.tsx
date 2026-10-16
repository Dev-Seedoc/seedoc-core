import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { toast } from "sonner";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { FolderRead, MeRead, SpaceRead } from "@/lib/api/types";
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
  vi.restoreAllMocks();
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

// ─────────────────────────── push 2: changing folders and spaces ───────────────────────────

const FOLDERS_PATH = `/api/v1/app/tenants/${TENANT_ID}/folders`;
const EDITOR_ME: MeRead = {
  ...TEST_ME,
  memberships: TEST_ME.memberships.map((membership) => ({ ...membership, role: "editor" as const })),
};

// A fake library API with state: GET lists, POST adds (path built from the parent), PATCH answers the folder,
// DELETE removes it — or answers `deleteAnswer` (e.g. 409 "not empty").
function stubFolderApi(initial: FolderRead[], deleteAnswer?: ReturnType<typeof apiError>) {
  let folders = [...initial];
  const fetchMock = vi.fn(async (request: Request) => {
    const url = new URL(request.url);
    const folderId = url.pathname.startsWith(`${FOLDERS_PATH}/`) ? url.pathname.split("/").at(-1) : undefined;
    if (url.pathname.endsWith("/spaces")) {
      return Response.json({ items: [HANDBUECHER], next_cursor: null });
    }
    if (request.method === "GET" && url.pathname === FOLDERS_PATH) {
      return Response.json({ items: folders, next_cursor: null });
    }
    if (request.method === "POST" && url.pathname === FOLDERS_PATH) {
      const body = (await request.clone().json()) as { name: string; parent_id: string | null };
      const parent = folders.find((item) => item.id === body.parent_id);
      const id = `new-${String(folders.length)}`;
      const created = { ...folder(id, body.name, parent ? `${parent.path}/${body.name}` : body.name, body.parent_id) };
      folders = [...folders, created];
      return Response.json(created, { status: 201 });
    }
    if (request.method === "PATCH" && folderId) {
      return Response.json(folders.find((item) => item.id === folderId));
    }
    if (request.method === "DELETE" && folderId) {
      if (deleteAnswer) {
        return Response.json(deleteAnswer.body, { status: deleteAnswer.status });
      }
      folders = folders.filter((item) => item.id !== folderId);
      return new Response(null, { status: 204 });
    }
    return Response.json(apiError(404, "not_found").body, { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function lastRequest(fetchMock: { mock: { calls: [Request][] } }, method: string): Request | undefined {
  return fetchMock.mock.calls.map(([request]) => request).findLast((request) => request.method === method);
}

async function openFolderMenuItem(name: string) {
  fireEvent.keyDown(await screen.findByRole("button", { name: "Ordner-Aktionen" }), { key: "Enter" });
  fireEvent.click(await screen.findByRole("menuitem", { name }));
  return screen.findByRole("dialog");
}

const SAFETY_DEFAULTS: Partial<FolderRead> = {
  default_access_level: "customer",
  default_doc_type: "safety_instruction",
  default_language: "de",
};

describe("DocumentsPage – changing folders", () => {
  it("creates a top-level folder with defaults and selects it", async () => {
    const fetchMock = stubFolderApi(FOLDERS_OF.handbuecher ?? []);
    const router = renderRoute("/documents", TEST_ME);
    const success = vi.spyOn(toast, "success");

    fireEvent.click(await screen.findByRole("button", { name: "Ordner anlegen" }));
    const dialog = await screen.findByRole("dialog", { name: "Ordner anlegen" });
    fireEvent.change(within(dialog).getByLabelText("Name"), { target: { value: "  Betrieb  " } });
    fireEvent.change(within(dialog).getByLabelText("Dokumenttyp (Vorgabe)"), { target: { value: "operating_manual" } });
    fireEvent.change(within(dialog).getByLabelText("Sprache (Vorgabe)"), { target: { value: "de" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Anlegen" }));

    await waitFor(() => {
      expect(router.state.location.search).toBe("?space_id=handbuecher&folder_id=new-4");
    });
    expect(await lastRequest(fetchMock, "POST")?.json()).toEqual({
      space_id: "handbuecher",
      parent_id: null,
      name: "Betrieb",
      default_access_level: "public",
      default_doc_type: "operating_manual",
      default_language: "de",
    });
    expect(success).toHaveBeenCalledWith("Ordner angelegt.");
    expect(await screen.findByRole("treeitem", { name: "Betrieb" })).toHaveAttribute("aria-selected", "true");
  });

  it("shows a taken name under the field and keeps the dialog open", async () => {
    stubApi({
      [SPACES]: page([HANDBUECHER]),
      [FOLDERS]: page(FOLDERS_OF.handbuecher ?? []),
      [`POST ${FOLDERS_PATH}`]: apiError(409, "conflict", { field: "name" }),
    });
    renderRoute("/documents", TEST_ME);

    fireEvent.click(await screen.findByRole("button", { name: "Ordner anlegen" }));
    const dialog = await screen.findByRole("dialog", { name: "Ordner anlegen" });
    fireEvent.change(within(dialog).getByLabelText("Name"), { target: { value: "Wartung" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Anlegen" }));

    expect(await within(dialog).findByText("Ein Ordner mit diesem Namen existiert hier bereits.")).toBeInTheDocument();
    expect(within(dialog).getByLabelText("Name")).toHaveFocus();
    expect(within(dialog).queryByRole("alert")).not.toBeInTheDocument();
  });

  it("creates a subfolder with the parent's defaults and opens the parent", async () => {
    const sicherheit = { ...folder("sicherheit", "Sicherheit", "Sicherheit"), ...SAFETY_DEFAULTS };
    const fetchMock = stubFolderApi([sicherheit, folder("wartung", "Wartung", "Wartung")]);
    renderRoute("/documents?space_id=handbuecher&folder_id=sicherheit", TEST_ME);

    const dialog = await openFolderMenuItem("Unterordner anlegen");
    expect(within(dialog).getByRole("heading", { name: "Unterordner in „Sicherheit“ anlegen" })).toBeInTheDocument();
    expect(within(dialog).getByLabelText("Sichtbarkeit (Vorgabe)")).toHaveValue("customer");
    expect(within(dialog).getByLabelText("Dokumenttyp (Vorgabe)")).toHaveValue("safety_instruction");
    expect(within(dialog).getByLabelText("Sprache (Vorgabe)")).toHaveValue("de");
    fireEvent.change(within(dialog).getByLabelText("Name"), { target: { value: "Laser" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Anlegen" }));

    expect(await screen.findByRole("heading", { name: "Sicherheit/Laser" })).toBeInTheDocument();
    expect(screen.getByRole("treeitem", { name: "Sicherheit" })).toHaveAttribute("aria-expanded", "true");
    expect(await lastRequest(fetchMock, "POST")?.json()).toMatchObject({ parent_id: "sicherheit", name: "Laser" });
  });

  it("sends only the changed fields when editing, null to clear a default", async () => {
    const wartung = { ...folder("wartung", "Wartung", "Wartung"), ...SAFETY_DEFAULTS };
    const fetchMock = stubFolderApi([wartung]);
    renderRoute("/documents?space_id=handbuecher&folder_id=wartung", TEST_ME);

    const dialog = await openFolderMenuItem("Bearbeiten");
    expect(within(dialog).getByLabelText("Name")).toHaveValue("Wartung");
    fireEvent.change(within(dialog).getByLabelText("Dokumenttyp (Vorgabe)"), { target: { value: "" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Speichern" }));

    await waitFor(() => {
      expect(lastRequest(fetchMock, "PATCH")).toBeDefined();
    });
    expect(new URL(lastRequest(fetchMock, "PATCH")?.url ?? "").pathname).toBe(`${FOLDERS_PATH}/wartung`);
    expect(await lastRequest(fetchMock, "PATCH")?.json()).toEqual({ default_doc_type: null });
  });

  it("deletes an empty folder after confirming and selects its parent", async () => {
    const fetchMock = stubFolderApi(FOLDERS_OF.handbuecher ?? []);
    const router = renderRoute("/documents?space_id=handbuecher&folder_id=laser", TEST_ME);

    fireEvent.keyDown(await screen.findByRole("button", { name: "Ordner-Aktionen" }), { key: "Enter" });
    fireEvent.click(await screen.findByRole("menuitem", { name: "Löschen" }));
    const confirm = await screen.findByRole("alertdialog", { name: "Ordner „Laser“ löschen?" });
    expect(lastRequest(fetchMock, "DELETE")).toBeUndefined();
    fireEvent.click(within(confirm).getByRole("button", { name: "Löschen" }));

    await waitFor(() => {
      expect(router.state.location.search).toBe("?space_id=handbuecher&folder_id=hinweise");
    });
    expect(screen.queryByRole("treeitem", { name: "Laser" })).not.toBeInTheDocument();
  });

  it("explains a folder that is not empty and keeps it", async () => {
    stubFolderApi(FOLDERS_OF.handbuecher ?? [], apiError(409, "conflict"));
    renderRoute("/documents?space_id=handbuecher&folder_id=sicherheit", TEST_ME);
    const error = vi.spyOn(toast, "error");

    fireEvent.keyDown(await screen.findByRole("button", { name: "Ordner-Aktionen" }), { key: "Enter" });
    fireEvent.click(await screen.findByRole("menuitem", { name: "Löschen" }));
    fireEvent.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Löschen" }));

    await waitFor(() => {
      expect(error).toHaveBeenCalledWith(
        "Der Ordner ist nicht leer. Entfernen Sie zuerst seine Unterordner und Dokumente – auch die im Papierkorb.",
      );
    });
    expect(screen.getByRole("treeitem", { name: "Sicherheit" })).toBeInTheDocument();
  });
});

describe("DocumentsPage – spaces", () => {
  it("lets owners create a space and opens it", async () => {
    let spaces = [HANDBUECHER];
    const fetchMock = stubApi({
      [SPACES]: () => page(spaces),
      [FOLDERS]: page([]),
      [`POST /api/v1/app/tenants/${TENANT_ID}/spaces`]: () => {
        spaces = [...spaces, ZERTIFIKATE];
        return { status: 201, body: ZERTIFIKATE };
      },
    });
    const router = renderRoute("/documents", TEST_ME);

    fireEvent.click(await screen.findByRole("button", { name: "Bereich anlegen" }));
    const dialog = await screen.findByRole("dialog", { name: "Bereich anlegen" });
    fireEvent.change(within(dialog).getByLabelText("Name"), { target: { value: "Zertifikate" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Anlegen" }));

    await waitFor(() => {
      expect(router.state.location.search).toBe("?space_id=zertifikate");
    });
    expect(await lastRequest(fetchMock, "POST")?.json()).toEqual({ name: "Zertifikate" });
    expect(await screen.findByLabelText("Bereich")).toHaveValue("zertifikate");
  });

  it("renames the current space", async () => {
    const fetchMock = stubApi({
      [SPACES]: page([HANDBUECHER]),
      [FOLDERS]: page([]),
      [`PATCH /api/v1/app/tenants/${TENANT_ID}/spaces/handbuecher`]: { status: 200, body: HANDBUECHER },
    });
    renderRoute("/documents", TEST_ME);

    fireEvent.click(await screen.findByRole("button", { name: "Bereich umbenennen" }));
    const dialog = await screen.findByRole("dialog", { name: "Bereich umbenennen" });
    expect(within(dialog).getByLabelText("Name")).toHaveValue("Handbücher");
    fireEvent.change(within(dialog).getByLabelText("Name"), { target: { value: "Anleitungen" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Speichern" }));

    await waitFor(() => {
      expect(lastRequest(fetchMock, "PATCH")).toBeDefined();
    });
    expect(await lastRequest(fetchMock, "PATCH")?.json()).toEqual({ name: "Anleitungen" });
  });

  it("shows editors no space actions", async () => {
    stubLibrary();
    renderRoute("/documents", EDITOR_ME);

    await screen.findByRole("tree");
    expect(screen.queryByRole("button", { name: "Bereich anlegen" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Bereich umbenennen" })).not.toBeInTheDocument();
    // Folders are for every member.
    expect(screen.getByRole("button", { name: "Ordner anlegen" })).toBeInTheDocument();
  });

  it("tells editors without spaces to ask an administrator", async () => {
    stubLibrary([]);
    renderRoute("/documents", EDITOR_ME);
    expect(await screen.findByText(/Ein Administrator kann einen Bereich anlegen/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Bereich anlegen" })).not.toBeInTheDocument();
  });
});
