"""Embeddings for text chunks (ARCHITECTURE §9): batches of 96 texts per provider request."""

from collections.abc import Sequence

EMBED_BATCH_SIZE = 96


def batches[T](items: Sequence[T], size: int = EMBED_BATCH_SIZE) -> list[Sequence[T]]:
    """`items` in consecutive slices of at most `size`, in order."""
    return [items[start : start + size] for start in range(0, len(items), size)]
