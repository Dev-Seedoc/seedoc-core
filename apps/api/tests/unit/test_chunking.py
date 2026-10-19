"""Chunking (ARCHITECTURE §9): ~800 tokens (estimated 4 characters each), 100 tokens overlap, never across pages."""

from itertools import pairwise

from seedoc.ai.chunking import CHUNK_CHARS, OVERLAP_CHARS, build_chunks, split_text


def _words(count: int, prefix: str = "wort") -> str:
    return " ".join(f"{prefix}{index:04d}" for index in range(count))  # 8 characters + 1 space each


def test_short_text_is_one_chunk() -> None:
    assert split_text("Sicherheitshinweise\nVor dem Einschalten lesen.") == [
        "Sicherheitshinweise\nVor dem Einschalten lesen."
    ]


def test_empty_text_has_no_chunks() -> None:
    assert split_text("") == []
    assert build_chunks(["", ""]) == []


def test_long_text_is_split_into_chunks_of_at_most_the_size() -> None:
    text = _words(1000)  # ~9,000 characters; each chunk moves on by 3,200 - 400 = 2,800

    pieces = split_text(text)

    assert len(pieces) == 4
    assert all(len(piece) <= CHUNK_CHARS for piece in pieces)
    assert all(len(piece) > CHUNK_CHARS - 20 for piece in pieces[:-1])  # filled up to the size, whole words only


def test_each_chunk_starts_with_the_end_of_the_previous_one() -> None:
    pieces = split_text(_words(1000))

    for previous, current in pairwise(pieces):
        first_word = current.split()[0]
        overlap = previous[previous.index(first_word) :]  # from the shared word to the end of the previous chunk
        assert current.startswith(overlap)
        assert OVERLAP_CHARS - 9 <= len(overlap) <= OVERLAP_CHARS + 9  # whole words of 9 characters


def test_chunks_cover_every_word_in_order() -> None:
    text = _words(1000)

    pieces = split_text(text)

    seen: list[str] = []
    for piece in pieces:
        for word in piece.split():
            if not seen or word > seen[-1]:
                seen.append(word)
    assert seen == text.split()


def test_chunks_break_between_words() -> None:
    words = set(_words(1000).split())

    for piece in split_text(_words(1000)):
        assert set(piece.split()) <= words


def test_line_breaks_are_kept() -> None:
    text = "\n".join(_words(20, prefix=f"z{line}x") for line in range(30))

    pieces = split_text(text)

    assert all("\n" in piece for piece in pieces)
    assert "".join(pieces[0].split()) in "".join(text.split())


def test_a_word_longer_than_a_chunk_is_cut() -> None:
    pieces = split_text("x" * (CHUNK_CHARS * 2 + 10))

    assert [len(piece) for piece in pieces] == [CHUNK_CHARS, CHUNK_CHARS, 10]


def test_build_chunks_never_crosses_pages_and_numbers_through() -> None:
    chunks = build_chunks(["Seite eins", "", _words(1000), "Seite vier"])

    assert [chunk.page_no for chunk in chunks] == [1, 3, 3, 3, 3, 4]
    assert [chunk.chunk_index for chunk in chunks] == [0, 1, 2, 3, 4, 5]
    assert chunks[0].content == "Seite eins"
    assert chunks[-1].content == "Seite vier"
