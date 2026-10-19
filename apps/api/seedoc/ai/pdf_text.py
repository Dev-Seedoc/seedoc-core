"""Page text of a PDF with `pypdfium2` (ARCHITECTURE §3, D1 — never PyMuPDF). Scans without a text layer give
empty pages; OCR comes later (Docling)."""

import re

import pypdfium2 as pdfium  # pyright: ignore[reportMissingTypeStubs]  (no py.typed; its sources are typed)

# Written as escapes on purpose: the characters themselves are invisible or look like others.
_REPLACEMENT_CHARACTER = "\N{REPLACEMENT CHARACTER}"  # pdfium's stand-in for glyphs without a Unicode mapping
_SOFT_HYPHEN = "\N{SOFT HYPHEN}"
_SPACES = re.compile("[ \t\N{NO-BREAK SPACE}]+")


class PdfReadError(Exception):
    """The file is not a PDF pdfium can open (broken, or protected by a password)."""


def extract_page_texts(data: bytes) -> list[str]:
    """One cleaned text per page, in page order (so `len(result)` is the page count). Blocking — run it in a
    thread."""
    try:
        document = pdfium.PdfDocument(data)
    except pdfium.PdfiumError as exc:
        raise PdfReadError(str(exc)) from exc
    try:
        pages: list[str] = []
        for index in range(len(document)):
            page = document[index]
            text_page = page.get_textpage()
            try:
                pages.append(clean_text(text_page.get_text_range()))
            finally:
                text_page.close()
                page.close()
        return pages
    finally:
        document.close()


def clean_text(text: str) -> str:
    """Unix line ends, no NUL (Postgres text cannot hold it), no unmapped glyphs or soft hyphens, single spaces, no
    blank lines."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    text = text.replace(_REPLACEMENT_CHARACTER, "").replace(_SOFT_HYPHEN, "")
    lines = (_SPACES.sub(" ", line).strip() for line in text.split("\n"))
    return "\n".join(line for line in lines if line)
