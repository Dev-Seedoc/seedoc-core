"""Shared response shapes (NAMING §4 and §5)."""

from pydantic import BaseModel

DEFAULT_PAGE_LIMIT = 50
MAX_PAGE_LIMIT = 200


class Page[T](BaseModel):
    """List response: `{"items": [...], "next_cursor": "..." | null}`. Pass `next_cursor` back as `cursor`."""

    items: list[T]
    next_cursor: str | None
