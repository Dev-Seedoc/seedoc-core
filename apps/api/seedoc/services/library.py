"""Shared lookups for the document library (spaces, folders, documents). Every service that needs "the tenant's
space/folder or 404" or a folder path uses these, so the rules live in one place."""

from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from seedoc.errors import AppError, ErrorCode
from seedoc.models.documents import Folder, Space

PATH_SEPARATOR = "/"
# DIN 5007-1 ("dictionary order"): umlauts sort like their base letter, ß like "ss", case is ignored.
_GERMAN_FOLD = str.maketrans({"ä": "a", "ö": "o", "ü": "u", "ß": "ss"})


async def get_space(db: AsyncSession, tenant_id: UUID, space_id: UUID) -> Space:
    """The tenant's space, or `404 not_found` — also for another tenant's id, so its existence is not revealed."""
    space = await db.scalar(select(Space).where(Space.id == space_id, Space.tenant_id == tenant_id))
    if space is None:
        raise AppError(ErrorCode.NOT_FOUND)
    return space


async def get_folder(db: AsyncSession, tenant_id: UUID, folder_id: UUID) -> Folder:
    """The tenant's folder, or `404 not_found` (same rule as `get_space`)."""
    folder = await db.scalar(select(Folder).where(Folder.id == folder_id, Folder.tenant_id == tenant_id))
    if folder is None:
        raise AppError(ErrorCode.NOT_FOUND)
    return folder


def build_folder_paths(folders: Iterable[Folder]) -> dict[UUID, str]:
    """`{folder id: "Root/Child/Folder"}` (folder names from the root, without the space name). Pass every folder of
    the space(s) involved: a parent is always in the same space, so every parent is in `folders`."""
    by_id = {folder.id: folder for folder in folders}
    paths: dict[UUID, str] = {}
    for folder in by_id.values():
        names: list[str] = []
        current: Folder | None = folder
        while current is not None:
            names.append(current.name)
            current = by_id.get(current.parent_id) if current.parent_id is not None else None
        paths[folder.id] = PATH_SEPARATOR.join(reversed(names))
    return paths


def get_sort_key(text: str) -> tuple[str, str]:
    """German-friendly sort key: "Ärger" sorts next to "Arger", not after "Z". The second element keeps the order
    stable when two texts fold to the same key."""
    return text.casefold().translate(_GERMAN_FOLD), text


def get_path_sort_key(path: str) -> tuple[tuple[str, str], ...]:
    """Sort key for folder paths, compared folder by folder, so every folder is directly followed by its subfolders
    ("Sicherheit", "Sicherheit/Hinweise", "Sicherheit Neu") — comparing whole strings would put "Sicherheit Neu"
    in between, because " " sorts before "/"."""
    return tuple(get_sort_key(name) for name in path.split(PATH_SEPARATOR))
