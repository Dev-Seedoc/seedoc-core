"""Shared response shapes (NAMING §4 and §5) and field types used by several resources."""

from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field, StringConstraints

from seedoc.languages import SUPPORTED_LANGUAGES

DEFAULT_PAGE_LIMIT = 50
MAX_PAGE_LIMIT = 200

# A display name (space, folder, ...): surrounding spaces removed, then 1 to 200 characters.
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


def _check_required_languages(languages: list[str]) -> list[str]:
    if len(set(languages)) != len(languages):
        raise ValueError("languages must be distinct")
    unsupported = [language for language in languages if language not in SUPPORTED_LANGUAGES]
    if unsupported:
        raise ValueError(f"unsupported language: {unsupported[0]}")
    return languages


# `required_languages` of products and deliveries: 1 to 25 distinct supported ISO codes, in the given order.
RequiredLanguages = Annotated[
    list[str], Field(min_length=1, max_length=len(SUPPORTED_LANGUAGES)), AfterValidator(_check_required_languages)
]


class Page[T](BaseModel):
    """List response: `{"items": [...], "next_cursor": "..." | null}`. Pass `next_cursor` back as `cursor`."""

    items: list[T]
    next_cursor: str | None
