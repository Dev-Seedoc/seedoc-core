"""Shared response shapes (NAMING §4 and §5)."""

from typing import Annotated

from pydantic import BaseModel, StringConstraints

DEFAULT_PAGE_LIMIT = 50
MAX_PAGE_LIMIT = 200

# A display name (space, folder, ...): surrounding spaces removed, then 1 to 200 characters.
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class Page[T](BaseModel):
    """List response: `{"items": [...], "next_cursor": "..." | null}`. Pass `next_cursor` back as `cursor`."""

    items: list[T]
    next_cursor: str | None
