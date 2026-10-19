"""Split page texts into overlapping chunks for search and the assistant (ARCHITECTURE §9).

~800 tokens per chunk with 100 tokens overlap, never across pages. There is no tokenizer in the stack, so tokens are
estimated as 4 characters (the usual rate for English; German words are longer, so chunks come out a bit smaller in
tokens, which is the safe side for the embedding model). Chunks break between words, never inside one.
"""

import re
from dataclasses import dataclass

CHUNK_TOKENS = 800
OVERLAP_TOKENS = 100
CHARS_PER_TOKEN = 4
CHUNK_CHARS = CHUNK_TOKENS * CHARS_PER_TOKEN
OVERLAP_CHARS = OVERLAP_TOKENS * CHARS_PER_TOKEN

_WORD = re.compile(r"\S+\s*")  # a word with the whitespace after it, so joining keeps the line breaks


@dataclass(frozen=True)
class Chunk:
    page_no: int  # 1-based
    chunk_index: int  # 0-based, running through the whole version
    content: str


def build_chunks(page_texts: list[str]) -> list[Chunk]:
    """Chunks of all pages in order; empty pages give none."""
    chunks: list[Chunk] = []
    for page_no, text in enumerate(page_texts, start=1):
        for content in split_text(text):
            chunks.append(Chunk(page_no=page_no, chunk_index=len(chunks), content=content))
    return chunks


def split_text(text: str, size: int = CHUNK_CHARS, overlap: int = OVERLAP_CHARS) -> list[str]:
    """Pieces of at most `size` characters (a single longer word is cut), each starting with the last ≥ `overlap`
    characters of words of the previous piece."""
    words = [match.group() for match in _WORD.finditer(text)]
    words = [piece for word in words for piece in _cut(word, size)]
    pieces: list[str] = []
    start = 0
    while start < len(words):
        end, length = start, 0
        while end < len(words) and length + len(words[end].rstrip()) <= size:
            length += len(words[end])
            end += 1
        end = max(end, start + 1)
        pieces.append("".join(words[start:end]).strip())
        if end == len(words):
            break
        # Step back from the end until the overlap is covered, but always move forward.
        back, covered = end, 0
        while back > start + 1 and covered < overlap:
            back -= 1
            covered += len(words[back])
        start = back
    return pieces


def _cut(word: str, size: int) -> list[str]:
    return [word[index : index + size] for index in range(0, len(word), size)] if len(word) > size else [word]
